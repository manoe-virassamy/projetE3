"""
Chatbot interactif - Escalade adaptée pour personnes aveugles et malvoyantes
=============================================================================
AUDIO COMPLET : Le chatbot écoute ta voix ET répond à haute voix.

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
import platform
import subprocess
import threading
import unicodedata
from typing import Optional

# ============================================================
#  MOTEUR TEXT-TO-SPEECH (voix de sortie)
# ============================================================

class MoteurVocal:
    """Lit le texte à haute voix. Détecte automatiquement le meilleur moteur."""

    def __init__(self):
        self.moteur   = None
        self.methode  = None
        self._initialiser()

    def _initialiser(self):
        # 1. pyttsx3 (tous OS)
        try:
            import pyttsx3
            m = pyttsx3.init()
            m.setProperty("rate", 155)
            m.setProperty("volume", 1.0)
            for v in m.getProperty("voices"):
                nom = v.name.lower()
                lang = (v.languages[0] if v.languages else b"").decode("utf-8", errors="ignore").lower()
                if "fr" in lang or "french" in nom:
                    m.setProperty("voice", v.id)
                    break
            self.moteur  = m
            self.methode = "pyttsx3"
            return
        except Exception:
            pass

        # 2. macOS  → say
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
                self.moteur.say(t)
                self.moteur.runAndWait()
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
                subprocess.run(["powershell","-NoProfile","-WindowStyle","Hidden",
                                "-Command", ps], capture_output=True)
            elif self.methode in ("espeak-ng","espeak"):
                subprocess.run([self.methode,"-v","fr","-s","145", t],
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
    Utilise Google Speech Recognition (gratuit, nécessite Internet)
    avec repli sur reconnaissance hors-ligne via Vosk si disponible.
    """

    def __init__(self):
        self.sr         = None   # module speech_recognition
        self.disponible = False
        self._initialiser()

    def _initialiser(self):
        try:
            import speech_recognition as sr
            # Vérifie aussi que pyaudio est accessible (nécessaire pour Microphone)
            import pyaudio
            self.sr         = sr
            self.disponible = True
        except ImportError as e:
            print(f"  [Micro] Module manquant : {e}", file=sys.stderr)
            print("  → pip install SpeechRecognition pyaudio", file=sys.stderr)

    def ecouter(self, vocal_out: "MoteurVocal") -> Optional[str]:
        """
        Écoute le micro, retourne le texte détecté (str)
        ou None si rien n'a été capté / reconnu.
        """
        if not self.disponible:
            return None

        sr = self.sr
        rec = sr.Recognizer()
        rec.pause_threshold          = 1.0   # secondes de silence avant fin
        rec.dynamic_energy_threshold = True

        print("  [Micro] J'écoute... (parlez maintenant)")

        try:
            with sr.Microphone() as source:
                # Calibration rapide du bruit ambiant
                rec.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = rec.listen(source, timeout=8, phrase_time_limit=15)
                except sr.WaitTimeoutError:
                    print("  [Micro] Aucune voix détectée (timeout).")
                    return None
        except OSError as e:
            # pyaudio installé mais aucun micro disponible sur le système
            print(f"  [Micro] Impossible d'accéder au microphone : {e}", file=sys.stderr)
            print("  → Vérifiez que votre micro est branché et autorisé.", file=sys.stderr)
            return None

        # Tentative 1 : Google (en ligne, meilleure précision)
        try:
            texte = rec.recognize_google(audio, language="fr-FR")
            print(f"  [Micro] Entendu : « {texte} »")
            return texte
        except sr.UnknownValueError:
            print("  [Micro] Parole non comprise.")
            return None
        except sr.RequestError:
            pass   # pas d'Internet → tenter hors-ligne

        # Tentative 2 : Vosk hors-ligne (si installé)
        try:
            texte = rec.recognize_vosk(audio, language="fr")
            print(f"  [Micro] (hors-ligne) Entendu : « {texte} »")
            return texte
        except Exception:
            print("  [Micro] Reconnaissance hors-ligne indisponible.")
            return None

    def info(self) -> str:
        if self.disponible:
            return "Reconnaissance vocale : SpeechRecognition + Google (fr-FR)"
        return ("Reconnaissance vocale inactive.\n"
                "  → Pour l'activer : pip install SpeechRecognition pyaudio")


# ============================================================
#  BASE DE CONNAISSANCES
# ============================================================

