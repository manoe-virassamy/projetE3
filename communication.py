"""
Chatbot interactif - Escalade adaptée pour personnes aveugles et malvoyantes
=============================================================================
AUDIO COMPLET : Le chatbot écoute ta voix ET répond à haute voix.

NOUVEAUTÉ — MODE MICRO CONTINU :
  Le chatbot écoute en boucle automatiquement, sans appuyer sur Entrée.
  Il attend ta voix, transcrit, répond à voix haute, puis réécoute.
  Dis "au revoir" pour terminer.

Installation (une seule fois) :
  pip install SpeechRecognition pyttsx3 pyaudio

Sur Linux si pyaudio échoue :
  sudo apt install portaudio19-dev python3-pyaudio
  pip install SpeechRecognition pyttsx3 pyaudio

Sur macOS :
  brew install portaudio
  pip install SpeechRecognition pyttsx3 pyaudio
"""

import re
import sys
import os
import io
import json
import platform
import subprocess
import unicodedata
from typing import Optional

# Chemin du modèle Vosk (même dossier que ce fichier)
_VOSK_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "vosk-model-small-fr-0.22")
_vosk_model = None   # chargé une seule fois à la première utilisation


def _get_vosk_model():
    global _vosk_model
    if _vosk_model is None:
        import vosk
        vosk.SetLogLevel(-1)
        _vosk_model = vosk.Model(_VOSK_MODEL_PATH)
    return _vosk_model


# ============================================================
#  MOTEUR TEXT-TO-SPEECH (voix de sortie)
# ============================================================

class MoteurVocal:
    """Lit le texte à haute voix. Détecte automatiquement le meilleur moteur."""

    def __init__(self):
        self.moteur  = None
        self.methode = None
        self._initialiser()

    def _initialiser(self):
        # 1. pyttsx3 (tous OS — priorité)
        # On teste juste que pyttsx3 fonctionne ; l'engine est recréé dans chaque
        # appel à dire() pour être thread-safe (COM/SAPI5 n'est pas réentrant).
        try:
            import pyttsx3
            m = pyttsx3.init()
            m.stop()
            self.methode = "pyttsx3"
            return
        except Exception:
            pass

        # 2. macOS → say
        if platform.system() == "Darwin":
            try:
                subprocess.run(["say", "--version"], capture_output=True, check=True)
                self.methode = "macos"
                return
            except Exception:
                pass

        # 3. Windows → PowerShell
        if platform.system() == "Windows":
            self.methode = "windows"
            return

        # 4. Linux → espeak-ng / espeak
        for cmd in ("espeak-ng", "espeak"):
            try:
                subprocess.run([cmd, "--version"], capture_output=True, check=True)
                self.methode = cmd
                return
            except Exception:
                pass

        self.methode = None

    def _nettoyer(self, texte: str) -> str:
        texte = re.sub(r"\s+", " ", texte).strip()
        texte = re.sub(
            r"[\U00010000-\U0010ffff\U0001F600-\U0001F64F"
            r"\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            r"\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]+",
            "", texte, flags=re.UNICODE
        )
        texte = re.sub(r"[•→←↑↓]", "", texte)
        return texte.strip()

    def dire(self, texte: str) -> None:
        if not texte or not self.methode:
            return
        t = self._nettoyer(texte)
        if not t:
            return
        try:
            if self.methode == "pyttsx3":
                import pyttsx3
                m = pyttsx3.init()
                m.setProperty("rate", 155)
                m.setProperty("volume", 1.0)
                for v in m.getProperty("voices"):
                    nom      = v.name.lower()
                    lang_raw = v.languages[0] if v.languages else ""
                    lang     = (lang_raw.decode("utf-8", errors="ignore")
                                if isinstance(lang_raw, bytes) else str(lang_raw)).lower()
                    if "fr" in lang or "french" in nom:
                        m.setProperty("voice", v.id)
                        break
                m.say(t)
                m.runAndWait()
                m.stop()
            elif self.methode == "macos":
                subprocess.run(["say", "-r", "155", "-v", "Amelie", t],
                               capture_output=True)
            elif self.methode == "windows":
                ps = (
                    "Add-Type -AssemblyName System.Speech;"
                    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                    "$s.Rate=0;$s.Volume=100;"
                    "try{$s.SelectVoiceByHints('fr-FR')}catch{};"
                    f"$s.Speak({t!r});$s.Dispose()"
                )
                subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                                "-Command", ps], capture_output=True)
            elif self.methode in ("espeak-ng", "espeak"):
                subprocess.run([self.methode, "-v", "fr", "-s", "145", t],
                               capture_output=True)
        except Exception as e:
            print(f"  [Audio sortie] Erreur : {e}", file=sys.stderr)

    def disponible(self) -> bool:
        return self.methode is not None

    def info(self) -> str:
        return f"Moteur vocal : {self.methode}" if self.methode \
               else "Aucun moteur vocal (pip install pyttsx3)"


