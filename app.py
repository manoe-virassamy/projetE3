import streamlit as st
st.set_page_config(page_title="BlindClimb Assist", layout="wide")
import cv2
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from detect import detect_image
from detection_task import detect_corps
from path import trouver_prises_par_membre
from Communication2 import MoteurVocal, EcouteurVocal, trouver_reponse
from streamlit_image_coordinates import streamlit_image_coordinates


# ==============================================================================
# TTS / ASR
# ==============================================================================
@st.cache_resource
def get_vocal():
    return MoteurVocal()

@st.cache_resource
def get_ecouteur():
    return EcouteurVocal()


# ==============================================================================
# SERVEUR MJPEG — flux vidéo direct dans le browser, sans passer par Streamlit
# ==============================================================================
MJPEG_PORT = 8765
_latest_jpeg = None
_jpeg_lock   = threading.Lock()


class _ReuseHTTPServer(HTTPServer):
    allow_reuse_address = True


class _MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frm")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                with _jpeg_lock:
                    data = _latest_jpeg
                if data:
                    self.wfile.write(b"--frm\r\nContent-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(data)
                    self.wfile.write(b"\r\n")
                time.sleep(0.033)          # ~30 fps côté serveur
        except Exception:
            pass


@st.cache_resource
def _start_mjpeg_server():
    srv = _ReuseHTTPServer(("localhost", MJPEG_PORT), _MJPEGHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ==============================================================================
# CAPTURE CAMÉRA (thread séparé)
# ==============================================================================
class FreshVideoCapture:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  480)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.ret, self.frame = self.cap.read()
        self.running = True
        threading.Thread(target=self._update, daemon=True).start()

    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.ret, self.frame = ret, frame
            time.sleep(0.01)

    def read(self):
        return self.ret, self.frame

    def release(self):
        self.running = False
        time.sleep(0.1)
        self.cap.release()


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
# WORKER VIDÉO — capture + dessin + écriture MJPEG dans un seul thread
# ==============================================================================
LIAISONS_SQUELETTE = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
]
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


class VideoWorker:
    def __init__(self, prises_coords):
        self._prises       = list(prises_coords)
        self._prises_lock  = threading.Lock()
        self._state_lock   = threading.Lock()
        self._membres      = {}
        self._suggestions  = {}
        self._running      = True
        self._cap          = FreshVideoCapture(0)
        self._pose         = AsyncPoseDetector()
        threading.Thread(target=self._loop, daemon=True).start()

    def set_prises(self, prises_coords):
        with self._prises_lock:
            self._prises = list(prises_coords)

    def get_state(self):
        """Retourne membres et suggestions courants (thread-safe)."""
        with self._state_lock:
            return dict(self._membres), dict(self._suggestions)

    def _loop(self):
        global _latest_jpeg
        while self._running:
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            self._pose.submit(frame)
            landmarks, dimensions = self._pose.get()

            membres = {k: None for k in _COULEUR_MEMBRE}

            if landmarks:
                w, h = dimensions
                # Liaisons squelette
                for pt1, pt2 in LIAISONS_SQUELETTE:
                    if pt1 < len(landmarks) and pt2 < len(landmarks):
                        x1 = int(landmarks[pt1]["x"] * w)
                        y1 = int(landmarks[pt1]["y"] * h)
                        x2 = int(landmarks[pt2]["x"] * w)
                        y2 = int(landmarks[pt2]["y"] * h)
                        if 0 <= x1 < w and 0 <= y1 < h and 0 <= x2 < w and 0 <= y2 < h:
                            cv2.line(frame, (x1, y1), (x2, y2), JAUNE, 3)
                # Points squelette
                for lm in landmarks[11:]:
                    cx, cy = int(lm["x"] * w), int(lm["y"] * h)
                    if 0 <= cx < w and 0 <= cy < h:
                        cv2.circle(frame, (cx, cy), 4, JAUNE, -1)
                # Mains : 15 = gauche, 16 = droite
                if len(landmarks) > 16:
                    xd, yd = int(landmarks[16]["x"] * w), int(landmarks[16]["y"] * h)
                    xg, yg = int(landmarks[15]["x"] * w), int(landmarks[15]["y"] * h)
                    if 0 <= xd < w and 0 <= yd < h:
                        membres['main_droite'] = (xd, yd)
                        cv2.circle(frame, (xd, yd), 12, JAUNE, -1)
                    if 0 <= xg < w and 0 <= yg < h:
                        membres['main_gauche'] = (xg, yg)
                        cv2.circle(frame, (xg, yg), 12, CYAN, -1)
                # Pieds : 27 = gauche, 28 = droite
                if len(landmarks) > 28:
                    xpd, ypd = int(landmarks[28]["x"] * w), int(landmarks[28]["y"] * h)
                    xpg, ypg = int(landmarks[27]["x"] * w), int(landmarks[27]["y"] * h)
                    if 0 <= xpd < w and 0 <= ypd < h:
                        membres['pied_droit'] = (xpd, ypd)
                        cv2.circle(frame, (xpd, ypd), 12, VERT, -1)
                    if 0 <= xpg < w and 0 <= ypg < h:
                        membres['pied_gauche'] = (xpg, ypg)
                        cv2.circle(frame, (xpg, ypg), 12, ORANGE, -1)

            with self._prises_lock:
                prises = list(self._prises)

            # Prises : BLEU = mains, ORANGE = pieds
            for p in prises:
                px, py = p['coords']
                c = BLEU if p.get('usage', 'Mains') == 'Mains' else ORANGE
                cv2.circle(frame, (px, py), 6, c, -1)

            # Flèche de guidance par membre
            suggestions = {}
            if any(membres[k] is not None for k in membres):
                suggestions = trouver_prises_par_membre(membres, prises)
                for nom, cible in suggestions.items():
                    if cible and membres[nom]:
                        c = _COULEUR_MEMBRE[nom]
                        cv2.circle(frame, cible, 15, c, 3)
                        cv2.line(frame, membres[nom], cible, c, 2)

            with self._state_lock:
                self._membres     = dict(membres)
                self._suggestions = dict(suggestions)

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            with _jpeg_lock:
                _latest_jpeg = buf.tobytes()

            time.sleep(0.001)

    def stop(self):
        self._running = False
        self._cap.release()
        self._pose.stop()


