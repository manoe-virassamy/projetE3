"""Styles et composants partagés entre les pages Streamlit de BlindClimb Assist."""
import base64
import streamlit as st

COULEUR_HEX = {
    "Rouge":      "#e53935",
    "Orange":     "#fb8c00",
    "Jaune":      "#fdd835",
    "Jaune-Vert": "#c0ca33",
    "Vert":       "#43a047",
    "Bleu":       "#1e88e5",
    "Violet":     "#8e24aa",
    "Inconnue":   "#9e9e9e",
}


@st.cache_data
def get_logo_b64():
    with open("Logo.jpg", "rb") as f:
        return base64.b64encode(f.read()).decode()


def gate_username():
    """Bloque la page tant que l'utilisateur n'a pas saisi son prénom.
    Doit être appelé en tout début de chaque page, avant tout autre contenu."""
    if st.session_state.get("username"):
        return

    logo_b64 = get_logo_b64()

    st.markdown("""<style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(160deg, #0d1a26 0%, #1e2e40 100%) !important;
    }
    [data-testid="stHeader"]  { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stForm"] {
        background: #111518 !important;
        border: 1.5px solid #2a3040 !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.5) !important;
    }
    </style>""", unsafe_allow_html=True)

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(f"""
        <div style='text-align:center;padding:3.5rem 0 1.2rem;'>
          <img src="data:image/jpeg;base64,{logo_b64}"
               style="height:88px;border-radius:12px;object-fit:contain;
                      display:block;margin:0 auto 1.2rem;">
          <div style='color:#C9A020;font-size:1.95rem;font-weight:800;letter-spacing:0.03em;
                      text-shadow:0 2px 8px rgba(0,0,0,0.3);'>BlindClimb Assist</div>
          <div style='color:rgba(255,255,255,0.6);font-size:0.92rem;margin-top:0.35rem;
                      margin-bottom:1.8rem;font-style:italic;'>
              La voix qui vous guide pour une montée en confiance</div>
          <div style='color:rgba(255,255,255,0.82);font-size:1rem;font-weight:600;
                      margin-bottom:0.6rem;'>Comment souhaitez-vous être appelé(e) ?</div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("bca_username_form"):
            nom = st.text_input("prénom", placeholder="Votre prénom…", label_visibility="collapsed")
            submitted = st.form_submit_button("🧗 Commencer", use_container_width=True, type="primary")

        if submitted:
            if nom.strip():
                st.session_state.username = nom.strip()
                st.rerun()
            else:
                st.warning("Veuillez entrer votre prénom pour continuer.")

    st.stop()


def inject_pwa_tags():
    """Injecte les balises PWA (manifest, icône, titre) dans le <head> du document
    parent via JavaScript. Filet de secours pour les environnements où le patch
    direct de l'index.html de Streamlit est impossible (ex. Streamlit Community
    Cloud, où le process applicatif n'a pas les droits d'écriture sur les fichiers
    installés par pip) — voir patch_streamlit_pwa.py pour l'approche par patch
    statique, utilisée en local."""
    st.iframe("""
    <script>
    (function() {
        var doc = window.parent.document;
        if (doc.getElementById('bca-pwa-manifest')) return;

        // Supprimer les balises Streamlit existantes pour qu'elles ne prennent
        // pas la priorité sur les nôtres (le navigateur utilise la première
        // balise <link rel="manifest"> trouvée — il faut retirer celle de
        // Streamlit avant d'injecter la nôtre).
        ['link[rel="manifest"]', 'link[rel="apple-touch-icon"]',
         'link[rel="shortcut icon"]', 'link[rel="icon"]'].forEach(function(sel) {
            doc.querySelectorAll(sel).forEach(function(el) { el.remove(); });
        });

        function lien(rel, href, id) {
            var l = doc.createElement('link');
            l.rel = rel; l.href = href;
            if (id) l.id = id;
            doc.head.appendChild(l);
        }
        function meta(name, content) {
            var m = doc.createElement('meta');
            m.name = name; m.content = content;
            doc.head.appendChild(m);
        }

        lien('manifest', '/app/static/manifest.json', 'bca-pwa-manifest');
        lien('apple-touch-icon', '/app/static/icons/apple-touch-icon.png');
        lien('icon', '/app/static/icons/icon-192.png');
        meta('apple-mobile-web-app-capable', 'yes');
        meta('apple-mobile-web-app-title', 'BlindClimb Assist');
        meta('theme-color', '#C9A020');
        doc.title = 'BlindClimb Assist';
    })();
    </script>
    """, height=1, width=1)


def inject_global_css():
    st.markdown("""
    <style>

    /* ── Masquer le sélecteur de pages natif (remplacé par notre nav custom) ───── */
    [data-testid="stSidebarNav"] {
        display: none;
    }

    /* ── Réduction du padding haut ────────────────────────────────────────────── */
    [data-testid="stAppViewBlockContainer"] {
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    /* ── Titres de section h3 — style carte ──────────────────────────────────── */
    h3 {
        color: #111111;
        font-size: 1.1rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        background: #ffffff;
        border-left: 4px solid #C9A020;
        border-radius: 0 8px 8px 0;
        padding: 0.55rem 1rem;
        margin-top: 0.4rem;
        margin-bottom: 0.9rem;
        box-shadow: 0 2px 8px rgba(201, 160, 32, 0.12);
    }
    @media (prefers-color-scheme: dark) {
        h3 {
            color: #e8dfc0 !important;
            background: #1a1a14 !important;
        }
    }

    /* ── Séparateurs ──────────────────────────────────────────────────────────── */
    hr {
        border: none;
        border-top: 2px solid #e0e0e0;
        margin: 1.4rem 0;
    }

    /* ── Boutons principaux ───────────────────────────────────────────────────── */
    button[kind="primary"] {
        background-color: #111111 !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        transition: background-color 0.2s ease, transform 0.1s ease !important;
    }
    button[kind="primary"]:hover {
        background-color: #333333 !important;
        transform: translateY(-1px) !important;
    }

    /* ── Boutons secondaires ──────────────────────────────────────────────────── */
    button[kind="secondary"] {
        border-radius: 8px !important;
        border: 1.5px solid #C9A020 !important;
        color: #7A5C00 !important;
        font-weight: 500 !important;
        transition: background-color 0.2s ease !important;
    }
    button[kind="secondary"]:hover {
        background-color: #fdf8e8 !important;
    }

    /* ── Tabs ─────────────────────────────────────────────────────────────────── */
    [data-testid="stTabs"] [data-baseweb="tab"] {
        font-weight: 600;
        color: #555;
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        color: #7A5C00 !important;
        border-bottom: 3px solid #C9A020 !important;
    }

    /* ── Conteneurs chat ──────────────────────────────────────────────────────── */
    [data-testid="stChatMessageContent"] {
        border-radius: 10px;
    }

    /* ── Métriques / info boxes ───────────────────────────────────────────────── */
    [data-testid="stAlert"] {
        border-radius: 8px !important;
    }

    /* ── Scrollbar fine ───────────────────────────────────────────────────────── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #f0f0f0; }
    ::-webkit-scrollbar-thumb { background: #C9A020; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #8B6914; }

    /* ── Spinner ──────────────────────────────────────────────────────────────── */
    [data-testid="stSpinner"] {
        background: #ffffff !important;
        border: 1.5px solid #e8e4d0 !important;
        border-radius: 12px !important;
        padding: 1rem 1.4rem !important;
        box-shadow: 0 2px 12px rgba(201,160,32,0.12) !important;
    }
    [data-testid="stSpinner"] p {
        color: #111111 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
    }
    /* Roue de chargement en or */
    [data-testid="stSpinner"] svg {
        color: #C9A020 !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stSpinner"] {
            background: #1c1c1c !important;
            border-color: #2e2e2e !important;
        }
        [data-testid="stSpinner"] p { color: #e0e0e0 !important; }
    }

    /* ── Formulaire assistant ─────────────────────────────────────────────────── */
    [data-testid="stForm"] {
        background: #ffffff;
        border: 1.5px solid #e8e4d0;
        border-radius: 12px !important;
        padding: 1rem !important;
        box-shadow: 0 2px 10px rgba(201,160,32,0.08);
    }
    [data-testid="stForm"] textarea {
        border: 1.5px solid #d4c07a !important;
        border-radius: 8px !important;
        font-size: 0.92rem !important;
        background: #fffef8 !important;
        transition: border-color 0.2s ease !important;
    }
    [data-testid="stForm"] textarea:focus {
        border-color: #C9A020 !important;
        box-shadow: 0 0 0 3px rgba(201,160,32,0.12) !important;
    }
    @media (prefers-color-scheme: dark) {
        [data-testid="stForm"] {
            background: #1a1a16 !important;
            border-color: #2e2a18 !important;
        }
        [data-testid="stForm"] textarea {
            background: #111110 !important;
            border-color: #3a3020 !important;
        }
    }
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: transform 0.1s ease !important;
    }
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {
        transform: translateY(-1px) !important;
    }

    /* ── Responsive mobile ────────────────────────────────────────────────────── */
    @media (max-width: 768px) {
        /* Bannière : réduire taille et padding */
        .bca-banner {
            flex-direction: column !important;
            text-align: center !important;
            padding: 1.2rem 1rem !important;
            gap: 0.8rem !important;
        }
        .bca-banner img {
            height: 70px !important;
        }
        .bca-banner div[style*="font-size:2rem"] {
            font-size: 1.4rem !important;
        }
        .bca-banner div[style*="margin-left:auto"] {
            margin-left: 0 !important;
        }

        /* Padding général réduit */
        [data-testid="stAppViewBlockContainer"] {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 1rem !important;
        }

        /* Sidebar (panneau prises) : pleine largeur en overlay */
        [data-testid="stSidebar"] {
            width: 85vw !important;
            min-width: unset !important;
        }
        [data-testid="stSidebar"] > div {
            padding: 1rem 0.8rem !important;
        }
        /* Agrandir le bouton d'ouverture de la sidebar */
        [data-testid="stSidebarCollapsedControl"] button {
            width: 44px !important;
            height: 44px !important;
            background: #111111 !important;
            border-radius: 8px !important;
            color: #C9A020 !important;
        }

        /* Colonnes métriques : passer en 2×2 */
        [data-testid="column"] {
            min-width: 45% !important;
        }

        /* Titres h3 plus petits */
        h3 {
            font-size: 0.95rem !important;
            padding: 0.4rem 0.7rem !important;
        }

        /* Colonnes assistant (historique + formulaire) : empilées */
        [data-testid="stHorizontalBlock"]:has([data-testid="stForm"]) {
            flex-direction: column !important;
        }

        /* Formulaire : boutons en colonne */
        [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
        }

        /* Badges de statut : retour à la ligne */
        [data-testid="stMarkdownContainer"] span {
            margin-bottom: 4px !important;
            display: inline-flex !important;
        }

        /* Carte cartographie + détail : empilés */
        [data-testid="stHorizontalBlock"]:has([data-testid="stImageCoordinates"]) {
            flex-direction: column !important;
        }

        /* Flux vidéo live : hauteur fixe réduite + défilement interne au lieu d'un grand vide */
        [data-testid="stIFrame"] {
            max-height: 60vh !important;
        }

        /* Footer : tout en colonne */
        [data-testid="stMarkdownContainer"] div[style*="justify-content: space-between"] {
            flex-direction: column !important;
            text-align: center !important;
            gap: 0.5rem !important;
        }
    }

    /* ── Navigation sidebar (liens vers les sections) ────────────────────────────── */
    [data-testid="stSidebar"] a[href^="#sec-"],
    [data-testid="stSidebar"] a[href^="/#sec-"] {
        border-radius: 6px;
        margin: 0 -0.4rem;
        padding-left: 0.4rem !important;
        padding-right: 0.4rem !important;
        transition: background 0.15s ease;
    }
    [data-testid="stSidebar"] a[href^="#sec-"]:hover,
    [data-testid="stSidebar"] a[href^="/#sec-"]:hover {
        background: rgba(201,160,32,0.12);
    }

    /* ── Liens de page (st.page_link) dans la sidebar — bouton doré bien visible ── */
    [data-testid="stSidebar"] [data-testid="stPageLink"] {
        background: rgba(201,160,32,0.14);
        border: 1.5px solid #C9A020;
        border-radius: 8px;
        padding: 0.45rem 0.7rem !important;
        margin: 0.2rem 0 0.8rem 0;
        transition: background 0.15s ease, transform 0.1s ease;
    }
    [data-testid="stSidebar"] [data-testid="stPageLink"]:hover {
        background: rgba(201,160,32,0.28);
        transform: translateY(-1px);
    }
    [data-testid="stSidebar"] [data-testid="stPageLink"] p {
        color: #C9A020 !important;
        font-size: 0.85rem !important;
        font-weight: 700 !important;
    }

    /* ── Animations ───────────────────────────────────────────────────────────── */
    @keyframes bca-fadein {
        from { opacity: 0; transform: translateY(14px); }
        to   { opacity: 1; transform: translateY(0);    }
    }
    @keyframes bca-fadein-fast {
        from { opacity: 0; transform: translateY(6px); }
        to   { opacity: 1; transform: translateY(0);   }
    }

    /* ── Onde sonore (micro actif) ───────────────────────────────────────────────── */
    @keyframes bca-wave {
        0%, 100% { transform: scaleY(0.25); }
        50%      { transform: scaleY(1);    }
    }
    .bca-wave-bar {
        display: inline-block;
        width: 4px;
        height: 22px;
        margin: 0 2px;
        border-radius: 2px;
        background: #C9A020;
        animation: bca-wave 0.9s ease-in-out infinite;
        transform-origin: center;
    }

    .bca-banner {
        background:
            repeating-linear-gradient(0deg,  transparent 0px, transparent 59px, rgba(255,255,255,0.04) 60px),
            repeating-linear-gradient(90deg, transparent 0px, transparent 59px, rgba(255,255,255,0.04) 60px),
            radial-gradient(ellipse at 18% 60%, rgba(201,160,32,0.20) 0%, transparent 52%),
            radial-gradient(ellipse at 78% 35%, rgba(201,160,32,0.12) 0%, transparent 42%),
            linear-gradient(160deg, #1a2535 0%, #1e2e3e 55%, #162030 100%);
        border-radius: 14px;
        padding: 1.6rem 2.8rem 1.6rem 2rem;
        margin-bottom: 1.6rem;
        box-shadow: 0 4px 22px rgba(0,0,0,0.35);
        display: flex;
        align-items: center;
        gap: 1.8rem;
        animation: bca-fadein 0.55s ease both;
    }

    /* Sections principales */
    [data-testid="stMarkdownContainer"] h3 {
        animation: bca-fadein-fast 0.4s ease both;
    }

    /* Badges de statut */
    [data-testid="stMarkdownContainer"] span {
        animation: bca-fadein-fast 0.35s ease both;
    }

    /* Colonnes (métriques, carte…) */
    [data-testid="column"] {
        animation: bca-fadein 0.45s ease both;
    }

    /* Tabs */
    [data-testid="stTabs"] {
        animation: bca-fadein-fast 0.4s ease both;
    }
    </style>
    """, unsafe_allow_html=True)


def render_banner(sous_titre="La voix qui vous guide pour une montée en confiance !"):
    logo_b64 = get_logo_b64()
    username = st.session_state.get("username", "")
    user_badge = (
        f"<span style='background:rgba(201,160,32,0.25);color:#C9A020;font-size:0.78rem;"
        f"font-weight:700;padding:0.25rem 0.75rem;border-radius:20px;margin-top:0.4rem;"
        f"display:inline-block;border:1px solid rgba(201,160,32,0.5);'>👤 {username}</span>"
    ) if username else ""
    st.markdown(f"""
    <div class="bca-banner">
      <img src="data:image/jpeg;base64,{logo_b64}"
           style="height:100px;border-radius:10px;object-fit:contain;flex-shrink:0;">
      <div>
        <div style="color:#ffffff;font-size:2rem;font-weight:800;letter-spacing:0.03em;
                    line-height:1.15;text-shadow:0 2px 8px rgba(0,0,0,0.18);">
            BlindClimb Assist</div>
        <div style="color:rgba(255,255,255,0.82);font-size:1rem;font-style:italic;
                    margin-top:0.3rem;letter-spacing:0.01em;">
            {sous_titre}</div>
      </div>
      <div style="margin-left:auto;text-align:right;">
        <span style="background:rgba(255,255,255,0.15);color:#fff;font-size:0.75rem;
                     font-weight:600;padding:0.3rem 0.8rem;border-radius:20px;
                     letter-spacing:0.04em;border:1px solid rgba(255,255,255,0.3);">
            ESIEE Paris · 2025/2026</span>
        <br>{user_badge}
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_sidebar_logo():
    try:
        logo_b64 = get_logo_b64()
        st.markdown(f"""
        <div style='display:flex;align-items:center;gap:0.7rem;
                    background:linear-gradient(135deg,#0D0D0D,#1a1a1a);
                    border-radius:10px;padding:0.7rem 1rem;margin-bottom:0.6rem;'>
          <img src="data:image/jpeg;base64,{logo_b64}"
               style="height:40px;border-radius:6px;object-fit:contain;flex-shrink:0;">
          <div>
            <div style='color:#C9A020;font-weight:800;font-size:0.9rem;line-height:1.1;'>BlindClimb</div>
            <div style='color:rgba(255,255,255,0.55);font-size:0.72rem;'>Assist</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.markdown("""
        <div style='background:linear-gradient(135deg,#0D0D0D,#1a1a1a);
                    border-radius:10px;padding:0.7rem 1rem;margin-bottom:0.6rem;'>
          <span style='color:#C9A020;font-weight:800;font-size:0.9rem;'>🧗 BCA</span>
        </div>
        """, unsafe_allow_html=True)


def render_user_section():
    """Bloc utilisateur dans la sidebar : avatar, préférences, déconnexion."""
    username = st.session_state.get("username", "")

    if "prefs_main"   not in st.session_state: st.session_state.prefs_main   = "Les deux"
    if "prefs_niveau" not in st.session_state: st.session_state.prefs_niveau = "Débutant"
    if "prefs_audio"  not in st.session_state: st.session_state.prefs_audio  = True

    initiale = username[0].upper() if username else "?"
    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#111508,#1a1e08);border:1px solid #3a3a10;
                border-radius:10px;padding:0.75rem 1rem;margin-bottom:0.5rem;'>
      <div style='display:flex;align-items:center;gap:0.65rem;'>
        <div style='width:36px;height:36px;border-radius:50%;background:#C9A020;
                    display:flex;align-items:center;justify-content:center;
                    font-size:1rem;font-weight:800;color:#111111;flex-shrink:0;'>
            {initiale}</div>
        <div>
          <div style='color:#e8dfc0;font-weight:700;font-size:0.9rem;line-height:1.15;'>
              {username}</div>
          <div style='color:rgba(255,255,255,0.38);font-size:0.67rem;letter-spacing:.05em;
                      text-transform:uppercase;'>Grimpeur·se</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️ Préférences"):
        st.radio("Main dominante", ["Droite", "Gauche", "Les deux"],
                 horizontal=True, key="prefs_main")
        st.radio("Niveau", ["Débutant", "Confirmé"],
                 horizontal=True, key="prefs_niveau")
        st.toggle("Retour vocal", key="prefs_audio")

    if st.button("↩ Changer de profil", use_container_width=True, key="bca_logout"):
        for k in [k for k in st.session_state if k in ("username", "prefs_main", "prefs_niveau", "prefs_audio")]:
            del st.session_state[k]
        st.rerun()


def nav_row(href, icon, label):
    return (f"<a href='{href}' style='display:flex;align-items:center;gap:0.55rem;"
            f"padding:0.35rem 0;text-decoration:none;'>"
            f"<span style='width:22px;height:22px;border-radius:50%;"
            f"background:#1e1e1e;display:inline-flex;align-items:center;"
            f"justify-content:center;font-size:0.85rem;flex-shrink:0;'>"
            f"<span>{icon}</span></span>"
            f"<span style='font-size:0.82rem;color:rgba(255,255,255,0.85);font-weight:500;'>{label}</span>"
            f"</a>")


def render_section_nav(anchor_prefix=""):
    """Liens vers les 5 sections de la page principale.
    anchor_prefix="" si on est déjà sur la page principale (ancres locales),
    "/" si on est sur une autre page (ancres vers la racine)."""
    items = [
        ("sec-source",       "📷", "Source image"),
        ("sec-recadrage",    "✂️", "Recadrage"),
        ("sec-cartographie", "🗺️", "Cartographie"),
        ("sec-live",         "📹", "Mode Live"),
        ("sec-assistant",    "🎤", "Assistant IA"),
    ]
    rows = "".join(nav_row(f"{anchor_prefix}#{a}", icon, label) for a, icon, label in items)
    st.markdown(f"""
    <div style='background:#131313;border:1px solid #2a2a2a;border-radius:10px;
                padding:0.7rem 0.9rem;margin-bottom:0.6rem;'>
      <div style='color:rgba(255,255,255,0.5);font-size:0.72rem;font-weight:600;
                  letter-spacing:.06em;text-transform:uppercase;margin-bottom:0.4rem;'>
        Navigation
      </div>
      {rows}
    </div>
    """, unsafe_allow_html=True)


def render_page_nav(current):
    """Menu des 3 pages (Accueil / Aide / À propos) avec indication de la page courante.
    current: "accueil", "aide" ou "a_propos"."""
    pages = [
        ("accueil",  "app.py",            "🏠", "Accueil"),
        ("aide",     "pages/Aide.py",     "❓", "Aide"),
        ("a_propos", "pages/A_propos.py", "ℹ️", "À propos"),
    ]
    for key, target, icon, label in pages:
        if key == current:
            st.markdown(f"""
            <div style='display:flex;align-items:center;gap:0.5rem;
                        background:#C9A020;border:1.5px solid #C9A020;
                        border-radius:8px;padding:0.45rem 0.7rem;margin:0.2rem 0 0.6rem 0;
                        box-shadow:0 2px 8px rgba(201,160,32,0.35);'>
              <span>{icon}</span>
              <span style='color:#111111;font-size:0.85rem;font-weight:800;'>{label}</span>
              <span style='margin-left:auto;color:rgba(0,0,0,0.55);font-size:0.65rem;
                          text-transform:uppercase;letter-spacing:.04em;font-weight:700;'>Ici</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.page_link(target, label=label, icon=icon)


def couleur_swatch(nom_couleur, taille="12px"):
    hexcode = COULEUR_HEX.get(nom_couleur, "#9e9e9e")
    return (f"<span style='display:inline-block;width:{taille};height:{taille};"
            f"border-radius:50%;background:{hexcode};"
            f"border:1px solid rgba(0,0,0,0.15);vertical-align:middle;'></span>")


def score_bar(score, dark=True, show_label=True):
    pct = max(0, min(100, round(score * 100)))
    if score >= 0.7:
        color = "#43a047"
    elif score >= 0.4:
        color = "#fb8c00"
    else:
        color = "#e53935"
    label_col = "rgba(255,255,255,0.5)" if dark else "#666"
    track_bg  = "#1e1e1e" if dark else "#eee"
    label_row = (
        f"<div style='display:flex;justify-content:space-between;"
        f"font-size:0.75rem;color:{label_col};margin-bottom:2px;'>"
        f"<span>Confiance YOLO</span>"
        f"<span style='color:{color};font-weight:700;'>{pct}%</span>"
        f"</div>"
    ) if show_label else ""
    return (
        f"<div style='margin-top:6px;'>"
        f"{label_row}"
        f"<div style='background:{track_bg};border-radius:6px;height:8px;overflow:hidden;'>"
        f"<div style='background:{color};width:{pct}%;height:100%;border-radius:6px;'></div>"
        f"</div>"
        f"</div>"
    )


def wave_html(label="🎙️ J'écoute…"):
    delays = [0.0, 0.15, 0.3, 0.45, 0.6, 0.45, 0.3]
    bars = "".join(
        f"<span class='bca-wave-bar' style='animation-delay:{d}s;'></span>"
        for d in delays
    )
    return (
        f"<div style='display:flex;align-items:center;gap:14px;"
        f"background:#161616;border:1px solid #2a2a2a;border-radius:10px;"
        f"padding:0.8rem 1.1rem;margin:0.4rem 0;'>"
        f"<div style='display:flex;align-items:center;height:24px;'>{bars}</div>"
        f"<span style='color:#C9A020;font-weight:600;font-size:0.9rem;'>{label}</span>"
        f"</div>"
    )


def badge(texte, couleur_fond, couleur_texte, couleur_point):
    return (
        f"<span style='display:inline-flex;align-items:center;gap:6px;"
        f"background:{couleur_fond};color:{couleur_texte};"
        f"font-size:0.82rem;font-weight:600;padding:0.3rem 0.9rem;"
        f"border-radius:20px;margin-right:8px;'>"
        f"<span style='width:8px;height:8px;border-radius:50%;"
        f"background:{couleur_point};display:inline-block;'></span>"
        f"{texte}</span>"
    )


def tag(mot):
    return (f"<span style='background:#fdf8e8;color:#7A5C00;border-radius:10px;"
            f"padding:2px 9px;font-size:0.78rem;font-weight:600;"
            f"margin:2px 4px 2px 0;display:inline-block;'>{mot}</span>")