# ============================================================
#  RECONNAISSANCE VOCALE (voix d'entrée)
# ============================================================

class EcouteurVocal:
    """
    Écoute le micro et retourne le texte reconnu.
    Deux modes :
      - ecouter()         → écoute unique (appui Entrée requis)
      - ecouter_continu() → boucle automatique, retourne dès qu'une phrase est captée
    """

    def __init__(self):
        self.sr                  = None
        self.disponible          = False   # micro serveur (pyaudio) — CLI uniquement
        self.disponible_navigateur = False # transcription de WAV envoyés par le navigateur
        self.derniere_erreur     = None    # message d'erreur lisible pour l'UI
        self._initialiser()

    def _initialiser(self):
        try:
            import speech_recognition as sr
            self.sr = sr
            self.disponible_navigateur = True
        except ImportError as e:
            print(f"  [Micro] Module manquant : {e}", file=sys.stderr)
            print("  → pip install SpeechRecognition", file=sys.stderr)
            return

        try:
            import pyaudio  # noqa — vérifie juste la présence
            self.disponible = True
        except ImportError as e:
            print(f"  [Micro serveur] pyaudio absent (mode CLI uniquement indisponible) : {e}", file=sys.stderr)

    # ----------------------------------------------------------
    #  Écoute unique (utilisée en mode Entrée)
    # ----------------------------------------------------------
    def ecouter(self, vocal_out: "MoteurVocal") -> Optional[str]:
        """Écoute une seule phrase et retourne le texte, ou None."""
        if not self.disponible:
            return None

        sr  = self.sr
        rec = sr.Recognizer()
        rec.energy_threshold         = 300   # seuil fixe bas — capte la voix sans calibration dynamique
        rec.dynamic_energy_threshold = False
        rec.pause_threshold          = 0.8

        print("  [Micro] J'écoute... (parlez maintenant)")

        self.derniere_erreur = None
        try:
            with sr.Microphone() as source:
                try:
                    audio = rec.listen(source, timeout=8, phrase_time_limit=15)
                except sr.WaitTimeoutError:
                    self.derniere_erreur = "Aucune voix détectée. Parlez plus fort ou vérifiez votre micro."
                    return None
        except OSError as e:
            self.derniere_erreur = f"Microphone inaccessible : {e}\nVérifiez qu'il est branché et autorisé dans Windows."
            return None

        return self._reconnaitre(rec, audio)

    # ----------------------------------------------------------
    #  Écoute CONTINUE — NOUVEAU
    # ----------------------------------------------------------
    def ecouter_continu(self, vocal_out: "MoteurVocal") -> Optional[str]:
        """
        Écoute en boucle sans intervention de l'utilisateur.
        Retourne la phrase reconnue dès qu'elle est captée,
        ou None si l'utilisateur fait Ctrl+C.

        Différences avec ecouter() :
          - Pas de timeout : attend indéfiniment que quelqu'un parle.
          - phrase_time_limit réduit à 12 s pour éviter les captures trop longues.
          - Affiche "En attente..." pour signaler que le micro est ouvert.
        """
        if not self.disponible:
            return None

        sr  = self.sr
        rec = sr.Recognizer()
        rec.pause_threshold          = 0.9   # réaction un peu plus vive
        rec.dynamic_energy_threshold = True

        print("\n  [Micro] En attente de ta voix... (parle quand tu veux)")

        try:
            with sr.Microphone() as source:
                rec.adjust_for_ambient_noise(source, duration=0.4)
                try:
                    # timeout=None → attend sans limite jusqu'à ce qu'une voix soit détectée
                    audio = rec.listen(source, timeout=None, phrase_time_limit=12)
                except KeyboardInterrupt:
                    return None
        except OSError as e:
            print(f"  [Micro] Impossible d'accéder au microphone : {e}", file=sys.stderr)
            return None

        texte = self._reconnaitre(rec, audio)
        if texte:
            print(f"  [Micro] Tu as dit : « {texte} »")
        return texte

    # ----------------------------------------------------------
    #  Moteur de reconnaissance commun
    # ----------------------------------------------------------
    def _reconnaitre(self, rec, audio) -> Optional[str]:
        sr = self.sr

        # Tentative 1 : Vosk hors-ligne (prioritaire si le modèle est présent)
        if os.path.exists(_VOSK_MODEL_PATH):
            try:
                import vosk
                model = _get_vosk_model()
                raw   = audio.get_raw_data(convert_rate=16000, convert_width=2)
                kaldi = vosk.KaldiRecognizer(model, 16000)
                kaldi.AcceptWaveform(raw)
                texte = json.loads(kaldi.FinalResult()).get("text", "").strip()
                if texte:
                    return texte
                self.derniere_erreur = "Parole non comprise. Parlez plus fort et plus distinctement."
                return None
            except Exception as e:
                self.derniere_erreur = f"Erreur Vosk : {e}"
                return None

        # Tentative 2 : Google (en ligne, si pas de modèle Vosk local)
        try:
            texte = rec.recognize_google(audio, language="fr-FR")
            return texte
        except sr.UnknownValueError:
            self.derniere_erreur = "Parole non comprise. Parlez plus clairement et plus fort."
            return None
        except Exception:
            self.derniere_erreur = "Reconnaissance vocale indisponible (Google inaccessible, modèle Vosk absent)."
            return None

    def info(self) -> str:
        if self.disponible:
            return "Reconnaissance vocale : SpeechRecognition + Google (fr-FR)"
        return ("Reconnaissance vocale inactive.\n"
                "  → Pour l'activer : pip install SpeechRecognition pyaudio")

    # ----------------------------------------------------------
    #  Transcription d'un WAV envoyé par le navigateur (st.audio_input)
    # ----------------------------------------------------------
    def transcrire_wav(self, wav_bytes: bytes) -> Optional[str]:
        """Transcrit un enregistrement WAV reçu du navigateur (PC ou téléphone).
        Ne dépend pas de pyaudio — utilisable même sans micro serveur."""
        if not self.disponible_navigateur:
            return None

        sr  = self.sr
        rec = sr.Recognizer()
        self.derniere_erreur = None

        try:
            with sr.AudioFile(io.BytesIO(wav_bytes)) as source:
                audio = rec.record(source)
        except Exception as e:
            self.derniere_erreur = f"Audio illisible : {e}"
            return None

        return self._reconnaitre(rec, audio)