# ==============================================================================
# GUIDANCE VOCALE — construit le texte de direction pour chaque membre
# ==============================================================================
_NOMS_FR = {
    'main_droite': 'main droite',
    'main_gauche': 'main gauche',
    'pied_droit':  'pied droit',
    'pied_gauche': 'pied gauche',
}

def _compter_prises_restantes(worker, prises_session, img_h):
    if not prises_session:
        return "Aucune prise détectée. Lancez d'abord la détection sur une image."

    total = len(prises_session)

    if not worker or not st.session_state.live_actif:
        return (f"Il y a {total} prise{'s' if total > 1 else ''} sur ce mur. "
                "Activez le mode live pour que je repère votre position.")

    membres, _ = worker.get_state()
    ys = [pos[1] for pos in membres.values() if pos is not None]
    if not ys:
        return (f"Je ne détecte pas votre silhouette. "
                f"Il y a {total} prise{'s' if total > 1 else ''} au total.")

    # Position normalisée du point le plus haut du grimpeur dans la vidéo (0=sommet)
    y_norm = min(ys) / 360.0
    h_img  = img_h or 360

    # Prises dont le centre est au-dessus du grimpeur (y normalisé plus petit)
    restantes = sum(
        1 for p in prises_session
        if (p["coords"][1] + p["coords"][3]) / 2 / h_img < y_norm
    )
    franchies = total - restantes

    if restantes == 0:
        return f"Bravo ! Vous avez atteint le sommet — {franchies} prise{'s' if franchies > 1 else ''} franchie{'s' if franchies > 1 else ''}."
    return (f"Il reste {restantes} prise{'s' if restantes > 1 else ''} avant le sommet "
            f"({franchies} déjà franchie{'s' if franchies > 1 else ''} sur {total}).")


def _generer_guidance(worker):
    membres, suggestions = worker.get_state()
    if not any(membres.values()):
        return "Aucune silhouette détectée. Placez-vous devant la caméra."

    parties = []
    for membre, cible in suggestions.items():
        nom = _NOMS_FR[membre]
        if cible is None:
            parties.append(f"{nom} : aucune prise à portée")
            continue
        pos = membres.get(membre)
        if pos:
            dx = cible[0] - pos[0]
            dy = cible[1] - pos[1]
            dirs = []
            if abs(dy) > 25:
                dirs.append("en haut" if dy < 0 else "en bas")
            if abs(dx) > 25:
                dirs.append("à droite" if dx > 0 else "à gauche")
            direction = " et ".join(dirs) if dirs else "juste devant"
            import math
            dist_px = math.hypot(dx, dy)
            proximite = "très proche" if dist_px < 80 else ("à portée" if dist_px < 160 else "un peu loin")
            parties.append(f"{nom} : prise {direction}, {proximite}")
        else:
            parties.append(f"{nom} : prise détectée")

    return ". ".join(parties) + "."


