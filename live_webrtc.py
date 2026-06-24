"""Mode Live : traitement vidéo image par image, alimenté par la caméra du
navigateur (PC ou téléphone) via streamlit-webrtc, au lieu de la webcam du
serveur.

`LiveProcessor.process()` reprend telle quelle la logique de dessin/suivi qui
tournait auparavant dans une boucle `while` auto-alimentée par
`cv2.VideoCapture` côté serveur (squelette MediaPipe, suivi des prises par
homographie, flèches de guidage) — seule la source des frames change : elles
arrivent désormais poussées une par une par le callback WebRTC
(`video_frame_callback`), au lieu d'être tirées d'une webcam locale.
"""
import logging
import socket
import struct
import sys
import threading
import time

import cv2
import streamlit as st

from detectionV1 import detect_corps
from homographie import HomographyWorker, transformer_prises, preparer_reference
from path import trouver_prises_par_membre

# DEBUG temporaire — streamlit_webrtc journalise l'état réel de la connexion
# ICE (checking/failed/disconnected/connected) via logger.debug(...), jamais
# affiché par défaut (niveau racine = WARNING). Or c'est précisément ce qui
# manque : on voit bien que la connexion reste bloquée (signalling=True,
# playing=False) et qu'une exception de nettoyage aioice survient en boucle,
# mais jamais pourquoi l'ICE échoue (pas de réponse STUN ? allocation TURN
# refusée ? aucune paire de candidats valide ?). On active donc le niveau
# DEBUG sur aioice/aiortc/streamlit_webrtc, avec sortie vers stdout flush
# immédiat (cf. le souci déjà rencontré de prints non flush dans les logs
# cloud) — à retirer une fois le live diagnostiqué.
_diag_handler = logging.StreamHandler(sys.stdout)
_diag_handler.setFormatter(logging.Formatter("[ICE-DIAG] %(name)s: %(message)s"))
for _logger_name in ("aioice", "aiortc", "streamlit_webrtc"):
    _lg = logging.getLogger(_logger_name)
    _lg.setLevel(logging.DEBUG)
    _lg.addHandler(_diag_handler)
    _lg.propagate = False

# DEBUG temporaire — le serveur TURN répond bien désormais (turn/tcp:80),
# mais avec une réponse ALLOCATE ERROR ; `aioice` ne journalise jamais le
# détail (ERROR-CODE / REASON-PHRASE) de cette erreur, seulement
# "message_class=Class.ERROR". On patche request_with_retry() pour afficher
# les attributs complets de la réponse d'erreur — sans ça impossible de
# savoir si c'est un rejet d'identifiants (401/403) ou autre chose.
import aioice.turn as _aioice_turn  # noqa: E402

_original_request_with_retry = _aioice_turn.TurnClientMixin.request_with_retry


async def _patched_request_with_retry(self, request):
    try:
        return await _original_request_with_retry(self, request)
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None:
            print(f"[TURN-ERR-DIAG] {dict(resp.attributes)}", flush=True)
        else:
            print(f"[TURN-ERR-DIAG] exception sans response : {type(e).__name__}: {e}", flush=True)
        raise


_aioice_turn.TurnClientMixin.request_with_retry = _patched_request_with_retry


