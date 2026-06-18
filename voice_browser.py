"""Synthèse vocale côté navigateur.

Génère l'audio avec une voix neuronale gratuite (Microsoft Edge, via le paquet
edge-tts) côté serveur, puis l'envoie au navigateur de l'utilisateur (PC ou
téléphone) pour lecture — nettement moins robotique que les voix
`window.speechSynthesis` embarquées sur les appareils mobiles. Si edge-tts est
indisponible (paquet manquant ou pas d'accès Internet au moment de l'appel), on
retombe automatiquement sur la voix du navigateur.
"""
import asyncio
import base64
import json

import streamlit as st
import streamlit.components.v1 as components

try:
    import edge_tts
    _EDGE_TTS_DISPONIBLE = True
except ImportError:
    _EDGE_TTS_DISPONIBLE = False

VOIX_NEURONALE = "fr-FR-DeniseNeural"


@st.cache_data(show_spinner=False, max_entries=50)
def _generer_mp3(texte: str, voix: str = VOIX_NEURONALE) -> bytes:
    async def _go() -> bytes:
        morceaux = bytearray()
        communicate = edge_tts.Communicate(texte, voix)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                morceaux.extend(chunk["data"])
        return bytes(morceaux)

    return asyncio.run(_go())


def _audio_data_uri(texte: str) -> str | None:
    """Génère l'audio neuronal et le renvoie en data URI, ou None si indisponible
    (déclenche alors le repli vers la voix du navigateur côté JS)."""
    if not _EDGE_TTS_DISPONIBLE:
        return None
    try:
        mp3 = _generer_mp3(texte)
    except Exception:
        return None
    if not mp3:
        return None
    return "data:audio/mpeg;base64," + base64.b64encode(mp3).decode("ascii")


def _lecture_js(data_uri: str | None, texte_js: str, lang: str, rate: float, auto: bool) -> str:
    """Code JS de lecture : voix neuronale (data URI) si dispo, sinon voix du navigateur."""
    if data_uri:
        verbe = "automatique " if auto else ""
        return f"""
          const audio = new Audio({json.dumps(data_uri)});
          audio.onplay  = function() {{ setStatus("🔊 Lecture en cours…"); }};
          audio.onended = function() {{ setStatus("✅ Lecture terminée"); }};
          audio.onerror = function() {{ setStatus("⚠️ Erreur de lecture audio"); }};
          audio.play().catch(function(e) {{ setStatus("⚠️ Lecture {verbe}bloquée"); }});
        """
    return f"""
          if (!('speechSynthesis' in window)) {{
            setStatus("⚠️ Synthèse vocale indisponible");
            return;
          }}
          window.speechSynthesis.cancel();
          const u = new SpeechSynthesisUtterance({texte_js});
          u.lang = "{lang}";
          u.rate = {rate};
          const voix = window.speechSynthesis.getVoices();
          const voixFr = voix.find(v => v.lang && v.lang.toLowerCase().startsWith("fr"));
          if (voixFr) u.voice = voixFr;
          u.onstart = function() {{ setStatus("🔊 Lecture en cours…"); }};
          u.onend   = function() {{ setStatus("✅ Lecture terminée"); }};
          u.onerror = function(e) {{ setStatus("⚠️ Erreur : " + e.error); }};
          window.speechSynthesis.speak(u);
        """


def speak_browser(texte: str, lang: str = "fr-FR", rate: float = 1.0, debug: bool = False) -> None:
    """Tente une lecture automatique (sans clic) dès le chargement du composant.

    Fonctionne en général sur PC ; les navigateurs mobiles bloquent souvent la
    lecture automatique avec son — `speak_button_html` reste le moyen fiable
    sur téléphone.
    """
    if not texte:
        return

    data_uri = _audio_data_uri(texte)
    texte_js = json.dumps(texte)
    lecture_js = _lecture_js(data_uri, texte_js, lang, rate, auto=True)

    html = f"""
    <div id="tts-status" style="font-size:0.75rem;color:#888;font-family:sans-serif;"></div>
    <script>
      (function() {{
        const statusEl = document.getElementById("tts-status");
        function setStatus(msg) {{ if (statusEl) statusEl.textContent = msg; }}
        try {{
          {lecture_js}
        }} catch (e) {{
          setStatus("⚠️ Exception JS : " + e.message);
        }}
      }})();
    </script>
    """
    components.html(html, height=20 if debug else 0, width=None if debug else 0)


def speak_button_html(texte: str, label: str = "🔊 Écouter la réponse",
                       lang: str = "fr-FR", rate: float = 1.0) -> None:
    """Bouton HTML autonome qui lit `texte` à voix haute au clic, sans aller-retour
    Streamlit (nécessaire sur Safari/iOS : la lecture doit démarrer de façon
    synchrone dans le geste utilisateur, ce qu'un st.button ne permet pas).
    """
    if not texte:
        return

    data_uri = _audio_data_uri(texte)
    texte_js = json.dumps(texte)
    lecture_js = _lecture_js(data_uri, texte_js, lang, rate, auto=False)

    html = f"""
    <div style="font-family:sans-serif;">
      <button id="speak-btn" style="
          width:100%;padding:0.55rem 1rem;border-radius:8px;border:1.5px solid #C9A020;
          background:rgba(201,160,32,0.14);color:#7A5C00;font-weight:700;font-size:0.85rem;
          cursor:pointer;">{label}</button>
      <div id="speak-status" style="font-size:0.75rem;color:#888;margin-top:4px;min-height:1em;"></div>
    </div>
    <script>
      (function() {{
        const btn = document.getElementById("speak-btn");
        const statusEl = document.getElementById("speak-status");
        function setStatus(msg) {{ if (statusEl) statusEl.textContent = msg; }}
        btn.addEventListener("click", function() {{
          try {{
            {lecture_js}
          }} catch (e) {{
            setStatus("⚠️ Exception JS : " + e.message);
          }}
        }});
      }})();
    </script>
    """
    components.html(html, height=72)
