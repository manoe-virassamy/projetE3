"""Insère les balises PWA (icône d'écran d'accueil) directement dans le HTML
statique installé avec Streamlit.

Nécessaire car Chrome et Safari ne détectent les balises <link rel="manifest">
/ <link rel="apple-touch-icon"> que si elles sont présentes au chargement
initial de la page — les ajouter en JavaScript après coup (seule option
offerte par l'API publique de Streamlit, via st.components.v1.html) n'est pas
fiable pour "Ajouter à l'écran d'accueil".

À relancer après toute (ré)installation ou mise à jour de Streamlit, car pip
réécrit ce fichier à chaque fois, effaçant le correctif :
    python patch_streamlit_pwa.py
"""
from pathlib import Path

import streamlit

MARQUEUR_DEBUT = "<!-- BCA-PWA-START -->"
MARQUEUR_FIN = "<!-- BCA-PWA-END -->"

BALISES = f"""{MARQUEUR_DEBUT}
    <link rel="manifest" href="/app/static/manifest.json" />
    <link rel="apple-touch-icon" href="/app/static/icons/apple-touch-icon.png" />
    <link rel="icon" href="/app/static/icons/icon-192.png" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="BlindClimb Assist" />
    <meta name="theme-color" content="#C9A020" />
    {MARQUEUR_FIN}"""


def index_html() -> Path:
    return Path(streamlit.__file__).parent / "static" / "index.html"


def patcher() -> None:
    chemin = index_html()
    html = chemin.read_text(encoding="utf-8")

    if MARQUEUR_DEBUT in html:
        debut = html.index(MARQUEUR_DEBUT)
        fin = html.index(MARQUEUR_FIN) + len(MARQUEUR_FIN)
        html = html[:debut] + BALISES.strip() + html[fin:]
        print("Balises PWA déjà présentes : mises à jour.")
    else:
        if "</head>" not in html:
            raise RuntimeError(f"</head> introuvable dans {chemin} — structure inattendue, abandon.")
        html = html.replace("</head>", f"  {BALISES}\n  </head>")
        print("Balises PWA insérées.")

    chemin.write_text(html, encoding="utf-8")
    print(f"Fichier modifié : {chemin}")


if __name__ == "__main__":
    patcher()