# ============================================================
#  BASE DE CONNAISSANCES
# ============================================================

REPONSES = [
    {
        "mots_cles": ["échauffement", "echauffement", "chauffer", "préparation", "preparation"],
        "reponse": (
            "Fais quelques rotations des épaules, poignets et chevilles.\n"
            "Commence par des voies faciles pour activer les muscles."
        )
    },
    {
        "mots_cles": ["descente", "redescendre", "descendre", "rappel", "moulinette"],
        "reponse": (
            "Préviens ton assureur avant de descendre.\n"
            "Garde les jambes légèrement fléchies et signale quand tu touches le sol."
        )
    },
    {
        "mots_cles": ["douleur", "doigt", "tendon", "blessure", "mal", "bobo"],
        "reponse": (
            "Stop ! Arrête-toi et redescends.\n"
            "Ne force jamais sur une douleur vive."
        )
    },
    {
        "mots_cles": ["technique", "position", "équilibre", "equilibre"],
        "reponse": (
            "Grimpe avec les jambes, elles sont plus puissantes que les bras.\n"
            "Garde les bras détendus pour économiser ton énergie."
        )
    },
    {
        "mots_cles": ["sensation", "toucher", "tactile", "explorer", "palper"],
        "reponse": (
            "Avant chaque mouvement, explore la zone à portée de main.\n"
            "Tes mains et tes pieds sont tes yeux sur le mur."
        )
    },
    {
        "mots_cles": ["fatigue", "repos", "pause", "récupération", "recuperation"],
        "reponse": (
            "Prends des pauses régulières et hydrate-toi.\n"
            "Si tes avant-bras sont congestionnés, repose-toi avant de repartir."
        )
    },
    {
        "mots_cles": ["peur", "vertige", "stress", "confiance"],
        "reponse": (
            "concentre-toi sur ce que tu sens sous tes mains et tes pieds."
            "Respire calmement. La confiance vient avec la pratique."
        )
    },
    {
        "mots_cles": ["chute", "tomber", "vol", "tombe"],
        "reponse": (
            "Préviens ton assureur avant de lâcher.\n"
            "Écarte-toi du mur avec les pieds et garde les jambes légèrement fléchies."
        )
    },
    {
        "mots_cles": ["lecture", "voie", "itinéraire", "itineraire"],
        "reponse": (
            "Demander à l'assureur de décrire la voie verbalement et construire un plan mental."
            "Repère les prises importantes : ça économise beaucoup d'énergie."
        )
    },
    {
        "mots_cles": ["magnésie", "magnesie", "mains", "adhérence", "adherence"],
        "reponse": (
            "Utilise la magnésie avec modération.\n"
            "La précision des placements compte souvent plus que la force."
        )
    },
    {
        "mots_cles": ["débutant", "debutant", "commencer", "première fois", "premiere fois"],
        "reponse": (
            "Concentre-toi sur les mouvements simples et l'équilibre.\n"
            "N'hésite pas à demander conseil aux encadrants. Chacun progresse à son rythme."
        )
    },
    {
        "mots_cles": ["matériel", "materiel", "baudrier", "corde"],
        "reponse": (
            "Contrôle baudrier, corde et système d'assurage avant chaque séance.\n"
            "En cas de doute, demande vérification à un encadrant."
        )
    },
    {
        "mots_cles": ["performance", "progresser", "progression", "niveau"],
        "reponse": (
            "Travaille des voies légèrement au-dessus de ton niveau.\n"
            "La technique est souvent plus importante que la force brute."
        )
    },
    {
        "mots_cles": ["combien", "reste", "finir", "fin"],
        "reponse": (
            "Il vous reste ... de prises.\n"
            "Vous pouvez le faire{prenom} !"
        )
    },
    {
        "mots_cles": ["bonjour", "salut", "hello", "bonsoir", "coucou"],
        "reponse": (
            "Bonjour{prenom} ! Je suis ton assistant escalade pour les personnes aveugles et malvoyantes.\n"
            "Pose-moi ta question sur la sécurité, l'équipement, les techniques, ou les associations."
        )
    },
    {
        "mots_cles": ["qui es-tu", "qui es tu", "c'est quoi", "tu fais quoi", "aide", "help"],
        "reponse": (
            "Je suis un assistant spécialisé dans l'escalade adaptée.\n"
            "Je t'aide sur la sécurité, les techniques, l'équipement et la communication avec ton assureur.\n"
            "Et si ma réponse ne te convient pas, tu peux toujours discuter avec ton assureur et lui demander conseil."
        )
    },
    {
        "mots_cles": ["sécurité", "securite", "danger", "risque", "sûr", "sur"],
        "reponse": (
            "Conviens d'un code vocal clair avec ton assureur : DROITE, GAUCHE, HAUT, BAS.\n"
            "Vérifie toujours le baudrier et les noeuds avant de grimper.\n"
            "La communication est la clé de la sécurité !"
        )
    },
    {
        "mots_cles": ["équipement", "equipement", "matériel", "materiel", "chaussures", "baudrier", "corde", "acheter"],
        "reponse": (
            "Baudrier avec boucles en relief, chaussures légèrement serrées, la magnésie est optionel.\n"
            "Un casque est fortement conseillé pour les débutants."
        )
    },
    {
        "mots_cles": ["assureur", "communiquer", "communication", "guider", "guidage", "instructions", "verbal", "code"],
        "reponse": (
            "Mettez-vous d'accord sur un code vocal avant de grimper.\n"
            "Directions : DROITE, GAUCHE, HAUT, BAS.\n"
            "Distances : PROCHE (< 20 cm), MOYEN (< 50 cm), LOIN.\n"
            "Sécurité : STOP pour ne plus bouger, OK DESCEND pour redescendre."
        )
    },
    {
        "mots_cles": ["technique", "grimper", "comment monter", "prises", "pied", "main", "mouvement", "déplacement"],
        "reponse": (
            "Explore à la main avant chaque mouvement.\n"
            "Place tes pieds en premier, garde trois appuis sur le mur.\n"
        )
    },
    {
        "mots_cles": ["orientation", "repère", "repere", "carte", "position", "où je suis", "situer", "mur"],
        "reponse": (
            "Palpe les bords du mur pour t'ancrer au départ.\n"
            "L'assureur peut t'indiquer ta hauteur et les prises restantes.\n"
            "Demande au staff de t'orienter avant de commencer."
        )
    },
    {
        "mots_cles": ["association", "club", "fédération", "federation", "handisport", "adapté", "adapte", "handicap"],
        "reponse": (
            "Handisport France : handisport.org\n"
            "FFME commission Escalade Handisport : ffme.fr\n"
            "AVH : avh.asso.fr\n"
            "Beaucoup de salles ont des créneaux adaptés, renseigne-toi !"
        )
    },
    {
        "mots_cles": ["première fois", "premiere fois", "debut", "débuter", "commencer", "débutant", "novice", "jamais grimpé"],
        "reponse": (
            "Commencez par le bloc et définissez votre code vocal avant de poser les mains.\n"
            "Bonne première grimpe !"
        )
    },
    {
        "mots_cles": ["vocabulaire", "mot", "terme", "jug", "réglette", "reglette", "bombe", "pince", "dégaine", "degaine", "nœud", "noeud"],
        "reponse": (
            "JUG : grosse prise en forme de poignée.\n"
            "RÉGLETTE : prise plate et fine.\n"
            "BOMBE : prise ronde qu'on enserre.\n"
            "PINCE : serrée entre pouce et doigts.\n"
            "BLOC : mur bas sans corde. MOULINETTE : corde déjà en haut."
        )
    },
    {
        "mots_cles": ["droit", "accessibilité", "accessibilite", "loi", "discrimination", "accès", "acces", "tarif"],
        "reponse": (
            "La loi du 11 février 2005 garantit l'accès aux établissements sportifs.\n"
            "En cas de refus, contacte le Défenseur des Droits : 0 809 849 849.\n"
            "Demande le tarif handisport en salle."
        )
    },
    {
        "mots_cles": ["au revoir", "bye", "à bientôt", "a bientot", "merci", "ciao", "tchao", "quitter", "fin", "arrêter", "arreter"],
        "reponse": (
            "À bientôt{prenom} !\n"
        )
    },
]

