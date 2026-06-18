"""Génère les icônes utilisées quand l'app est ajoutée à l'écran d'accueil
d'un téléphone (PWA Android / "Sur l'écran d'accueil" iOS Safari).

À lancer une fois (ou si Logo.jpg change) :
    python generate_icons.py

Écrit static/icons/*.png et static/manifest.json, servis par Streamlit via
`enableStaticServing` (voir .streamlit/config.toml) et référencés depuis les
balises PWA insérées dans index.html par patch_streamlit_pwa.py.
"""
import json
from pathlib import Path

from PIL import Image

RACINE = Path(__file__).parent
LOGO = RACINE / "Logo.jpg"
ICONS_DIR = RACINE / "static" / "icons"
COULEUR_THEME = "#C9A020"
COULEUR_FOND = "#000000"

# Android (icônes adaptatives) recadre les icônes "maskable" en cercle/squircle :
# le contenu doit tenir dans une zone de sécurité centrale (ratio recommandé ~0.8),
# sinon le logo est en partie rogné par le masque.
MARGE_SECURITE = 0.8

TAILLES_MASKABLE = {"icon-192.png": 192, "icon-512.png": 512}
TAILLES_PLEIN_CADRE = {"apple-touch-icon.png": 180}


def logo_carre(marge_securite: float = 1.0) -> Image.Image:
    """Place Logo.jpg (portrait) sur un canevas carré, fond noir comme le logo.

    marge_securite < 1 réduit le logo pour laisser une marge (zone de sécurité
    des icônes "maskable" Android).
    """
    logo = Image.open(LOGO).convert("RGBA")
    cote = max(logo.size)
    if marge_securite < 1.0:
        nouvelle_hauteur = int(logo.height * marge_securite)
        nouvelle_largeur = int(logo.width * marge_securite)
        logo = logo.resize((nouvelle_largeur, nouvelle_hauteur), Image.LANCZOS)
    canevas = Image.new("RGBA", (cote, cote), COULEUR_FOND)
    canevas.paste(logo, ((cote - logo.width) // 2, (cote - logo.height) // 2))
    return canevas


def generer() -> None:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    base_maskable = logo_carre(marge_securite=MARGE_SECURITE)
    for nom, taille in TAILLES_MASKABLE.items():
        base_maskable.resize((taille, taille), Image.LANCZOS).save(ICONS_DIR / nom)

    base_plein_cadre = logo_carre()
    for nom, taille in TAILLES_PLEIN_CADRE.items():
        base_plein_cadre.resize((taille, taille), Image.LANCZOS).save(ICONS_DIR / nom)

    manifest = {
        "name": "BlindClimb Assist",
        "short_name": "BCA",
        "start_url": ".",
        "display": "standalone",
        "background_color": COULEUR_FOND,
        "theme_color": COULEUR_THEME,
        "icons": [
            {"src": "/app/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/app/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    (RACINE / "static" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Icônes et manifest générés dans {ICONS_DIR.parent}")


if __name__ == "__main__":
    generer()
