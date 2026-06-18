import streamlit as st
st.set_page_config(page_title="BlindClimb Assist — Aide", layout="wide", page_icon="Logo.jpg")

from ui_common import inject_global_css, inject_pwa_tags, render_banner, render_sidebar_logo, render_section_nav, render_page_nav, tag

inject_global_css()
inject_pwa_tags()
render_banner(sous_titre="Aide & mots-clés de l'assistant vocal")

with st.sidebar:
    render_sidebar_logo()
    render_page_nav("aide")
    render_section_nav(anchor_prefix="/")

st.markdown("### ❓ Aide")


def _etape_card(numero, icone, titre, description):
    return f"""
    <div style="background:#ffffff;border:1px solid #e8e4d0;border-radius:12px;
                padding:1rem 1.2rem;display:flex;gap:1rem;align-items:flex-start;
                box-shadow:0 2px 6px rgba(0,0,0,0.04);margin-bottom:0.7rem;">
      <div style="background:#111111;color:#C9A020;width:32px;height:32px;border-radius:50%;
                  display:flex;align-items:center;justify-content:center;
                  font-weight:800;font-size:0.95rem;flex-shrink:0;">{numero}</div>
      <div>
        <div style="font-weight:700;color:#111111;font-size:0.95rem;margin-bottom:2px;">
          {icone} {titre}
        </div>
        <div style="color:#555;font-size:0.85rem;line-height:1.45;">{description}</div>
      </div>
    </div>"""


st.markdown("#### 🧭 Comment utiliser l'application")
st.markdown(_etape_card(1, "📷", "Source image",
    "Importez une photo du mur depuis un fichier, ou prenez-la directement avec la caméra."),
    unsafe_allow_html=True)
st.markdown(_etape_card(2, "✂️", "Recadrage (optionnel)",
    "Recadrez l'image pour ne garder que la zone du mur avant de lancer la détection."),
    unsafe_allow_html=True)
st.markdown(_etape_card(3, "🗺️", "Cartographie",
    "Les prises sont détectées automatiquement par IA. Cliquez sur une prise dans la carte "
    "pour la sélectionner ; modifiez-la ou ajoutez-en une depuis le panneau prises (sidebar)."),
    unsafe_allow_html=True)
st.markdown(_etape_card(4, "📹", "Mode Live",
    "Activez le flux vidéo en direct pour suivre votre position en temps réel sur le mur."),
    unsafe_allow_html=True)
st.markdown(_etape_card(5, "🎤", "Assistant vocal",
    "Posez vos questions par écrit ou à voix haute : conseils, guidage vers la prochaine prise, "
    "ou nombre de prises restantes avant le sommet."),
    unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("#### 🎤 Mots-clés utiles pour l'assistant vocal")
st.caption("Dites ou écrivez une phrase contenant l'un de ces mots — inutile d'utiliser la formule exacte.")

_AIDE_MOTS_CLES = [
    ("📹 Guidage en direct", "Nécessite le mode Live activé.",
     ["prochaine", "suivante", "quelle prise", "guide", "guider", "dois-je prendre"]),
    ("🪜 Progression sur la voie", None,
     ["reste", "restant", "sommet", "combien", "loin du sommet"]),
    ("🛟 Sécurité", None,
     ["sécurité", "danger", "risque", "sûr", "chute", "tomber", "douleur", "blessure"]),
    ("🎒 Équipement", None,
     ["équipement", "matériel", "chaussures", "baudrier", "corde", "casque"]),
    ("🗣️ Communication avec l'assureur", None,
     ["assureur", "communiquer", "guidage", "instructions", "code", "verbal"]),
    ("🧗 Technique de grimpe", None,
     ["technique", "grimper", "comment monter", "prises", "pied", "main", "mouvement", "équilibre"]),
    ("🧭 Orientation sur le mur", None,
     ["orientation", "repère", "carte", "position", "où je suis", "situer"]),
    ("😮‍💨 Fatigue & gestion de l'effort", None,
     ["fatigue", "repos", "pause", "récupération", "peur", "vertige", "stress", "confiance"]),
    ("📖 Vocabulaire d'escalade", None,
     ["vocabulaire", "jug", "réglette", "bombe", "pince", "dégaine", "nœud"]),
    ("♿ Associations & droits", None,
     ["association", "club", "fédération", "handisport", "droit", "accessibilité", "tarif"]),
    ("👋 Démarrage & fin de session", None,
     ["bonjour", "salut", "aide", "au revoir", "merci", "stop", "arrête"]),
]

for titre_cat, note, mots in _AIDE_MOTS_CLES:
    with st.expander(titre_cat):
        if note:
            st.caption(note)
        st.markdown("".join(tag(m) for m in mots), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("""
<div style="text-align:center;color:#9a9a9a;font-size:0.8rem;
            padding-top:0.8rem;border-top:1px solid #e8e4d0;">
  🧗 BlindClimb Assist &nbsp;·&nbsp; ESIEE Paris &nbsp;·&nbsp; 2025/2026
</div>
""", unsafe_allow_html=True)