REPONSE_DEFAUT = (
    "Désolé{prenom}, je n'ai pas compris ta question.\n"
    "Parle-moi de : sécurité, équipement, communication, technique, orientation, association, ou vocabulaire"
)


# ============================================================
#  MOTEUR DE CORRESPONDANCE
# ============================================================

def normaliser(texte: str) -> str:
    texte = texte.lower().strip()
    texte = unicodedata.normalize("NFD", texte)
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def trouver_reponse(message: str, username: str = "", niveau: str = "Débutant") -> str:
    msg_norm = normaliser(message)
    meilleur, meilleure = 0, REPONSE_DEFAUT
    for entree in REPONSES:
        score = sum(1 for m in entree["mots_cles"] if normaliser(m) in msg_norm)
        if score > meilleur:
            meilleur, meilleure = score, entree["reponse"]
    prenom = username.strip()
    reponse = meilleure.replace("{prenom}", f" {prenom}" if prenom else "")
    if niveau == "Débutant" and meilleure == REPONSE_DEFAUT:
        reponse += "\nN'hésite pas à reformuler ou à poser une question plus précise !"
    return reponse


# ============================================================
#  INTERFACE PRINCIPALE
# ============================================================

def choisir_mode(vocal: MoteurVocal, ecouteur: EcouteurVocal) -> str:
    """
    Affiche un menu de démarrage et retourne le mode choisi :
      'continu'  → micro automatique, pas d'Entrée requise  (NOUVEAU)
      'micro'    → micro sur Entrée
      'texte'    → clavier uniquement
    """
    print("=" * 60)
    print("  ASSISTANT ESCALADE ADAPTÉ")
    print("  Pour les personnes aveugles et malvoyantes")
    print("=" * 60)
    print(f"  {vocal.info()}")
    print(f"  {ecouteur.info()}")
    print("=" * 60)
    print()

    if not ecouteur.disponible:
        print("  Reconnaissance vocale non disponible.")
        print("  Démarrage automatique en MODE TEXTE.\n")
        vocal.dire("Mode texte activé. Tapez votre question.")
        return "texte"

    vocal.dire(
        "Bonjour. Choisissez votre mode. "
        "Tapez 1 pour le micro continu sans Entrée, "
        "2 pour le micro avec Entrée, "
        "ou 3 pour le clavier."
    )

    print("  Comment voulez-vous interagir ?")
    print()
    print("    1  →  MICRO CONTINU   (parle, le chatbot t'écoute en permanence)")
    print("    2  →  MICRO + ENTREE  (appuie sur Entrée pour activer le micro)")
    print("    3  →  CLAVIER         (tape les questions)")
    print()

    while True:
        try:
            choix = input("  Votre choix (1, 2 ou 3) : ").strip()
        except (EOFError, KeyboardInterrupt):
            choix = "3"

        if choix == "1":
            print()
            print("  MODE MICRO CONTINU activé.")
            print("  Parle normalement, le chatbot t'écoute apres chaque reponse.")
            print("  Dis 'au revoir' pour terminer.  Ctrl+C pour forcer l'arret.")
            print()
            vocal.dire(
                "Mode micro continu activé. "
                "Je t'écoute dès maintenant. Parle quand tu veux."
            )
            return "continu"

        elif choix == "2":
            print()
            print("  MODE MICRO + ENTREE activé.")
            print("  Appuie sur Entree pour activer le micro, ou tape directement.")
            print("  Dis ou tape 'au revoir' pour terminer.")
            print()
            vocal.dire("Mode micro activé. Appuyez sur Entrée pour parler.")
            return "micro"

        elif choix == "3":
            print()
            print("  MODE CLAVIER activé.")
            print("  Tape tes questions et appuie sur Entree.")
            print("  Tape 'au revoir' pour terminer.")
            print()
            vocal.dire("Mode clavier activé. Tapez votre question.")
            return "texte"

        else:
            print("  Entrez 1, 2 ou 3.")
            vocal.dire("Entrez 1, 2 ou 3.")


