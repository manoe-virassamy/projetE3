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
import socket
import struct
import threading
import time

import cv2

from detectionV1 import detect_corps
from homographie import HomographyWorker, transformer_prises, preparer_reference
from path import trouver_prises_par_membre


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

# Le diagnostic [NET-DIAG] a confirme que le STUN UDP marche depuis
# Streamlit Cloud (donc l'UDP sortant n'est pas bloque), mais le crash aioice
# (Transaction.__retry() sur un transport deja ferme) persiste meme apres
# avoir corrige le TURN et fixe Python 3.12 — ce n'etait donc ni un probleme
# de TURN injoignable, ni de version Python. Hypothese restante, coherente
# avec "STUN brut reussit mais l'ICE complete echoue quand meme" : un NAT
# symetrique cote Streamlit Cloud, qui rend toute tentative de connexion P2P
# directe vouee a l'echec (l'adresse reflexive vue par le serveur STUN ne
# correspond pas a celle utilisee vers le vrai pair). Dans ce cas, seul un
# relai TURN peut fonctionner. On force donc iceTransportPolicy="relay" —
# deja tente avant, mais a l'epoque le seul TURN configure
# (openrelay.metered.ca:443) etait injoignable, donc forcer le relais ne
# laissait alors aucune voie possible. Le TURN actuel
# (global.relay.metered.ca) est confirme joignable sur 80/443/3478, donc ca
# vaut le coup de retester avec le relais force.
RTC_CONFIGURATION = {
    "iceTransportPolicy": "relay",
    "iceServers": [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {
            "urls": [
                "turn:global.relay.metered.ca:443?transport=tcp",
                "turns:global.relay.metered.ca:443?transport=tcp",
                "turn:global.relay.metered.ca:80?transport=tcp",
            ],
            "username": "openrelayproject",
            "credential": "openrelayproject",
        },
    ],
}

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