REPONSES = [

    {
        "mots_cles": ["bonjour", "salut", "hello", "bonsoir", "coucou"],
        "reponse": (
            "Bonjour et bienvenue ! 😊\n"
            "Je suis ton assistant escalade pour les personnes aveugles et malvoyantes.\n"
            "Je peux t'aider sur :\n"
            "  • La sécurité et l'équipement\n"
            "  • Comment communiquer avec ton assureur\n"
            "  • Les techniques de grimpe à l'aveugle\n"
            "  • L'orientation sur le mur\n"
            "  • Les droits et les associations\n"
            "Pose-moi ta question, je suis là ! 🧗"
        )
    },
    {
        "mots_cles": ["qui es-tu", "qui es tu", "c'est quoi", "tu fais quoi", "aide", "help"],
        "reponse": (
            "Je suis un assistant virtuel spécialisé dans l'escalade adaptée.\n"
            "Mon rôle est de t'accompagner dans ta pratique de l'escalade en salle\n"
            "lorsque tu es aveugle ou malvoyant.\n\n"
            "Tu peux me parler de sécurité, d'équipement, de techniques,\n"
            "de communication avec ton assureur, ou encore des associations. 🏔️"
        )
    },
    {
        "mots_cles": ["sécurité", "securite", "danger", "risque", "sûr", "sur"],
        "reponse": (
            "🔐 SÉCURITÉ — Points essentiels :\n\n"
            "Avant de grimper, palpe le mur à portée de main pour repérer les prises proches.\n"
            "Conviens avec ton assureur d'un code vocal clair : DROITE, GAUCHE, HAUT, BAS.\n"
            "Vérifie toujours ensemble le baudrier et les nœuds avant de commencer.\n"
            "Informe le staff de la salle de ton passage.\n\n"
            "La communication est la clé de la sécurité ! 🗣️"
        )
    },
    {
        "mots_cles": ["équipement", "equipement", "matériel", "materiel", "chaussures", "baudrier", "corde", "acheter"],
        "reponse": (
            "🎒 ÉQUIPEMENT recommandé :\n\n"
            "• Baudrier avec boucles en relief pour les reconnaître au toucher.\n"
            "• Chaussures d'escalade légèrement serrées pour maximiser les sensations.\n"
            "• Magnésie pour améliorer l'adhérence des mains.\n"
            "• Casque fortement conseillé pour les débutants. 🪖"
        )
    },
    {
        "mots_cles": ["assureur", "communiquer", "communication", "guider", "guidage", "instructions", "verbal", "code"],
        "reponse": (
            "🗣️ COMMUNICATION avec ton assureur :\n\n"
            "Mettez-vous d'accord sur un code vocal précis avant de grimper.\n\n"
            "Directions : DROITE, GAUCHE, HAUT, BAS.\n"
            "Distances : PROCHE moins de 20 cm, MOYEN jusqu'à 50 cm, LOIN au-delà.\n"
            "Type de prise : RÉGLETTE, JUG, BOMBE, PINCE.\n"
            "Sécurité : STOP pour ne plus bouger. OK DESCEND pour redescendre.\n\n"
            "Entraîne-toi à ce code à terre avant de grimper ! 💬"
        )
    },
    {
        "mots_cles": ["technique", "grimper", "comment monter", "prises", "pied", "main", "mouvement", "déplacement"],
        "reponse": (
            "🧗 TECHNIQUES de grimpe à l'aveugle :\n\n"
            "1. EXPLORATION TACTILE : explore la zone à portée de main avant chaque mouvement.\n"
            "2. PIEDS EN PREMIER : place tes pieds précisément, ils portent le corps.\n"
            "3. TROIS POINTS D'APPUI : garde toujours 3 membres sur le mur.\n"
            "4. RESPIRATION : expire à l'effort, inspire dans les positions stables.\n"
            "5. MÉMORISATION : construis mentalement une carte du mur en montant.\n"
            "6. ÉCOUTE DU CORPS : tes sensations sont tes meilleures alliées. 🤲"
        )
    },
    {
        "mots_cles": ["orientation", "repère", "repere", "carte", "position", "où je suis", "situer", "mur"],
        "reponse": (
            "🗺️ S'ORIENTER sur le mur :\n\n"
            "• Palpe les bords du mur pour t'ancrer au départ.\n"
            "• L'assureur t'indique ta hauteur et le nombre de prises restantes.\n"
            "• Méthode de la grille : imagine le mur en colonnes et lignes numérotées.\n"
            "• Certaines salles placent des reliefs tactiles comme repères.\n\n"
            "Demande au staff de t'orienter avant de commencer. 📍"
        )
    },
    {
        "mots_cles": ["association", "club", "fédération", "federation", "handisport", "adapté", "adapte", "handicap"],
        "reponse": (
            "🏢 ASSOCIATIONS et ressources utiles :\n\n"
            "• Handisport France : fédération officielle. www.handisport.org\n"
            "• FFME, commission Escalade Handisport. www.ffme.fr\n"
            "• AVH, Association Valentin Haüy. www.avh.asso.fr\n"
            "• Contacte la salle locale : beaucoup ont des créneaux adaptés. 📞"
        )
    },
    {
        "mots_cles": ["première fois", "premiere fois", "debut", "débuter", "commencer", "débutant", "novice", "jamais grimpé"],
        "reponse": (
            "🌟 TA PREMIÈRE SÉANCE :\n\n"
            "1. Appelle la salle à l'avance pour demander un moniteur formé.\n"
            "2. Arrive avec ton assureur et faites une visite tactile ensemble.\n"
            "3. Commencez par le bloc, le mur bas sans corde.\n"
            "4. Définissez votre code de communication avant de poser les mains.\n"
            "5. Commence à 1 mètre du sol, l'objectif c'est ressentir !\n\n"
            "Bonne première grimpe ! 🎉"
        )
    },
    {
        "mots_cles": ["difficile", "dur", "peur", "panique", "fatigué", "fatigue", "découragé", "décourage", "abandonner"],
        "reponse": (
            "💙 C'est normal de trouver ça difficile au début.\n\n"
            "Respire profondément avant chaque mouvement.\n"
            "Reste proche du sol, la confiance vient progressivement.\n"
            "Chaque centimètre gagné est une vraie victoire.\n\n"
            "Beaucoup de grimpeurs non-voyants atteignent des niveaux impressionnants.\n"
            "Continue ! 🌟"
        )
    },
    {
        "mots_cles": ["vocabulaire", "mot", "terme", "jug", "réglette", "reglette", "bombe", "pince", "dégaine", "degaine", "nœud", "noeud"],
        "reponse": (
            "📖 VOCABULAIRE de l'escalade :\n\n"
            "JUG : grosse prise facile, en forme de poignée.\n"
            "RÉGLETTE : prise plate et fine, juste pour les doigts.\n"
            "BOMBE : prise ronde qu'on enserre avec la main.\n"
            "PINCE : serrée entre le pouce et les doigts.\n"
            "BAUDRIER : harnais autour de la taille et des cuisses.\n"
            "NŒUD EN HUIT : nœud principal pour s'encorder.\n"
            "BLOC : mur bas sans corde. MOULINETTE : corde déjà en haut. 📚"
        )
    },
    {
        "mots_cles": ["droit", "accessibilité", "accessibilite", "loi", "discrimination", "accès", "acces", "tarif"],
        "reponse": (
            "⚖️ DROITS et accessibilité :\n\n"
            "La loi du 11 février 2005 garantit l'accès des personnes handicapées\n"
            "aux établissements sportifs en France.\n\n"
            "En cas de refus, contacte le Défenseur des Droits au 0 809 849 849.\n"
            "Demande le tarif handisport en salle, et renseigne-toi auprès de ta mutuelle. 🤝"
        )
    },
    {
        "mots_cles": ["au revoir", "bye", "à bientôt", "a bientot", "merci", "ciao", "tchao", "quitter", "fin", "arrêter", "arreter"],
        "reponse": (
            "À bientôt ! 🧗\n"
            "Bonne chance dans ta pratique de l'escalade.\n"
            "N'oublie pas : chaque prise conquise est une victoire !\n"
            "Reviens quand tu veux. 💪"
        )
    },
]