# ==============================================================================
# INTERFACE PRINCIPALE STREAMLIT
# ==============================================================================
st.title("BlindClimb Assist")

if "message" in st.session_state:
    st.success(st.session_state.message)
    del st.session_state.message

if "result"          not in st.session_state: st.session_state.result          = None
if "prises"          not in st.session_state: st.session_state.prises          = None
if "original_prises" not in st.session_state: st.session_state.original_prises = None
if "live_actif"      not in st.session_state: st.session_state.live_actif      = False
if "video_worker"    not in st.session_state: st.session_state.video_worker    = None
if "chat_historique"      not in st.session_state: st.session_state.chat_historique      = []
if "img_h"               not in st.session_state: st.session_state.img_h               = None
if "selected_prise_index" not in st.session_state: st.session_state.selected_prise_index = 0

# ==============================================================================
# SECTION LIVE — pleine largeur
# ==============================================================================
st.markdown("---")
st.markdown("### 📷 Mode Flux Live")

if st.session_state.prises:
    live_clique = st.checkbox("Activer le mode live vidéo",
                              value=st.session_state.live_actif)

    if live_clique != st.session_state.live_actif:
        st.session_state.live_actif = live_clique
        if live_clique:
            prises_info = [
                {
                    'coords': (int((p["coords"][0] + p["coords"][2]) / 2),
                               int((p["coords"][1] + p["coords"][3]) / 2)),
                    'usage':  p.get("usage", "Mains"),
                }
                for p in st.session_state.prises
            ]
            _start_mjpeg_server()
            st.session_state.video_worker = VideoWorker(prises_info)
        else:
            if st.session_state.video_worker is not None:
                st.session_state.video_worker.stop()
            st.session_state.video_worker = None
        st.rerun()

    if st.session_state.live_actif:
        if st.session_state.video_worker is not None:
            prises_info = [
                {
                    'coords': (int((p["coords"][0] + p["coords"][2]) / 2),
                               int((p["coords"][1] + p["coords"][3]) / 2)),
                    'usage':  p.get("usage", "Mains"),
                }
                for p in st.session_state.prises
            ]
            st.session_state.video_worker.set_prises(prises_info)

        st.components.v1.html(
            f"""
            <div id="videoWrap" style="position:relative;background:#111;border-radius:12px;
                        overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.5);">
              <img id="liveImg" src="http://localhost:{MJPEG_PORT}"
                   style="width:100%;display:block;">
              <button onclick="
                var el = document.getElementById('videoWrap');
                if (el.requestFullscreen)       el.requestFullscreen();
                else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
              " style="position:absolute;top:10px;right:10px;
                       background:rgba(0,0,0,0.55);color:#fff;
                       border:1px solid rgba(255,255,255,0.4);border-radius:8px;
                       padding:6px 14px;cursor:pointer;font-size:14px;
                       backdrop-filter:blur(4px);">
                ⛶ Plein écran
              </button>
            </div>
            """,
            height=700,
        )

        # Légende + bouton Guider
        leg_col, btn_col = st.columns([4, 1])
        with leg_col:
            st.markdown(
                "<div style='display:flex;flex-wrap:wrap;gap:18px;font-size:13px;padding-top:4px;'>"
                "<span>🟡 Main droite</span>"
                "<span>🩵 Main gauche</span>"
                "<span>🟢 Pied droit</span>"
                "<span>🟠 Pied gauche</span>"
                "<span style='opacity:.6'>● prise mains &nbsp; ● prise pieds</span>"
                "</div>",
                unsafe_allow_html=True,
            )
        with btn_col:
            if st.button("🔊 Guider", use_container_width=True):
                texte = _generer_guidance(st.session_state.video_worker)
                st.session_state.chat_historique.append(
                    {"role": "assistant", "content": texte}
                )
                threading.Thread(target=get_vocal().dire, args=(texte,), daemon=True).start()
                st.rerun()
else:
    st.checkbox("Activer le mode live vidéo", disabled=True,
                help="Lancez d'abord la détection sur une image fixe.")

# ==============================================================================
# SECTION ASSISTANT — pleine largeur, en dessous
# ==============================================================================
st.markdown("---")
st.markdown("### 🎤 Assistant vocal escalade")

vocal    = get_vocal()
ecouteur = get_ecouteur()

col_hist, col_form = st.columns([3, 2])

with col_hist:
    if not ecouteur.disponible:
        st.info("Bouton 'Parler' désactivé — `pip install SpeechRecognition pyaudio`")
    with st.container(height=420):
        for msg in st.session_state.chat_historique:
            st.chat_message(msg["role"]).write(msg["content"])