def obtenir_message(mode: str, ecouteur: EcouteurVocal, vocal: MoteurVocal) -> Optional[str]:
    """
    Récupère le prochain message selon le mode.

    'continu' → appelle ecouter_continu() sans aucune interaction clavier.
    'micro'   → Entrée vide = écoute, sinon utilise le texte tapé.
    'texte'   → saisie clavier pure.

    Retourne None si l'utilisateur fait Ctrl+C (signal d'arrêt).
    """

    # ── MODE CONTINU ─────────────────────────────────────────
    if mode == "continu":
        try:
            texte = ecouteur.ecouter_continu(vocal)
        except KeyboardInterrupt:
            return None
        # None = Ctrl+C dans ecouter_continu → signal d'arrêt
        return texte   # peut être None (Ctrl+C) ou str (phrase reconnue ou "")

    # ── MODE MICRO + ENTREE ───────────────────────────────────
    if mode == "micro":
        try:
            saisie = input("Vous [ENTREE=micro / ou tapez] : ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if saisie == "":
            if not ecouteur.disponible:
                msg = "Microphone non disponible. Tapez votre question."
                print(f"\n  {msg}\n")
                vocal.dire(msg)
                return ""
            vocal.dire("Je vous écoute.")
            try:
                message_vocal = ecouteur.ecouter(vocal)
            except Exception as e:
                print(f"  [Micro] Erreur inattendue : {e}", file=sys.stderr)
                vocal.dire("Erreur du microphone. Vérifiez qu'il est bien branché.")
                return ""
            if message_vocal:
                return message_vocal
            vocal.dire("Je n'ai pas entendu. Réessayez ou tapez votre question.")
            return ""

        return saisie

    # ── MODE TEXTE ────────────────────────────────────────────
    try:
        return input("Vous : ").strip()
    except (EOFError, KeyboardInterrupt):
        return None


# ============================================================
#  BOUCLE PRINCIPALE
# ============================================================

def lancer_chatbot():
    vocal    = MoteurVocal()
    ecouteur = EcouteurVocal()

    mode = choisir_mode(vocal, ecouteur)

    while True:
        # ── Récupération du message ───────────────────────────
        try:
            message = obtenir_message(mode, ecouteur, vocal)
        except KeyboardInterrupt:
            message = None

        # Ctrl+C / EOF → sortie propre
        if message is None:
            msg_fin = "À bientôt !"
            print(f"\nChatbot : {msg_fin}\n")
            vocal.dire(msg_fin)
            break

        # Rien capté (silence, micro raté) → reboucle sans répondre
        if not message:
            continue

        # ── Commande spéciale : changer de mode ──────────────
        if normaliser(message) in ("changer mode", "changer le mode", "switch"):
            if mode == "continu":
                mode = "texte"
                msg  = "Mode clavier activé."
            elif mode == "micro":
                mode = "continu"
                msg  = "Mode micro continu activé. Parle quand tu veux."
            else:
                mode = "continu" if ecouteur.disponible else "texte"
                msg  = "Mode micro continu activé." if ecouteur.disponible \
                       else "Micro indisponible, mode clavier conservé."
            print(f"\nChatbot : {msg}\n")
            vocal.dire(msg)
            continue

        # ── Détection sortie ─────────────────────────────────
        if normaliser(message) in {normaliser(m) for m in MOTS_SORTIE}:
            reponse = trouver_reponse(message)
            print(f"\nChatbot : {reponse}\n")
            vocal.dire(reponse)
            break

        # ── Réponse normale ───────────────────────────────────
        reponse = trouver_reponse(message)
        print(f"\nChatbot : {reponse}\n")
        vocal.dire(reponse)

        # En mode continu : petite pause visuelle avant la prochaine écoute
        if mode == "continu":
            print("  ─" * 20)


# ============================================================
#  POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    lancer_chatbot()