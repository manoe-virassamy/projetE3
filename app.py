import streamlit as st
st.set_page_config(page_title="BlindClimb Assist", layout="wide", page_icon="Logo.jpg")


@st.cache_resource
def _patch_pwa_une_fois():
    try:
        from patch_streamlit_pwa import patcher
        patcher()
    except Exception as e:
        print(f"[PWA] Patch index.html ignore : {e}")
    return True


_patch_pwa_une_fois()

import av
import cv2
import numpy as np
import tempfile
import json
from detect import detect_image
from communication import EcouteurVocal, trouver_reponse
from streamlit_image_coordinates import streamlit_image_coordinates
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from live_webrtc import LiveProcessor, RTC_CONFIGURATION, MEDIA_CONSTRAINTS
from ui_common import (
    inject_global_css, inject_pwa_tags, gate_username,
    render_banner, render_sidebar_logo, render_section_nav, render_page_nav,
    couleur_swatch as _couleur_swatch,
    score_bar as _score_bar,
    badge as _badge,
)
from voice_browser import speak_browser, speak_button_html


# ==============================================================================
# TTS / ASR
# ==============================================================================
@st.cache_resource
def get_ecouteur():
    return EcouteurVocal()


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
    prenom = st.session_state.get("username", "")
    appel  = f" {prenom}" if prenom else ""

    if not prises_session:
        return "Aucune prise détectée. Lancez d'abord la détection sur une image."

    total = len(prises_session)

    if not worker or not st.session_state.live_actif:
        return (f"Il y a {total} prise{'s' if total > 1 else ''} sur ce mur. "
                "Activez le mode live pour que je repère votre position.")

    membres, _ = worker.get_state()
    ys = [pos[1] for pos in membres.values() if pos is not None]
    if not ys:
        return (f"Je ne détecte pas votre silhouette{appel}. "
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
        return f"Bravo{appel} ! Vous avez atteint le sommet — {franchies} prise{'s' if franchies > 1 else ''} franchie{'s' if franchies > 1 else ''}."
    return (f"Courage{appel} ! Il reste {restantes} prise{'s' if restantes > 1 else ''} avant le sommet "
            f"({franchies} déjà franchie{'s' if franchies > 1 else ''} sur {total}).")


def _generer_guidance(worker):
    prenom = st.session_state.get("username", "")
    appel  = f" {prenom}" if prenom else ""

    membres, suggestions = worker.get_state()
    if not any(membres.values()):
        return f"Aucune silhouette détectée{appel}. Placez-vous devant la caméra."

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
inject_global_css()
inject_pwa_tags()
gate_username()
render_banner()

if "message" in st.session_state:
    st.toast(st.session_state.message, icon="✅")
    del st.session_state.message

if "result"          not in st.session_state: st.session_state.result          = None
if "prises"          not in st.session_state: st.session_state.prises          = None
if "original_prises" not in st.session_state: st.session_state.original_prises = None
if "live_actif"      not in st.session_state: st.session_state.live_actif      = False
if "live_processor"  not in st.session_state: st.session_state.live_processor  = None
if "chat_historique"      not in st.session_state: st.session_state.chat_historique      = []
if "img_h"               not in st.session_state: st.session_state.img_h               = None
if "selected_prise_index" not in st.session_state: st.session_state.selected_prise_index = 0
if "photo_en_attente"    not in st.session_state: st.session_state.photo_en_attente    = None
if "crop_p1"             not in st.session_state: st.session_state.crop_p1             = None
if "crop_p2"             not in st.session_state: st.session_state.crop_p2             = None
if "crop_step"           not in st.session_state: st.session_state.crop_step           = 0
if "ref_img"             not in st.session_state: st.session_state.ref_img             = None
if "voice_turn"          not in st.session_state: st.session_state.voice_turn          = 0
if "pending_speech"      not in st.session_state: st.session_state.pending_speech      = None

# ── Lecture vocale en attente (voir section 4 du plan : on évite d'appeler
#    speak_browser() juste avant un st.rerun(), qui coupe le script avant que
#    l'iframe ait eu le temps de charger et d'exécuter le speechSynthesis) ──
if st.session_state.pending_speech:
    speak_browser(st.session_state.pending_speech)
    st.session_state.pending_speech = None

# ── Badges de statut ────────────────────────────────────────────────────────
_nb_prises  = len(st.session_state.prises) if st.session_state.prises else 0
_live_on    = st.session_state.live_actif
_micro_ok   = get_ecouteur().disponible_navigateur

_badges_html = (
    _badge("Live actif",   "#d4edda", "#155724", "#28a745") if _live_on  else
    _badge("Live inactif", "#f8d7da", "#721c24", "#dc3545")
) + (
    _badge(f"{_nb_prises} prise{'s' if _nb_prises != 1 else ''} détectée{'s' if _nb_prises != 1 else ''}",
           "#fdf8e8", "#7A5C00", "#C9A020")
) + (
    _badge("Micro disponible",    "#d4edda", "#155724", "#28a745") if _micro_ok else
    _badge("Micro indisponible",  "#fff3cd", "#856404", "#ffc107")
)

st.markdown(
    f"<div style='margin-bottom:0.5rem;'>{_badges_html}</div>",
    unsafe_allow_html=True,
)

# ==============================================================================
# SOURCE IMAGE — fichier ou capture caméra
# ==============================================================================
st.markdown('<div id="sec-source"></div>', unsafe_allow_html=True)
st.markdown("---")

def _lancer_detection(image_bytes: bytes):
    """Sauvegarde les bytes dans un fichier temp, lance YOLO et met à jour le state."""
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tfile.write(image_bytes)
    tfile.flush()
    conf = st.session_state.get("conf_seuil", 0.1)
    result, prises = detect_image(tfile.name, conf=conf)
    st.session_state.result               = result
    st.session_state.ref_img              = result.copy()
    st.session_state.prises               = prises
    st.session_state.original_prises      = [p.copy() for p in prises]
    st.session_state.img_h                = result.shape[0]
    st.session_state.selected_prise_index = 0


if st.session_state.result is None and st.session_state.photo_en_attente is None:
    st.markdown("""
    <style>
    .bca-empty {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background: #ffffff;
        border: 2px dashed #C9A020;
        border-radius: 16px;
        padding: 2.8rem 2rem;
        margin-bottom: 1.2rem;
        text-align: center;
    }}
    .bca-empty h4 {{
        color: #111111;
        font-size: 1.2rem;
        font-weight: 700;
        margin: 0 0 0.5rem 0;
        border: none; background: none; box-shadow: none; padding: 0;
    }}
    .bca-empty p {{ color: #666; font-size: 0.92rem; margin: 0; }}
    @media (prefers-color-scheme: dark) {{
        .bca-empty {{ background: #1a1a16 !important; }}
        .bca-empty h4 {{ color: #e8e0c8 !important; }}
        .bca-empty p {{ color: #999 !important; }}
    }}
    </style>
    <div class="bca-empty">
      <h4>📷 Chargez une photo du mur pour commencer</h4>
      <p>Utilisez l'onglet ci-dessous pour importer un fichier<br>ou prendre une photo avec votre caméra.</p>
    </div>
    """, unsafe_allow_html=True)

tab_fichier, tab_camera = st.tabs(["📁 Choisir un fichier", "📸 Prendre une photo du mur"])

def _stocker_photo(image_bytes: bytes):
    """Stocke la photo pour recadrage avant détection."""
    st.session_state.photo_en_attente = image_bytes
    st.session_state.crop_p1   = None
    st.session_state.crop_p2   = None
    st.session_state.crop_step = 0

with tab_fichier:
    uploaded_file = st.file_uploader("Image du mur d'escalade",
                                     type=["jpg", "jpeg", "png"],
                                     label_visibility="collapsed")
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Image chargée", use_container_width=True)
        if st.button("✂️ Utiliser cette image", key="btn_use_file",
                     use_container_width=True, type="primary"):
            _stocker_photo(uploaded_file.getvalue())
            st.rerun()

with tab_camera:
    if st.session_state.live_actif:
        st.info("Le live est actif. Désactivez-le pour prendre une nouvelle photo, "
                "ou capturez la frame courante ci-dessous.")
        _snap_preview = (
            st.session_state.live_processor.get_last_annotated_jpeg()
            if st.session_state.live_processor is not None else None
        )
        if _snap_preview is not None:
            st.image(_snap_preview, caption="Frame courante", use_container_width=True)
            if st.button("📷 Utiliser cette frame", use_container_width=True, type="primary"):
                _stocker_photo(_snap_preview)
                st.rerun()
        else:
            st.info("Patientez — en attente de la première frame de la caméra…")
    else:
        photo = st.camera_input("Prenez une photo du mur", label_visibility="collapsed")
        if photo is not None:
            if st.button("✂️ Utiliser cette photo", key="btn_use_cam",
                         use_container_width=True, type="primary"):
                _stocker_photo(photo.getvalue())
                st.rerun()

# ==============================================================================
# RECADRAGE INTERACTIF
# ==============================================================================
if st.session_state.photo_en_attente is not None:
    st.markdown('<div id="sec-recadrage"></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### ✂️ Recadrage (optionnel)")

    img_brut = cv2.imdecode(
        np.frombuffer(st.session_state.photo_en_attente, np.uint8),
        cv2.IMREAD_COLOR,
    )
    ih, iw = img_brut.shape[:2]
    p1 = st.session_state.crop_p1

    if p1 is None:
        # ── Étape 1 : clic pour placer le premier coin ───────────────────────────
        st.info("Cliquez sur le **premier coin** de la zone à recadrer.")
        img_rgb = cv2.cvtColor(img_brut, cv2.COLOR_BGR2RGB)
        # Même limitation que pour la carte cliquable plus bas : une photo de
        # téléphone en pleine résolution fait planter le rendu du composant
        # dans Safari iOS (espace vide, sans erreur) — on réduit l'image
        # envoyée et on remet les coordonnées du clic à l'échelle d'origine.
        _CROP_LARGEUR_MAX = 1000
        _echelle_crop = min(1.0, _CROP_LARGEUR_MAX / iw)
        if _echelle_crop < 1.0:
            img_rgb_affichee = cv2.resize(
                img_rgb,
                (int(iw * _echelle_crop), int(ih * _echelle_crop)),
                interpolation=cv2.INTER_AREA,
            )
        else:
            img_rgb_affichee = img_rgb
        click = streamlit_image_coordinates(img_rgb_affichee, key="crop_click_p1", use_column_width="always")
        if click is not None:
            # Le composant renvoie le clic dans la taille affichée à l'écran
            # (CSS), pas dans la taille de l'image envoyée — on remonte à
            # l'échelle d'origine via click["width"]/["height"] (taille
            # réellement rendue), pas via notre propre facteur de réduction.
            st.session_state.crop_p1 = (
                int(click["x"] * (iw / click["width"])),
                int(click["y"] * (ih / click["height"])),
            )
            st.session_state.crop_step = 1
            st.rerun()

        col_skip, col_ann = st.columns(2)
        with col_skip:
            if st.button("🔍 Détecter sans recadrage", use_container_width=True):
                with st.spinner("🔍 Analyse du mur en cours — détection des prises…"):
                    _lancer_detection(st.session_state.photo_en_attente)
                st.session_state.photo_en_attente = None
                st.session_state.crop_step = 0
                st.rerun()
        with col_ann:
            if st.button("✕ Annuler", use_container_width=True):
                st.session_state.photo_en_attente = None
                st.session_state.crop_step = 0
                st.rerun()

    else:
        # ── Étape 2 : sliders pour ajuster le coin opposé ───────────────────────
        # Les sliders sont initialisés au bord opposé de l'image par rapport à p1
        default_x2 = iw if p1[0] <= iw // 2 else 0
        default_y2 = ih if p1[1] <= ih // 2 else 0

        # Clés incluant p1 → reset automatique si p1 change
        sk = f"{p1[0]}_{p1[1]}"
        col_sl1, col_sl2 = st.columns(2)
        with col_sl1:
            x2 = st.slider("← → Bord horizontal", 0, iw, default_x2, key=f"cx2_{sk}")
        with col_sl2:
            y2 = st.slider("↑ ↓ Bord vertical",   0, ih, default_y2, key=f"cy2_{sk}")

        # Rectangle normalisé (p1 peut être n'importe quel coin)
        x1c, y1c = min(p1[0], x2), min(p1[1], y2)
        x2c, y2c = max(p1[0], x2), max(p1[1], y2)

        # Aperçu avec rectangle + poignées de coin
        img_disp = img_brut.copy()
        cv2.rectangle(img_disp, (x1c, y1c), (x2c, y2c), (0, 220, 0), 3)
        cv2.rectangle(img_disp, (x1c-1, y1c-1), (x2c+1, y2c+1), (255, 255, 255), 1)
        for corner in [(x1c, y1c), (x2c, y1c), (x2c, y2c), (x1c, y2c)]:
            cv2.circle(img_disp, corner, 7, (255, 255, 255), -1)
            cv2.circle(img_disp, corner, 5, (0, 200, 0),     -1)
        st.image(cv2.cvtColor(img_disp, cv2.COLOR_BGR2RGB), use_container_width=True)
        st.caption(f"Zone sélectionnée : {x2c - x1c} × {y2c - y1c} px")

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("🔍 Détecter avec recadrage", use_container_width=True, type="primary"):
                recadree = img_brut[y1c:y2c, x1c:x2c]
                _, buf = cv2.imencode(".jpg", recadree)
                with st.spinner("🔍 Analyse du mur en cours — détection des prises…"):
                    _lancer_detection(buf.tobytes())
                st.session_state.photo_en_attente = None
                st.session_state.crop_p1 = None
                st.session_state.crop_step = 0
                st.rerun()
        with c2:
            if st.button("↩ Replacer le 1er coin", use_container_width=True):
                st.session_state.crop_p1   = None
                st.session_state.crop_step = 0
                st.rerun()
        with c3:
            if st.button("🔍 Détecter sans recadrage", use_container_width=True):
                with st.spinner("🔍 Analyse du mur en cours — détection des prises…"):
                    _lancer_detection(st.session_state.photo_en_attente)
                st.session_state.photo_en_attente = None
                st.session_state.crop_p1 = None
                st.session_state.crop_step = 0
                st.rerun()

# ==============================================================================
# CARTOGRAPHIE INTERACTIVE + MODIFICATION DES PRISES
# ==============================================================================
if st.session_state.result is not None:
    st.markdown('<div id="sec-cartographie"></div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 🗺️ Cartographie du mur")

    if st.session_state.prises:
        # ── Métriques résumées ───────────────────────────────────────────────────
        _total   = len(st.session_state.prises)
        _mains   = sum(1 for p in st.session_state.prises if p.get("usage") == "Mains+Pieds")
        _pieds   = _total - _mains
        _score_m = (sum(p["score"] for p in st.session_state.prises) / _total) if _total else 0

        def _carte_metrique(icone, valeur, label, couleur_fond, couleur_val):
            return f"""
            <div style="background:{couleur_fond};border-radius:12px;padding:1rem 1.2rem;
                        display:flex;align-items:center;gap:0.9rem;
                        box-shadow:0 2px 8px rgba(0,0,0,0.07);">
              <div style="font-size:1.9rem;line-height:1;">{icone}</div>
              <div>
                <div style="font-size:1.6rem;font-weight:800;color:{couleur_val};
                            line-height:1.1;">{valeur}</div>
                <div style="font-size:0.78rem;color:#555;font-weight:500;
                            margin-top:2px;letter-spacing:0.02em;">{label}</div>
              </div>
            </div>"""

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.markdown(_carte_metrique("🪨", _total,           "Prises totales",     "#ffffff", "#111111"), unsafe_allow_html=True)
        mc2.markdown(_carte_metrique("🟢", _mains,           "Mains + pieds",      "#f0faf0", "#1a7a1a"), unsafe_allow_html=True)
        mc3.markdown(_carte_metrique("🟠", _pieds,           "Pieds seulement",    "#fff5eb", "#b85c00"), unsafe_allow_html=True)
        mc4.markdown(_carte_metrique("⭐", f"{_score_m:.2f}", "Score moyen YOLO",   "#fdf8e8", "#7A5C00"), unsafe_allow_html=True)
        mc4.markdown(
            f"<div style='padding:0 1.2rem;'>{_score_bar(_score_m, dark=False, show_label=False)}</div>",
            unsafe_allow_html=True,
        )

        # ── Filtre par type + export ─────────────────────────────────────────────
        fcol, ecol1, ecol2 = st.columns([3, 1, 1])
        with fcol:
            filtre = st.radio(
                "Afficher :",
                ["Toutes", "Mains+Pieds", "Pieds"],
                horizontal=True,
                key="filtre_prises",
                label_visibility="collapsed",
            )
        prises_filtrees = [
            p for p in st.session_state.prises
            if filtre == "Toutes" or p.get("usage") == filtre
        ]

        export_data = [
            {k: (list(v) if isinstance(v, tuple) else v)
             for k, v in p.items()}
            for p in st.session_state.prises
        ]
        with ecol1:
            st.download_button(
                "⬇ JSON",
                data=json.dumps(export_data, indent=2, ensure_ascii=False),
                file_name="prises.json",
                mime="application/json",
                use_container_width=True,
            )
        _, png_buf = cv2.imencode(".png", st.session_state.result)
        with ecol2:
            st.download_button(
                "⬇ PNG",
                data=png_buf.tobytes(),
                file_name="mur_annote.png",
                mime="image/png",
                use_container_width=True,
            )

        # ── Réduire d'abord la photo de base, puis dessiner les marqueurs ────────
        # dessus (et non l'inverse) : sur une photo de téléphone en pleine
        # résolution (souvent 3000-4000px de large), des traits dessinés à
        # épaisseur fixe puis réduits à 1000px deviennent quasi invisibles
        # (un trait de 3px à l'échelle d'origine finit à <1px affiché). En
        # dessinant après réduction, l'épaisseur affichée est toujours la
        # même, quelle que soit la résolution de la photo source.
        img_base = st.session_state.result
        _CARTE_LARGEUR_MAX = 1000
        _h_carte, _w_carte = img_base.shape[:2]
        _echelle_carte = min(1.0, _CARTE_LARGEUR_MAX / _w_carte)
        if _echelle_carte < 1.0:
            img_map = cv2.resize(
                img_base,
                (int(_w_carte * _echelle_carte), int(_h_carte * _echelle_carte)),
                interpolation=cv2.INTER_AREA,
            )
        else:
            img_map = img_base.copy()

        idx_sel = min(st.session_state.selected_prise_index, len(st.session_state.prises) - 1)
        id_sel  = st.session_state.prises[idx_sel]["id"]

        for p in prises_filtrees:
            x1, y1, x2, y2 = (round(c * _echelle_carte) for c in p["coords"])
            est_sel = p["id"] == id_sel

            if est_sel:
                cv2.rectangle(img_map, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (255, 255, 255), 4)
                cv2.rectangle(img_map, (x1, y1), (x2, y2), (0, 0, 230), 5)
            else:
                couleur = (0, 190, 0) if p.get("usage") == "Mains+Pieds" else (0, 140, 255)
                cv2.rectangle(img_map, (x1, y1), (x2, y2), couleur, 4)

            txt_color = (230, 100, 0) if est_sel else (255, 255, 255)
            cv2.putText(img_map, str(p["id"]),
                        (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, txt_color, 2)

        img_rgb_affichee = cv2.cvtColor(img_map, cv2.COLOR_BGR2RGB)

        # ── Légende ─────────────────────────────────────────────────────────────
        st.markdown(
            "<div style='font-size:13px;margin-bottom:6px;'>"
            "🟢 Mains + pieds &nbsp;&nbsp; 🟠 Pieds seulement &nbsp;&nbsp; "
            "🔵 Sélectionnée — cliquez sur une prise pour la sélectionner</div>",
            unsafe_allow_html=True,
        )

        # ── Carte cliquable — pleine largeur ────────────────────────────────────
        click = streamlit_image_coordinates(img_rgb_affichee, key="wall_map", use_column_width="always")
        if click is not None:
            # Le composant renvoie le clic dans la taille AFFICHÉE à l'écran
            # (CSS, ex. la largeur de la colonne sur mobile), pas dans la
            # taille de l'image qu'on lui a envoyée — il faut donc se baser
            # sur click["width"]/["height"] (taille réellement rendue) pour
            # remonter à l'échelle de l'image d'origine en pixels, plutôt que
            # sur notre propre facteur de réduction (_echelle_carte), qui ne
            # correspond pas forcément à la taille d'affichage réelle.
            cx_c = click["x"] * (_w_carte / click["width"])
            cy_c = click["y"] * (_h_carte / click["height"])
            # Cherche uniquement parmi les prises affichées sur la carte (le
            # filtre "Mains+Pieds"/"Pieds" peut en masquer certaines) — sinon
            # un clic peut sélectionner une prise filtrée invisible plus
            # proche que la prise visible réellement visée.
            best_id, best_d = None, float("inf")
            for p in prises_filtrees:
                x1, y1, x2, y2 = map(int, p["coords"])
                d = ((((x1+x2)//2) - cx_c)**2 + (((y1+y2)//2) - cy_c)**2) ** 0.5
                if d < best_d:
                    best_d, best_id = d, p["id"]
            if best_id is not None:
                best = next(i for i, p in enumerate(st.session_state.prises) if p["id"] == best_id)
                if best != idx_sel:
                    st.session_state.selected_prise_index = best
                    st.rerun()

    else:
        st.write("Aucune prise détectée.")

# ==============================================================================
# SIDEBAR — navigation + état + prises + à propos
# ==============================================================================
with st.sidebar:
    # ── Logo compact ──────────────────────────────────────────────────────────
    render_sidebar_logo()

    # ── Liens de navigation ────────────────────────────────────────────────────
    render_page_nav("accueil")
    render_section_nav()

    # ── Résumé session ─────────────────────────────────────────────────────────
    _has_image    = st.session_state.get("uploaded_file") is not None or st.session_state.get("result") is not None
    _live_on      = bool(st.session_state.get("live_actif"))
    _nb_prises    = len(st.session_state.get("prises") or [])
    _nb_messages  = len(st.session_state.get("messages") or [])
    _micro_actif  = st.session_state.get("micro_actif", False)

    def _stat_chip(val, label, color="#C9A020"):
        return (f"<div style='text-align:center;background:#1a1a1a;border-radius:8px;"
                f"padding:0.4rem 0.2rem;'>"
                f"<div style='color:{color};font-size:1.1rem;font-weight:800;'>{val}</div>"
                f"<div style='color:rgba(255,255,255,0.45);font-size:0.68rem;'>{label}</div>"
                f"</div>")

    st.markdown(f"""
    <div style='background:#131313;border:1px solid #2a2a2a;border-radius:10px;
                padding:0.7rem 0.9rem;margin-bottom:1rem;'>
      <div style='color:rgba(255,255,255,0.5);font-size:0.72rem;font-weight:600;
                  letter-spacing:.06em;text-transform:uppercase;margin-bottom:0.5rem;'>
        Session
      </div>
      <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.4rem;'>
        {_stat_chip(_nb_prises,   "prises")}
        {_stat_chip(_nb_messages, "échanges")}
        {_stat_chip("🔴" if _live_on else "⚫", "live")}
      </div>
      <div style='margin-top:0.5rem;display:flex;gap:0.4rem;flex-wrap:wrap;'>
        {"<span style='background:#1a3a1a;color:#4ade80;border-radius:12px;padding:2px 8px;font-size:0.72rem;'>🎤 Micro actif</span>" if _micro_actif else ""}
        {"<span style='background:#1a2535;color:#60a5fa;border-radius:12px;padding:2px 8px;font-size:0.72rem;'>📷 Image chargée</span>" if _has_image else ""}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Seuil de confiance YOLO ───────────────────────────────────────────────
    st.markdown("""
    <div style='color:rgba(255,255,255,0.5);font-size:0.72rem;font-weight:600;
                letter-spacing:.06em;text-transform:uppercase;margin-bottom:0.3rem;'>
      Détection YOLO
    </div>
    """, unsafe_allow_html=True)
    conf_val = st.slider(
        "Seuil de confiance",
        min_value=0.05, max_value=0.95, step=0.05,
        value=st.session_state.get("conf_seuil", 0.10),
        format="%.2f",
        help="Valeur basse = plus de prises détectées (mais plus de faux positifs). Relancez la détection pour appliquer.",
        key="conf_seuil",
        label_visibility="collapsed",
    )
    st.caption(f"Seuil actuel : **{conf_val:.2f}** — relancez la détection pour appliquer.")

    st.markdown("---")

    # ── Panneau prises ────────────────────────────────────────────────────────
    st.markdown("""
    <div style='background:linear-gradient(135deg,#0D0D0D,#1a1a1a);
                border-radius:10px;padding:0.8rem 1rem;margin-bottom:1rem;'>
      <span style='color:#fff;font-weight:700;font-size:1rem;'>🧗 Panneau prises</span>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.prises:
        idx_sel_sb = min(st.session_state.selected_prise_index,
                         len(st.session_state.prises) - 1)
        options_sb = [f"Prise {p['id']}  ({p.get('usage','?')}, {p['score']:.2f})"
                      for p in st.session_state.prises]
        selected_sb = st.selectbox("Sélectionner :", options_sb, index=idx_sel_sb)
        index_sb    = options_sb.index(selected_sb)
        if index_sb != idx_sel_sb:
            st.session_state.selected_prise_index = index_sb
            st.rerun()

        p = st.session_state.prises[index_sb]

        st.markdown(f"#### Prise {p['id']}")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(
                f"<div style='font-size:0.8rem;color:rgba(255,255,255,0.5);'>Couleur</div>"
                f"<div style='font-size:1.1rem;font-weight:700;color:rgba(255,255,255,0.9);"
                f"display:flex;align-items:center;gap:6px;margin-top:2px;'>"
                f"{_couleur_swatch(p['couleur'], '14px')} {p['couleur']}</div>",
                unsafe_allow_html=True,
            )
        col_b.metric("Taille",   f"{p['taille']} px²")
        st.markdown(
            f"<span style='background:#fdf8e8;color:#7A5C00;padding:2px 10px;"
            f"border-radius:12px;font-size:0.82rem;font-weight:600;'>"
            f"{p.get('usage','Inconnu')}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(_score_bar(p["score"]), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("🗑️ Supprimer cette prise", use_container_width=True, type="primary"):
            st.session_state.prises.pop(index_sb)
            for i, pr in enumerate(st.session_state.prises):
                pr["id"] = i + 1
            st.session_state.selected_prise_index = max(0, index_sb - 1)
            st.session_state.message = "Prise supprimée !"
            st.rerun()

        with st.expander("✏️ Modifier cette prise"):
            new_couleur = st.text_input("Couleur :", value=p["couleur"], key="ec")
            st.markdown(
                f"{_couleur_swatch(new_couleur, '11px')} "
                f"<span style='font-size:0.78rem;color:rgba(255,255,255,0.5);'>aperçu</span>",
                unsafe_allow_html=True,
            )
            new_taille  = st.number_input("Taille (px²) :", value=int(p["taille"]), key="et")
            new_usage   = st.selectbox("Usage :", ["Mains+Pieds", "Pieds"], key="eu",
                                       index=0 if p.get("usage", "Mains+Pieds") == "Mains+Pieds" else 1)
            x1, y1, x2, y2 = p["coords"]
            new_x1 = st.number_input("x1 :", value=int(x1), key="ex1")
            new_y1 = st.number_input("y1 :", value=int(y1), key="ey1")
            new_x2 = st.number_input("x2 :", value=int(x2), key="ex2")
            new_y2 = st.number_input("y2 :", value=int(y2), key="ey2")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Valider", use_container_width=True):
                    st.session_state.prises[index_sb].update({
                        "couleur": new_couleur, "taille": new_taille,
                        "usage": new_usage,
                        "coords": (new_x1, new_y1, new_x2, new_y2),
                    })
                    st.session_state.message = "Modifications enregistrées !"
                    st.rerun()
            with c2:
                if st.button("↩ Reset", use_container_width=True):
                    st.session_state.prises[index_sb] = st.session_state.original_prises[index_sb].copy()
                    st.session_state.message = "Prise réinitialisée !"
                    st.rerun()

        st.markdown("---")

    if st.session_state.result is not None:
        st.markdown("#### ➕ Ajouter une prise")
        add_x1 = st.number_input("x1 :", key="add_x1")
        add_y1 = st.number_input("y1 :", key="add_y1")
        add_x2 = st.number_input("x2 :", value=50, key="add_x2")
        add_y2 = st.number_input("y2 :", value=0,  key="add_y2")
        add_couleur = st.text_input("Couleur :", value="Inconnue", key="add_couleur")
        st.markdown(
            f"{_couleur_swatch(add_couleur, '11px')} "
            f"<span style='font-size:0.78rem;color:rgba(255,255,255,0.5);'>aperçu</span>",
            unsafe_allow_html=True,
        )
        add_taille  = st.number_input("Taille (px²) :", value=100, key="add_taille")
        add_usage   = st.selectbox("Usage :", ["Mains+Pieds", "Pieds"], key="add_usage")
        if st.button("Ajouter la prise", use_container_width=True, type="primary"):
            x1 = int(min(add_x1, add_x2))
            y1 = int(min(add_y1, add_y2))
            x2 = int(max(add_x1, add_x2))
            y2 = int(max(add_y1, add_y2))
            new_id = len(st.session_state.prises) + 1 if st.session_state.prises else 1
            st.session_state.prises = st.session_state.prises or []
            st.session_state.prises.append({
                "id": new_id, "score": 1.0,
                "coords": (x1, y1, x2, y2),
                "couleur": add_couleur,
                "taille": int(add_taille),
                "usage": add_usage,
            })
            st.session_state.message = f"Prise {new_id} ajoutée avec succès !"
            st.rerun()
    else:
        st.info("Chargez une image pour gérer les prises.")

# ==============================================================================
# SECTION LIVE — pleine largeur
# ==============================================================================
st.markdown('<div id="sec-live"></div>', unsafe_allow_html=True)
st.markdown("---")
st.markdown("### 📷 Mode Flux Live")

if st.session_state.prises:
    live_clique = st.checkbox("▶ Activer le mode live vidéo",
                              value=st.session_state.live_actif)

    if live_clique != st.session_state.live_actif:
        st.session_state.live_actif = live_clique
        if live_clique:
            prises_info = [
                {
                    'ref_cx': int((p["coords"][0] + p["coords"][2]) / 2),
                    'ref_cy': int((p["coords"][1] + p["coords"][3]) / 2),
                    'usage':  p.get("usage", "Mains"),
                }
                for p in st.session_state.prises
            ]
            st.session_state.live_processor = LiveProcessor(prises_info, st.session_state.ref_img)
        else:
            if st.session_state.live_processor is not None:
                st.session_state.live_processor.stop()
            st.session_state.live_processor = None
        st.rerun()

    if not st.session_state.live_actif:
        st.markdown("""
        <div style="
            background:#1e2e3e;
            border-radius:12px;
            height:320px;
            display:flex;
            flex-direction:column;
            align-items:center;
            justify-content:center;
            gap:1rem;
            box-shadow:0 4px 18px rgba(0,0,0,0.25);
            margin-bottom:0.5rem;
        ">
          <div style="font-size:3.5rem;opacity:0.5;">📷</div>
          <div style="color:rgba(255,255,255,0.7);font-size:1rem;font-weight:600;
                      letter-spacing:0.04em;">
              Cochez la case ci-dessus pour démarrer le flux vidéo
          </div>
          <div style="color:rgba(255,255,255,0.35);font-size:0.82rem;">
              La caméra s'activera et les prises s'afficheront en temps réel
          </div>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.live_actif:
        if st.session_state.live_processor is not None:
            prises_info = [
                {
                    'ref_cx': int((p["coords"][0] + p["coords"][2]) / 2),
                    'ref_cy': int((p["coords"][1] + p["coords"][3]) / 2),
                    'usage':  p.get("usage", "Mains"),
                }
                for p in st.session_state.prises
            ]
            st.session_state.live_processor.set_prises(prises_info)

        # `_on_frame` est redéfini à chaque rerun, capturant `_processor`
        # comme variable de fermeture évaluée ici (thread principal) — et non
        # via st.session_state.get(...) à l'intérieur du callback, qui
        # s'exécute dans le thread caméra WebRTC sans ScriptRunContext
        # Streamlit et ne voit donc jamais la vraie session (renvoie None en
        # silence, d'où l'absence totale de squelette/prises constatée).
        _processor = st.session_state.live_processor

        def _on_frame(frame: av.VideoFrame) -> av.VideoFrame:
            img = frame.to_ndarray(format="bgr24")
            if _processor is not None:
                img = _processor.process(img)
            return av.VideoFrame.from_ndarray(img, format="bgr24")

        # Le live tourne sur la caméra du navigateur qui regarde la page (PC ou
        # téléphone), pas sur celle du serveur — `key=` doit rester fixe pour
        # éviter une reconnexion ICE à chaque st.rerun().
        webrtc_ctx = webrtc_streamer(
            key="bca_live_webrtc",
            mode=WebRtcMode.SENDRECV,
            video_frame_callback=_on_frame,
            media_stream_constraints=MEDIA_CONSTRAINTS,
            rtc_configuration=RTC_CONFIGURATION,
            async_processing=True,
            # Démarre automatiquement le flux dès l'activation du live (la
            # case à cocher est déjà le geste utilisateur) — évite le bouton
            # Start/Stop natif du composant, redondant et déroutant ici.
            desired_playing_state=True,
            # Par défaut streamlit-webrtc affiche les contrôles natifs du
            # navigateur (lecture/pause/barre de progression/plein écran)
            # comme pour une vidéo enregistrée — trompeur et source de bugs
            # sur un flux live (pause n'a pas de sens ici).
            # playsInline est indispensable sur Safari iOS : sans cet
            # attribut, la vidéo refuse de se lire "en ligne" dans la page
            # (même muette + autoplay) et le cadre reste blanc.
            video_html_attrs={
                "autoPlay": True,
                "controls": False,
                "muted": True,
                "playsInline": True,
                "style": {"width": "100%"},
            },
        )
        _live_pret = webrtc_ctx.state.playing

        # DEBUG temporaire : affiche l'état réel de la connexion WebRTC
        # directement dans l'app (pas besoin des logs cloud) — utile car le
        # crash aioice qui s'affichait avant a disparu (fix Python 3.12) mais
        # le live reste un cadre vide, sans aucune erreur dans les logs : on
        # ne sait pas si l'ICE échoue silencieusement ou si le flux vidéo
        # n'atteint juste jamais le callback. À retirer une fois diagnostiqué.
        st.caption(f"🔧 Debug WebRTC : playing={webrtc_ctx.state.playing} | "
                   f"signalling={getattr(webrtc_ctx.state, 'signalling', '?')} | "
                   f"state={webrtc_ctx.state}")

        # Légende + boutons
        leg_col, repere_col, btn_col = st.columns([4, 1, 1])
        with leg_col:
            st.markdown(
                "<div style='display:flex;flex-wrap:wrap;gap:18px;font-size:13px;padding-top:4px;'>"
                "<span>🟡 Main droite</span>"
                "<span>🩵 Main gauche</span>"
                "<span>🟢 Pied droit</span>"
                "<span>🟠 Pied gauche</span>"
                "<span style='opacity:.6'>● mains+pieds &nbsp; ● pieds seul.</span>"
                "</div>",
                unsafe_allow_html=True,
            )
        with repere_col:
            if st.button("📍 Fixer le repère", use_container_width=True, disabled=not _live_pret,
                         help="Ancre les prises à ce que la caméra voit maintenant. "
                              "Déplacez ensuite la caméra : les prises suivront le mur."):
                n = st.session_state.live_processor.fixer_repere()
                if n > 0:
                    st.session_state.message = (
                        f"Repère fixé — {n} prise(s) ancrée(s). "
                        "Les prises suivent maintenant le mur."
                    )
                else:
                    st.session_state.message = (
                        "Suivi du mur pas encore assez stable pour fixer le repère "
                        "— visez bien le mur quelques secondes et réessayez."
                    )
                st.rerun()
        with btn_col:
            if st.button("🔊 Guider", use_container_width=True, disabled=not _live_pret):
                texte = _generer_guidance(st.session_state.live_processor)
                st.session_state.chat_historique.append(
                    {"role": "assistant", "content": texte}
                )
                st.session_state.pending_speech = texte
                st.rerun()
else:
    st.markdown("""
    <div style="
        background:#1e2e3e;
        border-radius:12px;
        height:320px;
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        gap:1rem;
        box-shadow:0 4px 18px rgba(0,0,0,0.25);
        margin-bottom:0.8rem;
    ">
      <div style="font-size:3.5rem;opacity:0.4;">🔒</div>
      <div style="color:rgba(255,255,255,0.65);font-size:1rem;font-weight:600;
                  letter-spacing:0.04em;">
          Mode live verrouillé
      </div>
      <div style="color:rgba(255,255,255,0.32);font-size:0.82rem;">
          Chargez et analysez d'abord une image du mur
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.checkbox("▶ Activer le mode live vidéo", disabled=True,
                help="Lancez d'abord la détection sur une image fixe.")

# ==============================================================================
# SECTION ASSISTANT — pleine largeur, en dessous
# ==============================================================================
st.markdown('<div id="sec-assistant"></div>', unsafe_allow_html=True)
st.markdown("---")
st.markdown("### 🎤 Assistant vocal escalade")

ecouteur = get_ecouteur()

col_hist, col_form = st.columns([3, 2])

with col_hist:
    if not ecouteur.disponible_navigateur:
        st.info("Reconnaissance vocale désactivée — `pip install SpeechRecognition`")

    bulles_html = ""
    for msg in st.session_state.chat_historique:
        if msg["role"] == "user":
            bulles_html += (
                "<div style='display:flex;justify-content:flex-end;margin-bottom:10px;'>"
                "<div style='background:#111111;color:#fff;padding:10px 15px;"
                "border-radius:18px 18px 4px 18px;max-width:80%;font-size:0.9rem;"
                "box-shadow:0 2px 6px rgba(44,111,173,0.18);'>"
                f"<span style='font-size:0.75rem;opacity:0.75;display:block;margin-bottom:3px;'>👤 Vous</span>"
                f"{msg['content']}"
                "</div></div>"
            )
        else:
            bulles_html += (
                "<div style='display:flex;justify-content:flex-start;margin-bottom:10px;'>"
                "<div style='background:#ffffff;color:#111111;padding:10px 15px;"
                "border-radius:18px 18px 18px 4px;max-width:80%;font-size:0.9rem;"
                "box-shadow:0 2px 8px rgba(0,0,0,0.08);border:1px solid #e8eaf0;'>"
                f"<span style='font-size:0.75rem;color:#C9A020;font-weight:600;display:block;margin-bottom:3px;'>🧗 Assistant</span>"
                f"{msg['content']}"
                "</div></div>"
            )

    if not bulles_html:
        bulles_html = (
            "<div style='text-align:center;padding:3rem 0;'>"
            "<div style='font-size:2.4rem;opacity:0.3;margin-bottom:0.6rem;'>🎤</div>"
            "<div style='color:#999;font-size:0.9rem;'>Posez votre première question ci-contre !</div>"
            "</div>"
        )

    st.markdown(
        f"<div style='height:420px;overflow-y:auto;padding:12px 8px;"
        f"background:#fafaf2;border-radius:12px;border:1.5px solid #e8e4d0;'>"
        f"{bulles_html}</div>",
        unsafe_allow_html=True,
    )

with col_form:
    audio_actif = st.toggle("Réponses audio", value=True)

    _derniers_assistant = [m for m in st.session_state.chat_historique if m["role"] == "assistant"]
    if _derniers_assistant:
        st.caption("Sur téléphone, la lecture automatique peut être bloquée : "
                   "utilisez ce bouton si la réponse ne s'est pas dite à voix haute.")
        speak_button_html(_derniers_assistant[-1]["content"])

    st.markdown("<br>", unsafe_allow_html=True)

    with st.form("chat_form", clear_on_submit=True):
        question = st.text_area(
            "Votre question :",
            placeholder="Ex : comment sécuriser une chute ?",
            height=120,
        )
        submit_text = st.form_submit_button("📨 Envoyer", use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if ecouteur.disponible_navigateur:
        st.caption("🎙️ Posez votre question à voix haute — le navigateur demandera l'accès au micro.")
        audio_value = st.audio_input(
            "Parler", key=f"voice_recorder_{st.session_state.voice_turn}",
            label_visibility="collapsed",
        )
    else:
        audio_value = None
        st.caption("Reconnaissance vocale indisponible (pip install SpeechRecognition).")

question_finale = None
if submit_text and question:
    question_finale = question.strip()
elif audio_value is not None:
    with st.spinner("🎧 Transcription en cours…"):
        question_finale = ecouteur.transcrire_wav(audio_value.getvalue())
    st.session_state.voice_turn += 1
    if not question_finale:
        msg = ecouteur.derniere_erreur or "Aucune voix détectée, réessayez."
        st.warning(msg)
        st.rerun()

if question_finale:
    q = question_finale.lower()

    if any(kw in q for kw in ['reste', 'restant', 'sommet', 'combien', 'loin du sommet']):
        reponse = _compter_prises_restantes(
            st.session_state.live_processor,
            st.session_state.prises,
            st.session_state.img_h,
        )
    elif any(kw in q for kw in ['prochaine', 'suivante', 'accroché', 'accroch',
                                  'quelle prise', 'guide', 'guider', 'dois-je prendre']):
        if st.session_state.live_processor and st.session_state.live_actif:
            reponse = _generer_guidance(st.session_state.live_processor)
        else:
            reponse = "Activez le mode live pour que je puisse voir votre position et vous guider."
    else:
        reponse = trouver_reponse(question_finale, st.session_state.get("username", ""))

    st.session_state.chat_historique.append({"role": "user",      "content": question_finale})
    st.session_state.chat_historique.append({"role": "assistant", "content": reponse})
    if audio_actif:
        st.session_state.pending_speech = reponse
    st.rerun()

# ==============================================================================
# FOOTER
# ==============================================================================
st.markdown("""
<div style="
    margin-top: 3rem;
    border-top: 2px solid #e0e4ee;
    padding: 1.4rem 0 0.8rem 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.8rem;
    color: #6b7280;
    font-size: 0.82rem;
">
  <div>
    <span style="font-weight:700;color:#C9A020;">🧗 BlindClimb Assist</span>
    &nbsp;—&nbsp;Application d'assistance à l'escalade pour personnes malvoyantes
  </div>
  <div style="text-align:center;">
    BIJOU Thomas &nbsp;·&nbsp; MONDESIR Edeline &nbsp;·&nbsp; NANDAN Brayan
    &nbsp;·&nbsp; PLACIDE Noam &nbsp;·&nbsp; QUIMPERT Matéo &nbsp;·&nbsp; VIRASSAMY Manoé
  </div>
  <div style="text-align:right;">
    <span style="
        background:#fdf8e8;color:#7A5C00;
        padding:3px 10px;border-radius:12px;
        font-weight:600;font-size:0.78rem;
    ">ESIEE Paris · 2025/2026</span>
  </div>
</div>
""", unsafe_allow_html=True)