with col_form:
    audio_actif = st.toggle("Réponses audio", value=True)
    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("chat_form", clear_on_submit=True):
        question = st.text_area(
            "Votre question :",
            placeholder="Ex : comment sécuriser une chute ?",
            height=120,
        )
        c1, c2 = st.columns(2)
        with c1:
            submit_text  = st.form_submit_button("📨 Envoyer",  use_container_width=True)
        with c2:
            submit_voice = st.form_submit_button("🎙️ Parler",
                                                  use_container_width=True,
                                                  disabled=not ecouteur.disponible)

question_finale = None
if submit_text and question:
    question_finale = question.strip()
elif submit_voice:
    with st.spinner("J'écoute... (parlez maintenant)"):
        question_finale = ecouteur.ecouter(vocal)
    if not question_finale:
        msg = ecouteur.derniere_erreur or "Aucune voix détectée, réessayez."
        st.warning(msg)

if question_finale:
    q = question_finale.lower()

    if any(kw in q for kw in ['reste', 'restant', 'sommet', 'combien', 'loin du sommet']):
        reponse = _compter_prises_restantes(
            st.session_state.video_worker,
            st.session_state.prises,
            st.session_state.img_h,
        )
    elif any(kw in q for kw in ['prochaine', 'suivante', 'accroché', 'accroch',
                                  'quelle prise', 'guide', 'guider', 'dois-je prendre']):
        if st.session_state.video_worker and st.session_state.live_actif:
            reponse = _generer_guidance(st.session_state.video_worker)
        else:
            reponse = "Activez le mode live pour que je puisse voir votre position et vous guider."
    else:
        reponse = trouver_reponse(question_finale)

    st.session_state.chat_historique.append({"role": "user",      "content": question_finale})
    st.session_state.chat_historique.append({"role": "assistant", "content": reponse})
    if audio_actif:
        threading.Thread(target=vocal.dire, args=(reponse,), daemon=True).start()
    st.rerun()

st.markdown("---")