REPONSE_DEFAUT = (
    "Je n'ai pas bien compris ta question. 🤔\n"
    "Tu peux me parler de : sécurité, équipement, communication,\n"
    "technique, orientation, association, première fois, vocabulaire, ou droits.\n"
    "Reformule ta question ou répète un de ces mots-clés. 😊"
)

MOTS_SORTIE = {"quitter","quit","exit","bye","au revoir","a bientot",
               "à bientôt","fin","ciao","tchao","arrêter","arreter"}


# ============================================================
#  MOTEUR DE CORRESPONDANCE
# ============================================================

def normaliser(texte: str) -> str:
    texte = texte.lower().strip()
    texte = unicodedata.normalize("NFD", texte)
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def trouver_reponse(message: str) -> str:
    msg_norm = normaliser(message)
    meilleur, meilleure = 0, REPONSE_DEFAUT
    for entree in REPONSES:
        score = sum(1 for m in entree["mots_cles"] if normaliser(m) in msg_norm)
        if score > meilleur:
            meilleur, meilleure = score, entree["reponse"]
    return meilleure


# ============================================================
#  INTERFACE PRINCIPALE
# ============================================================

def choisir_mode(vocal: MoteurVocal, ecouteur: EcouteurVocal) -> str:
    """
    Affiche un menu de démarrage et retourne le mode choisi :
    'micro' ou 'texte'.
    Si la reconnaissance vocale n'est pas disponible, force le mode texte.
    """
    print("=" * 60)
    print("  🧗  ASSISTANT ESCALADE ADAPTÉ  🧗")
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

    # ── Menu de choix ────────────────────────────────────────
    vocal.dire(
        "Bonjour. Choisissez votre mode d'interaction. "
        "Tapez 1 pour utiliser le microphone, ou 2 pour taper au clavier."
    )

    print("  Comment voulez-vous interagir avec l'assistant ?")
    print()
    print("    1  →  🎤  MICROPHONE  (parler à voix haute)")
    print("    2  →  ⌨️   CLAVIER     (taper les questions)")
    print()

    while True:
        try:
            choix = input("  Votre choix (1 ou 2) : ").strip()
        except (EOFError, KeyboardInterrupt):
            choix = "2"

        if choix == "1":
            print()
            print("  MODE MICROPHONE activé.")
            print("  → Appuyez sur ENTRÉE pour activer le micro à chaque question.")
            print("  → Ou tapez directement si vous préférez.")
            print("  → Dites ou tapez 'au revoir' pour terminer.")
            print()
            vocal.dire("Mode microphone activé. Appuyez sur Entrée pour parler.")
            return "micro"

        elif choix == "2":
            print()
            print("  MODE CLAVIER activé.")
            print("  → Tapez vos questions et appuyez sur ENTRÉE.")
            print("  → Tapez 'au revoir' pour terminer.")
            print()
            vocal.dire("Mode clavier activé. Tapez votre question.")
            return "texte"

        else:
            print("  Entrez 1 pour le micro ou 2 pour le clavier.")
            vocal.dire("Entrez 1 pour le microphone ou 2 pour le clavier.")


