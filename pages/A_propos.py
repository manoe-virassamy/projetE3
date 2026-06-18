import streamlit as st
st.set_page_config(page_title="BlindClimb Assist — À propos", layout="wide", page_icon="Logo.jpg")

from ui_common import inject_global_css, inject_pwa_tags, render_banner, render_sidebar_logo, render_section_nav, render_page_nav

inject_global_css()
inject_pwa_tags()
render_banner(sous_titre="À propos du projet")

with st.sidebar:
    render_sidebar_logo()
    render_page_nav("a_propos")
    render_section_nav(anchor_prefix="/")

st.markdown("### ℹ️ À propos")

st.markdown("""
<div style="background:#ffffff;border:1px solid #e8e4d0;border-radius:12px;
            padding:1.2rem 1.4rem;box-shadow:0 2px 6px rgba(0,0,0,0.04);margin-bottom:1rem;">
  <div style="font-weight:700;color:#111111;font-size:1rem;margin-bottom:0.4rem;">
    🧗 BlindClimb Assist
  </div>
  <div style="color:#555;font-size:0.9rem;line-height:1.55;">
    Application d'assistance à la navigation sur mur d'escalade pour grimpeurs malvoyants
    ou aveugles, développée dans le cadre d'un projet étudiant à l'ESIEE Paris.
  </div>
  <div style="margin-top:0.8rem;">
    <span style="background:#fdf8e8;color:#7A5C00;padding:3px 10px;border-radius:12px;
                 font-weight:600;font-size:0.78rem;">ESIEE Paris · Promo 2025/2026</span>
  </div>
</div>
""", unsafe_allow_html=True)


def _feature_card(icone, titre, description):
    return f"""
    <div style="background:#ffffff;border:1px solid #e8e4d0;border-radius:12px;
                padding:1rem 1.2rem;display:flex;gap:1rem;align-items:flex-start;
                box-shadow:0 2px 6px rgba(0,0,0,0.04);margin-bottom:0.7rem;">
      <div style="font-size:1.4rem;flex-shrink:0;">{icone}</div>
      <div>
        <div style="font-weight:700;color:#111111;font-size:0.92rem;margin-bottom:2px;">{titre}</div>
        <div style="color:#555;font-size:0.84rem;line-height:1.45;">{description}</div>
      </div>
    </div>"""


st.markdown("#### ✨ Fonctionnalités")
_FEATURES = [
    ("🎯", "Détection automatique des prises",
     "Modèle YOLO entraîné sur des prises d'escalade, classification automatique en "
     "mains+pieds (grandes prises) et pieds seulement (petites prises)."),
    ("🗺️", "Cartographie interactive du mur",
     "Visualisation des prises détectées, sélection, modification et suppression manuelle."),
    ("📹", "Flux vidéo live",
     "Caméra en temps réel avec squelette MediaPipe superposé."),
    ("🧭", "Suivi des prises par homographie",
     "Les points restent ancrés sur le mur même si la caméra bouge (ORB + RANSAC)."),
    ("🗣️", "Guidage vocal",
     "Flèches de direction par membre (main droite/gauche, pied droit/gauche) avec retour vocal."),
    ("🎤", "Assistant vocal",
     "Questions/réponses sur l'escalade, guidance vers la prochaine prise, comptage des prises restantes."),
    ("🔁", "Mode micro continu",
     "Écoute en boucle automatique, répond à voix haute, recommence ; dire « au revoir » pour arrêter."),
    ("✂️", "Recadrage interactif",
     "Cliquer le premier coin, ajuster le rectangle avec deux sliders avant de lancer la détection."),
]
for icone, titre, desc in _FEATURES:
    st.markdown(_feature_card(icone, titre, desc), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("#### 🛠️ Technologies utilisées")
_TECHS = [
    ("YOLOv8",          "Détection et classification des prises d'escalade."),
    ("MediaPipe",       "Détection de pose pour le squelette superposé en mode live."),
    ("OpenCV",          "Traitement d'image, analyse couleur/forme et suivi par homographie."),
    ("Streamlit",       "Interface web interactive de l'application."),
    ("pyttsx3",         "Synthèse vocale pour les retours et le guidage."),
    ("SpeechRecognition / Vosk", "Reconnaissance vocale de l'assistant."),
]
cols = st.columns(3)
for i, (nom, desc) in enumerate(_TECHS):
    with cols[i % 3]:
        st.markdown(f"""
        <div style="background:#ffffff;border:1px solid #e8e4d0;border-radius:12px;
                    padding:1rem;box-shadow:0 2px 6px rgba(0,0,0,0.04);height:100%;
                    margin-bottom:0.7rem;">
          <div style="font-weight:700;color:#111111;font-size:0.9rem;margin-bottom:0.3rem;">{nom}</div>
          <div style="color:#666;font-size:0.8rem;line-height:1.4;">{desc}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("#### 👥 Équipe")
st.markdown("""
<div style="background:#ffffff;border:1px solid #e8e4d0;border-radius:12px;
            padding:1rem 1.4rem;box-shadow:0 2px 6px rgba(0,0,0,0.04);
            color:#555;font-size:0.88rem;line-height:1.7;">
  BIJOU Thomas &nbsp;·&nbsp; MONDESIR Edeline &nbsp;·&nbsp; NANDAN Brayan
  &nbsp;·&nbsp; PLACIDE Noam &nbsp;·&nbsp; QUIMPERT Matéo &nbsp;·&nbsp; VIRASSAMY Manoé
  <br>Projet ESIEE Paris — 2025/2026
</div>
""", unsafe_allow_html=True)