def _diag_reseau_ice():
    """DEBUG temporaire — exécuté une fois au démarrage du process serveur.

    Le live échoue systématiquement (négociation ICE qui boucle sur des
    retries STUN jusqu'à épuisement, cf. logs cloud) sans qu'on puisse dire,
    à la seule lecture des tracebacks asyncio internes à aioice, si c'est le
    flux UDP (STUN) qui est bloqué côté hébergement, le flux TCP (TURN) qui
    l'est aussi, ou autre chose. Ce test fait directement les deux requêtes
    depuis le serveur et log un résultat sans ambiguïté, à retirer une fois
    le live diagnostiqué.
    """
    def _test_udp_stun():
        try:
            transaction_id = b"\x00" * 12
            paquet = struct.pack("!HHI12s", 0x0001, 0, 0x2112A442, transaction_id)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(4)
            sock.sendto(paquet, ("stun.l.google.com", 19302))
            data, _ = sock.recvfrom(1024)
            print(f"[NET-DIAG] STUN UDP stun.l.google.com:19302 -> reponse recue ({len(data)} octets)", flush=True)
        except Exception as e:
            print(f"[NET-DIAG] STUN UDP stun.l.google.com:19302 -> ECHEC ({type(e).__name__}: {e})", flush=True)

    # openrelay.metered.ca:443 refuse la connexion (confirme via un test
    # precedent) - le projet OpenRelay a ete renomme cote Metered.ca vers
    # global.relay.metered.ca. On teste donc les deux domaines sur plusieurs
    # ports candidats pour trouver un relais TURN qui repond reellement,
    # sans creer aucun compte (simple test de connexion TCP).
    _CANDIDATS_TURN = [
        ("openrelay.metered.ca", 80),
        ("openrelay.metered.ca", 443),
        ("openrelay.metered.ca", 3478),
        ("global.relay.metered.ca", 80),
        ("global.relay.metered.ca", 443),
        ("global.relay.metered.ca", 3478),
    ]

    def _test_tcp_turn(host, port):
        try:
            sock = socket.create_connection((host, port), timeout=4)
            sock.close()
            print(f"[NET-DIAG] TCP {host}:{port} -> connexion etablie", flush=True)
        except Exception as e:
            print(f"[NET-DIAG] TCP {host}:{port} -> ECHEC ({type(e).__name__}: {e})", flush=True)

    print("[NET-DIAG] Lancement des tests reseau STUN/TURN...", flush=True)
    threading.Thread(target=_test_udp_stun, daemon=True).start()
    for _host, _port in _CANDIDATS_TURN:
        threading.Thread(target=_test_tcp_turn, args=(_host, _port), daemon=True).start()


_diag_reseau_ice()

# Le test "STUN seul" (sans TURN) a confirme que le P2P direct est impossible
# depuis Streamlit Community Cloud : aucune des paires de candidats (host LAN,
# srflx public) ne recoit jamais de reponse aux verifications de connectivite
# ICE, alors que le binding STUN sortant vers Google, lui, reussit aussitot —
# signe que l'hebergeur ne laisse passer aucun trafic UDP entrant arbitraire
# vers le conteneur (seul le HTTPS/WSS sur 443 est proxifie). Un relais TURN
# est donc structurellement necessaire ici, pas optionnel. L'ancien service
# public gratuit "openrelayproject" est mort (confirme via [TURN-ERR-DIAG] :
# ERROR-CODE 400 du vrai serveur Metered, alors que les identifiants etaient
# bien fournis) ; on utilise donc un compte Metered.ca (gratuit, sans CB), dont
# la cle va dans les secrets Streamlit Cloud (jamais dans le repo). En local,
# si les secrets ne sont pas configures, on retombe sur STUN seul (suffisant
# pour un test sur le meme reseau/LAN).
def _turn_server():
    try:
        username = st.secrets["metered_turn_username"]
        credential = st.secrets["metered_turn_credential"]
    except Exception:
        return None
    return {
        "urls": ["turn:global.relay.metered.ca:80?transport=tcp"],
        "username": username,
        "credential": credential,
    }


@st.cache_resource
def get_rtc_configuration():
    """Construit la configuration ICE lazily (dans le contexte Streamlit, après
    initialisation de st.secrets) pour que les credentials TURN soient bien lus.
    @st.cache_resource garantit un seul calcul par process."""
    turn = _turn_server()
    config = {
        "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}] + ([turn] if turn else []),
    }
    if turn:
        # Les candidats directs (host/srflx) n'aboutissent jamais sur cet
        # hebergement (cf. plus haut) : forcer "relay" evite d'attendre leur echec
        # avant de basculer sur le TURN, ce qui accelere la connexion.
        config["iceTransportPolicy"] = "relay"
    print(f"[TURN-CONFIG] {'TURN relay configure (mode relay)' if turn else 'STUN seul — pas de TURN'}", flush=True)
    return config