# ==============================================================================
# UPLOAD + DÉTECTION
# ==============================================================================
uploaded_file = st.file_uploader("Choisissez une image du mur d'escalade",
                                  type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tfile.write(uploaded_file.read())
    tfile.flush()

    st.image(uploaded_file, caption="Image originale du mur")

    if st.button("Lancer la détection des prises"):
        result, prises = detect_image(tfile.name)
        st.session_state.result          = result
        st.session_state.prises          = prises
        st.session_state.original_prises = [p.copy() for p in prises]
        st.session_state.img_h           = result.shape[0]
        st.rerun()

# ==============================================================================
# CARTOGRAPHIE INTERACTIVE + MODIFICATION DES PRISES
# ==============================================================================
if st.session_state.result is not None:
    st.markdown("---")
    st.markdown("### 🗺️ Cartographie du mur")

    if st.session_state.prises:
        # ── Construire l'image de la carte avec tous les marqueurs ──────────────
        img_map = st.session_state.result.copy()
        idx_sel = min(st.session_state.selected_prise_index, len(st.session_state.prises) - 1)

        for i, p in enumerate(st.session_state.prises):
            x1, y1, x2, y2 = map(int, p["coords"])
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

            if i == idx_sel:
                cv2.rectangle(img_map, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (255, 255, 255), 3)
                cv2.rectangle(img_map, (x1, y1), (x2, y2), (0, 0, 230), 3)
            else:
                couleur = (0, 190, 0) if p.get("usage") == "Mains" else (0, 140, 255)
                cv2.rectangle(img_map, (x1, y1), (x2, y2), couleur, 2)

            txt_color = (230, 100, 0) if i == idx_sel else (255, 255, 255)
            cv2.putText(img_map, str(p["id"]),
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, txt_color, 2)

        img_rgb = cv2.cvtColor(img_map, cv2.COLOR_BGR2RGB)

        # ── Légende ─────────────────────────────────────────────────────────────
        st.markdown(
            "<div style='font-size:13px;margin-bottom:6px;'>"
            "🟢 Prise de mains &nbsp;&nbsp; 🟠 Prise de pieds &nbsp;&nbsp; "
            "🔵 Sélectionnée — cliquez sur une prise pour la sélectionner</div>",
            unsafe_allow_html=True,
        )

        # ── Carte cliquable ──────────────────────────────────────────────────────
        col_map, col_detail = st.columns([3, 2])

        with col_map:
            click = streamlit_image_coordinates(img_rgb, key="wall_map")
            if click is not None:
                cx_c, cy_c = click["x"], click["y"]
                best, best_d = 0, float("inf")
                for i, p in enumerate(st.session_state.prises):
                    x1, y1, x2, y2 = map(int, p["coords"])
                    d = ((((x1+x2)//2) - cx_c)**2 + (((y1+y2)//2) - cy_c)**2) ** 0.5
                    if d < best_d:
                        best_d, best = d, i
                if best != idx_sel:
                    st.session_state.selected_prise_index = best
                    st.rerun()

        # ── Panneau de détail / édition ──────────────────────────────────────────
        with col_detail:
            options = [f"Prise {p['id']}  ({p.get('usage','?')}, score {p['score']:.2f})"
                       for p in st.session_state.prises]
            selected = st.selectbox("Sélection :", options, index=idx_sel)
            index    = options.index(selected)
            if index != idx_sel:
                st.session_state.selected_prise_index = index
                st.rerun()

            p = st.session_state.prises[index]

            st.markdown(f"**Prise {p['id']}**")
            st.write("Couleur :", p["couleur"])
            st.write("Taille  :", p["taille"], "px²")
            st.write("Usage   :", p.get("usage", "Inconnu"))

            if st.button("🗑️ Supprimer cette prise", use_container_width=True, type="primary"):
                st.session_state.prises.pop(index)
                for i, pr in enumerate(st.session_state.prises):
                    pr["id"] = i + 1
                st.session_state.selected_prise_index = max(0, index - 1)
                st.session_state.message = "Prise supprimée !"
                st.rerun()

            with st.expander("Modifier cette prise"):
                new_couleur = st.text_input("Couleur :", value=p["couleur"], key="ec")
                new_taille  = st.number_input("Taille (px²) :", value=int(p["taille"]), key="et")
                new_usage   = st.selectbox("Usage :", ["Mains", "Pieds"], key="eu",
                                           index=0 if p.get("usage", "Mains") == "Mains" else 1)
                x1, y1, x2, y2 = p["coords"]
                new_x1 = st.number_input("x1 :", value=int(x1), key="ex1")
                new_y1 = st.number_input("y1 :", value=int(y1), key="ey1")
                new_x2 = st.number_input("x2 :", value=int(x2), key="ex2")
                new_y2 = st.number_input("y2 :", value=int(y2), key="ey2")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("💾 Valider", use_container_width=True):
                        st.session_state.prises[index].update({
                            "couleur": new_couleur, "taille": new_taille,
                            "usage": new_usage,
                            "coords": (new_x1, new_y1, new_x2, new_y2),
                        })
                        st.session_state.message = "Modifications enregistrées !"
                        st.rerun()
                with c2:
                    if st.button("↩ Reset", use_container_width=True):
                        st.session_state.prises[index] = st.session_state.original_prises[index].copy()
                        st.session_state.message = "Prise réinitialisée !"
                        st.rerun()
    else:
        st.write("Aucune prise détectée.")

# ==============================================================================
# AJOUT MANUEL D'UNE PRISE
# ==============================================================================
if st.session_state.result is not None and st.session_state.prises is not None:
    st.markdown("---")
    st.subheader("Ajouter une nouvelle prise")

    add_x1 = st.number_input("x1 nouvelle prise:", key="add_x1")
    add_y1 = st.number_input("y1 nouvelle prise:", key="add_y1")
    add_x2 = st.number_input("x2 nouvelle prise:", value=50, key="add_x2")
    add_y2 = st.number_input("y2 nouvelle prise:", value=0,  key="add_y2")

    x1 = int(min(add_x1, add_x2))
    y1 = int(min(add_y1, add_y2))
    x2 = int(max(add_x1, add_x2))
    y2 = int(max(add_y1, add_y2))

    add_couleur = st.text_input("Couleur nouvelle prise:", value="inconnue", key="add_couleur")
    add_taille  = st.number_input("Taille nouvelle prise (pixels²):", value=100, key="add_taille")
    add_usage   = st.selectbox("Usage nouvelle prise:", ["Mains", "Pieds"], key="add_usage")

    if st.button("Ajouter la prise"):
        new_id    = len(st.session_state.prises) + 1
        new_prise = {
            "id":      new_id,
            "score":   1.0,
            "coords":  (x1, y1, x2, y2),
            "couleur": add_couleur,
            "taille":  int(add_taille),
            "usage":   add_usage,
        }
        st.session_state.prises.append(new_prise)
        st.session_state.message = f"Prise {new_id} ajoutée avec succès !"
        st.rerun()