def obtenir_message(mode: str, ecouteur: EcouteurVocal, vocal: MoteurVocal) -> Optional[str]:
    """
    Récupère le message selon le mode choisi.
    Mode 'micro'  : ENTRÉE vide → écoute micro, sinon utilise le texte tapé.
    Mode 'texte'  : saisie clavier uniquement.
    Retourne None en cas d'interruption (Ctrl+C).
    """
    try:
        if mode == "micro":
            saisie = input("Vous [ENTRÉE=micro / ou tapez] : ").strip()
        else:
            saisie = input("Vous : ").strip()
    except (EOFError, KeyboardInterrupt):
        return None

    # Mode micro + ENTRÉE vide → activation du micro
    if mode == "micro" and saisie == "":

        # ── CORRECTION 1 : vérifier la dispo avant d'appeler le micro ──
        if not ecouteur.disponible:
            msg = "Microphone non disponible. Tapez votre question ou vérifiez l'installation de pyaudio."
            print(f"\n  ⚠️  {msg}\n")
            vocal.dire(msg)
            return ""   # reboucle proprement

        vocal.dire("Je vous écoute.")

        # ── CORRECTION 2 : encadrer l'appel micro dans un try/except ──
        try:
            message_vocal = ecouteur.ecouter(vocal)
        except Exception as e:
            print(f"  [Micro] Erreur inattendue : {e}", file=sys.stderr)
            msg = "Erreur du microphone. Vérifiez qu'il est bien branché et réessayez."
            print(f"\n  ⚠️  {msg}\n")
            vocal.dire(msg)
            return ""   # reboucle proprement

        if message_vocal:
            return message_vocal

        # ── CORRECTION 3 : feedback clair quand rien n'est entendu ──
        msg = "Je n'ai pas entendu. Appuyez sur Entrée pour réessayer, ou tapez votre question."
        print(f"\n  ℹ️  {msg}\n")
        vocal.dire("Je n'ai pas entendu. Réessayez ou tapez votre question.")
        return ""   # reboucle, pas de sortie silencieuse

    return saisie


def lancer_chatbot():
    vocal    = MoteurVocal()
    ecouteur = EcouteurVocal()

    # ── Choix du mode au démarrage ───────────────────────────
    mode = choisir_mode(vocal, ecouteur)

    while True:
        message = obtenir_message(mode, ecouteur, vocal)

        if message is None:          # Ctrl+C / EOF
            msg_fin = "À bientôt !"
            print(f"\nChatbot : {msg_fin}\n")
            vocal.dire(msg_fin)
            break

        if not message:              # rien capté au micro → reboucle
            continue

        # Commande spéciale : changer de mode en cours de session
        if normaliser(message) in ("changer mode", "changer le mode", "switch"):
            if mode == "micro":
                mode = "texte"
                msg = "Mode clavier activé."
            else:
                mode = "micro"
                msg = "Mode microphone activé. Appuyez sur Entrée pour parler."
            print(f"\nChatbot : {msg}\n")
            vocal.dire(msg)
            continue

        if normaliser(message) in {normaliser(m) for m in MOTS_SORTIE}:
            reponse = trouver_reponse(message)
            print(f"\nChatbot : {reponse}\n")
            vocal.dire(reponse)
            break

        reponse = trouver_reponse(message)
        print(f"\nChatbot : {reponse}\n")
        vocal.dire(reponse)


# ============================================================
#  POINT D'ENTRÉE
# ============================================================

if __name__ == "__main__":
    lancer_chatbot()