# "ideal" plutôt qu'une contrainte stricte : certains navigateurs (notamment
# Safari/iOS) rejettent la connexion si la caméra arrière demandée n'existe
# pas exactement, alors qu'"ideal" retombe sur une autre caméra disponible.
MEDIA_CONSTRAINTS = {"video": {"facingMode": {"ideal": "environment"}}, "audio": False}


# ==============================================================================
# MEDIAPIPE ASYNCHRONE (thread séparé)
# ==============================================================================
class AsyncPoseDetector:
    def __init__(self):
        self.landmarks  = None
        self.dimensions = (480, 360)
        self._pending   = None
        self._lock      = threading.Lock()
        self.running    = True
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, frame):
        with self._lock:
            self._pending = frame

    def _worker(self):
        while self.running:
            frame = None
            with self._lock:
                frame, self._pending = self._pending, None
            if frame is not None:
                res_lm, res_dim = detect_corps(frame)
                with self._lock:
                    self.landmarks  = res_lm if res_lm is not None else None
                    if res_lm is not None:
                        self.dimensions = res_dim
            else:
                time.sleep(0.001)

    def get(self):
        with self._lock:
            return self.landmarks, self.dimensions

    def stop(self):
        self.running = False


# ==============================================================================
# TRAITEMENT D'UNE FRAME — dessin + suivi des prises
# ==============================================================================
LIAISONS_SQUELETTE = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 31), (28, 32), (27, 29), (28, 30),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (16, 18), (16, 20), (16, 22), (18, 20),
]
# Zone "grimpeur" : rectangle centré sur les hanches, dont la taille s'adapte
# à l'écart épaule->cheville (donc à la distance caméra/grimpeur) au lieu d'un
# carré fixe — repris de l'ancien LiveWorker._loop() du script standalone.
FACTEUR_DEMI_HAUTEUR = 1.05
FACTEUR_DEMI_LARGEUR = 0.70
MARGE_SOUS_PIEDS     = 15
DEMI_HAUTEUR_DEFAUT  = 220
DEMI_LARGEUR_DEFAUT  = 100

JAUNE  = (0, 255, 255)
CYAN   = (255, 255, 0)
VERT   = (0, 255, 0)
ORANGE = (0, 165, 255)
BLEU   = (255, 0, 0)

# Couleur par membre pour la navigation
_COULEUR_MEMBRE = {
    'main_droite': JAUNE,
    'main_gauche': CYAN,
    'pied_droit':  VERT,
    'pied_gauche': ORANGE,
}

_IDX_MEMBRE = {
    16: 'main_droite',
    15: 'main_gauche',
    28: 'pied_droit',
    27: 'pied_gauche',
}


class LiveProcessor:
    def __init__(self, prises_ref, ref_img):
        # prises_ref : [{'ref_cx': int, 'ref_cy': int, 'usage': str}]
        self._prises_ref    = list(prises_ref)
        self._prises_lock   = threading.Lock()
        self._state_lock    = threading.Lock()
        self._frame_lock    = threading.Lock()
        self._membres       = {}
        self._suggestions   = {}
        self._last_frame    = None   # dernière frame brute reçue (pour fixer_repere)
        self._last_annotated = None  # dernière frame annotée encodée en JPEG
        self._pose           = AsyncPoseDetector()
        self._diag_count     = 0  # DEBUG temporaire : compteur pour log throttlé

        ref_data        = preparer_reference(ref_img)
        self._orig_w    = ref_data['orig_w']
        self._orig_h    = ref_data['orig_h']
        self._hworker   = HomographyWorker(ref_data)

    def set_prises(self, prises_ref):
        with self._prises_lock:
            self._prises_ref = list(prises_ref)

    def get_state(self):
        with self._state_lock:
            return dict(self._membres), dict(self._suggestions)

    def process(self, frame):
        """Traite une frame brute (BGR) reçue du navigateur et retourne la
        frame annotée (squelette, prises, zone, flèches de guidage)."""
        live_h, live_w = frame.shape[:2]

        with self._frame_lock:
            self._last_frame = frame

        # Soumettre la frame à l'homographie (calcul asynchrone)
        self._hworker.submit(frame)
        H = self._hworker.get_H()

        self._pose.submit(frame)
        landmarks, dimensions = self._pose.get()

        membres      = {k: None for k in _COULEUR_MEMBRE}
        landmarks_px = {}

        if landmarks:
            w, h = dimensions
            # Tous les landmarks dans les bornes de la frame (sans filtre de visibilité)
            for idx in range(11, min(33, len(landmarks))):
                lm = landmarks[idx]
                cx = int(lm["x"] * w)
                cy = int(lm["y"] * h)
                if 0 <= cx < live_w and 0 <= cy < live_h:
                    landmarks_px[idx] = (cx, cy)

            # Squelette
            for pt1, pt2 in LIAISONS_SQUELETTE:
                if pt1 in landmarks_px and pt2 in landmarks_px:
                    cv2.line(frame, landmarks_px[pt1], landmarks_px[pt2], (255, 255, 0), 2)

            # Points corps
            for idx, pos in landmarks_px.items():
                nom = _IDX_MEMBRE.get(idx)
                c   = _COULEUR_MEMBRE[nom] if nom else (0, 255, 255)
                cv2.circle(frame, pos, 5, c, -1)

            # Membres (filtre visibilité > 0.3 pour la navigation uniquement)
            for idx, nom in _IDX_MEMBRE.items():
                if idx in landmarks_px and landmarks[idx].get("visibility", 1.0) > 0.3:
                    membres[nom] = landmarks_px[idx]
                    cv2.circle(frame, landmarks_px[idx], 12, _COULEUR_MEMBRE[nom], -1)

        with self._prises_lock:
            prises_ref = list(self._prises_ref)

        # Projeter les prises de l'espace référence vers la frame live
        prises_live = transformer_prises(
            prises_ref, H, self._orig_w, self._orig_h, live_w, live_h
        )

        # Zone autour du grimpeur, centrée sur les hanches (23/24) — taille
        # proportionnelle à l'écart épaule->cheville (11->27, 12->28), donc
        # adaptative à la distance caméra/grimpeur ; coupée sous les pieds.
        def _valide(idx):
            return idx in landmarks_px and landmarks[idx].get("visibility", 1.0) > 0.3

        hanche_centre = None
        demi_h = DEMI_HAUTEUR_DEFAUT
        demi_l = DEMI_LARGEUR_DEFAUT
        h23 = landmarks_px[23] if _valide(23) else None
        h24 = landmarks_px[24] if _valide(24) else None
        if h23 and h24:
            hanche_centre = (int((h23[0] + h24[0]) / 2), int((h23[1] + h24[1]) / 2))
        elif h23:
            hanche_centre = h23
        elif h24:
            hanche_centre = h24

        if hanche_centre:
            tailles = []
            for epaule, cheville in ((11, 27), (12, 28)):
                if _valide(epaule) and _valide(cheville):
                    tailles.append(abs(landmarks_px[cheville][1] - landmarks_px[epaule][1]))
            if tailles:
                t = max(tailles)
                demi_h = int(t * FACTEUR_DEMI_HAUTEUR)
                demi_l = int(t * FACTEUR_DEMI_LARGEUR)

        chevilles_y = [landmarks_px[i][1] for i in (27, 28) if _valide(i)]
        limite_y_bas = max(chevilles_y) + MARGE_SOUS_PIEDS if chevilles_y else None

        zone_courante = None
        if hanche_centre:
            hx, hy = hanche_centre
            zone_courante = (hx - demi_l, hy - demi_h, hx + demi_l, hy + demi_h)

        prises_visibles = [p for p in prises_live if p['coords'] is not None]

        # N'afficher que les prises dans la zone si le grimpeur est détecté
        if zone_courante is not None:
            zx1, zy1, zx2, zy2 = zone_courante
            prises_affichees = [
                p for p in prises_visibles
                if zx1 <= p['coords'][0] <= zx2 and zy1 <= p['coords'][1] <= zy2
                and (limite_y_bas is None or p['coords'][1] <= limite_y_bas)
            ]
        else:
            prises_affichees = prises_visibles

        for p in prises_affichees:
            px, py = p['coords']
            c = BLEU if p.get('usage', 'Mains+Pieds') == 'Mains+Pieds' else ORANGE
            cv2.circle(frame, (px, py), 6, c, -1)

        # Rectangle pointillé cyan autour du grimpeur
        if zone_courante is not None:
            zx1, zy1, zx2, zy2 = zone_courante
            dash = 10
            for x in range(zx1, zx2, dash * 2):
                cv2.line(frame, (x, zy1), (min(x + dash, zx2), zy1), (0, 255, 255), 1)
                cv2.line(frame, (x, zy2), (min(x + dash, zx2), zy2), (0, 255, 255), 1)
            for y in range(zy1, zy2, dash * 2):
                cv2.line(frame, (zx1, y), (zx1, min(y + dash, zy2)), (0, 255, 255), 1)
                cv2.line(frame, (zx2, y), (zx2, min(y + dash, zy2)), (0, 255, 255), 1)
            cv2.circle(frame, hanche_centre, 5, (0, 255, 255), -1)

        # Flèches de guidance (navigation — sur toutes les prises projetées)
        suggestions = {}
        if any(membres[k] is not None for k in membres):
            suggestions = trouver_prises_par_membre(membres, prises_visibles)
            for nom, cible in suggestions.items():
                if cible and membres[nom]:
                    c = _COULEUR_MEMBRE[nom]
                    cv2.circle(frame, cible, 15, c, 3)
                    cv2.line(frame, membres[nom], cible, c, 2)

        with self._state_lock:
            self._membres     = dict(membres)
            self._suggestions = dict(suggestions)

        # DEBUG temporaire : 1 ligne/seconde environ, à retirer une fois le
        # live diagnostiqué (cf. demande utilisateur "ne détecte pas les
        # prises et la silhouette").
        self._diag_count += 1
        if self._diag_count % 30 == 1:
            print(
                f"[LIVE-DIAG] frame={live_w}x{live_h} "
                f"landmarks={'oui' if landmarks else 'non'} "
                f"landmarks_px={len(landmarks_px)} "
                f"H={'oui' if H is not None else 'non (fallback echelle)'} "
                f"prises_ref={len(prises_ref)} "
                f"prises_visibles={len(prises_visibles)} "
                f"prises_affichees={len(prises_affichees)}"
            )

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        with self._frame_lock:
            self._last_annotated = buf.tobytes()

        return frame

    def get_last_annotated_jpeg(self):
        with self._frame_lock:
            return self._last_annotated

    def fixer_repere(self):
        """
        Ancre les prises à la dernière frame live reçue :
        1. Projette les prises dans la frame live (via H, requis — voir ci-dessous).
        2. Ces positions pixel deviennent les nouvelles coordonnées de référence.
        3. La frame courante devient le nouveau référentiel ORB.
        Retourne le nombre de prises correctement ancrées (0 si aucune frame
        n'est encore arrivée, ou si le suivi par homographie n'a pas encore
        verrouillé — sans H valide, la projection retombe sur une simple mise
        à l'échelle proportionnelle qui suppose un cadrage live identique à la
        photo de référence ; figer le repère sur cette base donnerait des
        prises ancrées n'importe où, de façon irréversible).
        """
        with self._frame_lock:
            frame = self._last_frame
        H = self._hworker.get_H()
        if frame is None or H is None:
            return 0
        live_h, live_w = frame.shape[:2]

        with self._prises_lock:
            prises_ref = list(self._prises_ref)

        prises_live = transformer_prises(
            prises_ref, H, self._orig_w, self._orig_h, live_w, live_h
        )

        new_prises = []
        for p_ref, p_live in zip(prises_ref, prises_live):
            if p_live['coords'] is not None:
                new_prises.append({
                    'ref_cx': p_live['coords'][0],
                    'ref_cy': p_live['coords'][1],
                    'usage':  p_ref['usage'],
                })

        orig_w, orig_h = self._hworker.fixer_repere(frame)
        self._orig_w = orig_w
        self._orig_h = orig_h

        with self._prises_lock:
            self._prises_ref = new_prises

        return len(new_prises)

    def stop(self):
        self._pose.stop()
        self._hworker.stop()
