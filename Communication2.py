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
import platform
import subprocess
import unicodedata
from typing import Optional


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
        try:
            import pyttsx3
            m = pyttsx3.init()
            m.setProperty("rate", 155)
            m.setProperty("volume", 1.0)
            for v in m.getProperty("voices"):
                nom  = v.name.lower()
                lang = (v.languages[0] if v.languages else b"").decode("utf-8", errors="ignore").lower()
                if "fr" in lang or "french" in nom:
                    m.setProperty("voice", v.id)
                    break
            self.moteur  = m
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
        self.sr         = None
        self.disponible = False
        self._initialiser()

    def _initialiser(self):
        try:
            import speech_recognition as sr
            import pyaudio  # noqa — vérifie juste la présence
            self.sr         = sr
            self.disponible = True
        except ImportError as e:
            print(f"  [Micro] Module manquant : {e}", file=sys.stderr)
            print("  → pip install SpeechRecognition pyaudio", file=sys.stderr)

    # ----------------------------------------------------------
    #  Écoute unique (utilisée en mode Entrée)
    # ----------------------------------------------------------
    def ecouter(self, vocal_out: "MoteurVocal") -> Optional[str]:
        """Écoute une seule phrase et retourne le texte, ou None."""
        if not self.disponible:
            return None

        sr  = self.sr
        rec = sr.Recognizer()
        rec.pause_threshold          = 1.0
        rec.dynamic_energy_threshold = True

        print("  [Micro] J'écoute... (parlez maintenant)")

        try:
            with sr.Microphone() as source:
                rec.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = rec.listen(source, timeout=8, phrase_time_limit=15)
                except sr.WaitTimeoutError:
                    print("  [Micro] Aucune voix détectée (timeout).")
                    return None
        except OSError as e:
            print(f"  [Micro] Impossible d'accéder au microphone : {e}", file=sys.stderr)
            print("  → Vérifiez que votre micro est branché et autorisé.", file=sys.stderr)
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

        # Tentative 1 : Google (en ligne)
        try:
            texte = rec.recognize_google(audio, language="fr-FR")
            return texte
        except sr.UnknownValueError:
            print("  [Micro] Parole non comprise, réessaie.")
            return None
        except sr.RequestError:
            pass   # pas d'Internet → hors-ligne

        # Tentative 2 : Vosk (hors-ligne, si installé)
        try:
            texte = rec.recognize_vosk(audio, language="fr")
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
        "mots_cles": ["échauffement", "echauffement", "chauffer", "préparation", "preparation"],
        "reponse": (
            "ÉCHAUFFEMENT — Prépare ton corps.\n"
            "Effectue quelques mouvements des épaules, poignets et chevilles.\n"
            "Commence par des voies faciles pour activer les muscles progressivement.\n"
            "Un bon échauffement réduit le risque de blessure et améliore les performances."
        )
    },
     {
        "mots_cles": ["descente", "redescendre", "descendre", "rappel", "moulinette"],
        "reponse": (
            "Pour descendre, préviens ton assureur avec le signal convenu.\n"
            "Garde les jambes légèrement fléchies.\n"
            "Signale quand tes pieds touchent le sol."
        )
    },
    {
        "mots_cles": ["douleur", "doigt", "tendon", "blessure", "mal", "bobo"],
        "reponse": (
            "Si tu as mal, arrête-toi et redescends.\n"
            "Ne force jamais sur une douleur vive.\n"
            "Consulte un médecin si la douleur dure."
        )
    },
    {
        "mots_cles": ["technique", "position", "équilibre", "equilibre"],
        "reponse": (
            "TECHNIQUE — Grimpe avec les jambes.\n"
            "Les jambes sont plus puissantes que les bras.\n"
            "Cherche ton équilibre avant de tirer sur les prises.\n"
            "Garde les bras détendus autant que possible pour économiser ton énergie."
        )
    },
    {
        "mots_cles": ["sensation", "toucher", "tactile", "explorer", "palper"],
        "reponse": (
            "Avant chaque mouvement, explore la zone à portée de main.\n"
            "Sens la taille et l'orientation de chaque prise.\n"
            "Tes mains et tes pieds sont tes yeux sur le mur."
        )
    },
    {
        "mots_cles": ["fatigue", "repos", "pause", "récupération", "recuperation"],
        "reponse": (
            "RÉCUPÉRATION — Écoute ton corps.\n"
            "Prends des pauses régulières entre les essais.\n"
            "Hydrate-toi fréquemment.\n"
            "Si tes avant-bras sont très congestionnés, repose-toi avant de repartir."
        )
    },
    {
        "mots_cles": ["peur", "vertige", "stress", "confiance"],
        "reponse": (
            "GESTION DU STRESS — Reste concentré.\n"
            "Regarde les prises suivantes plutôt que le vide sous toi.\n"
            "Respire calmement et communique avec ton assureur.\n"
            "La confiance se construit progressivement avec la pratique."
        )
    },
    {
        "mots_cles": ["chute", "tomber", "vol", "tombe"],
        "reponse": (
            "CHUTE — Quelques conseils.\n"
            "Préviens ton assureur avant de te laisser tomber.\n"
            "Écarte-toi du mur avec les pieds pour éviter les chocs.\n"
            "Garde les jambes légèrement fléchies lors de la réception dans le baudrier."
        )
    },
    {
        "mots_cles": ["lecture", "voie", "itinéraire", "itineraire"],
        "reponse": (
            "LECTURE DE VOIE — Anticipe tes mouvements.\n"
            "Observe la voie depuis le sol avant de partir.\n"
            "Repère les prises de mains et de pieds importantes.\n"
            "Prévoir son itinéraire permet d'économiser beaucoup d'énergie."
        )
    },
    {
        "mots_cles": ["magnésie", "magnesie", "mains", "adhérence", "adherence"],
        "reponse": (
            "ADHÉRENCE — Optimise ton grip.\n"
            "Utilise la magnésie avec modération.\n"
            "Essuie la transpiration de tes mains si nécessaire.\n"
            "La précision des placements compte souvent plus que la force."
        )
    },
    {
        "mots_cles": ["débutant", "debutant", "commencer", "première fois", "premiere fois"],
        "reponse": (
            "DÉBUTANT — Prends ton temps.\n"
            "Concentre-toi d'abord sur les mouvements simples et l'équilibre.\n"
            "N'hésite pas à demander conseil aux encadrants.\n"
            "Chaque grimpeur progresse à son rythme."
        )
    },
    {
        "mots_cles": ["matériel", "materiel", "baudrier", "corde", "équipement", "equipement"],
        "reponse": (
            "MATÉRIEL — Vérification essentielle.\n"
            "Contrôle l'état du baudrier, de la corde et du système d'assurage.\n"
            "Assure-toi que tous les réglages sont correctement effectués.\n"
            "En cas de doute, demande une vérification à un encadrant."
        )
    },
    {
        "mots_cles": ["performance", "progresser", "progression", "niveau"],
        "reponse": (
            "PROGRESSION — Grimpe intelligemment.\n"
            "Travaille régulièrement des voies légèrement au-dessus de ton niveau.\n"
            "Analyse tes erreurs et tes réussites.\n"
            "La technique est souvent plus importante que la force brute."
        )
    },

    {
        "mots_cles":["combien", "reste", "finir", "fin"],
        "reponse": (
            "Il vous reste ... de prises\n",
            "Vous pouvez le faire, vous en êtes tout à fait capable."
        )

    
    },
    {
        "mots_cles": ["bonjour", "salut", "hello", "bonsoir", "coucou"],
        "reponse": (
            "Bonjour et bienvenue !\n"
            "Je suis ton assistant escalade pour les personnes aveugles et malvoyantes.\n"
            "Je peux t'aider sur la sécurité, l'équipement, la communication avec ton assureur,\n"
            "les techniques de grimpe, l'orientation sur le mur, les droits et les associations.\n"
            "Pose-moi ta question, je suis là !"
        )
    },
    {
        "mots_cles": ["qui es-tu", "qui es tu", "c'est quoi", "tu fais quoi", "aide", "help"],
        "reponse": (
            "Je suis un assistant virtuel spécialisé dans l'escalade adaptée.\n"
            "Mon rôle est de t'accompagner dans ta pratique de l'escalade en salle\n"
            "lorsque tu es aveugle ou malvoyant.\n"
            "Tu peux me parler de sécurité, d'équipement, de techniques,\n"
            "de communication avec ton assureur, ou encore des associations."
        )
    },
    {
        "mots_cles": ["sécurité", "securite", "danger", "risque", "sûr", "sur"],
        "reponse": (
            "SÉCURITÉ — Points essentiels.\n"
            "Avant de grimper, palpe le mur à portée de main pour repérer les prises proches.\n"
            "Conviens avec ton assureur d'un code vocal clair : DROITE, GAUCHE, HAUT, BAS.\n"
            "Vérifie toujours ensemble le baudrier et les noeuds avant de commencer.\n"
            "Informe le staff de la salle de ton passage.\n"
            "La communication est la clé de la sécurité !"
        )
    },
    {
        "mots_cles": ["équipement", "equipement", "matériel", "materiel", "chaussures", "baudrier", "corde", "acheter"],
        "reponse": (
            "ÉQUIPEMENT recommandé.\n"
            "Un baudrier avec boucles en relief pour les reconnaître au toucher.\n"
            "Des chaussures d'escalade légèrement serrées pour maximiser les sensations.\n"
            "De la magnésie pour améliorer l'adhérence des mains.\n"
            "Un casque fortement conseillé pour les débutants."
        )
    },
    {
        "mots_cles": ["assureur", "communiquer", "communication", "guider", "guidage", "instructions", "verbal", "code"],
        "reponse": (
            "COMMUNICATION avec ton assureur.\n"
            "Mettez-vous d'accord sur un code vocal précis avant de grimper.\n"
            "Directions : DROITE, GAUCHE, HAUT, BAS.\n"
            "Distances : PROCHE pour moins de 20 centimètres, MOYEN jusqu'à 50, LOIN au-delà.\n"
            "Type de prise : RÉGLETTE, JUG, BOMBE, PINCE.\n"
            "Sécurité : STOP pour ne plus bouger. OK DESCEND pour redescendre.\n"
            "Entraîne-toi à ce code à terre avant de grimper !"
        )
    },
    {
        "mots_cles": ["technique", "grimper", "comment monter", "prises", "pied", "main", "mouvement", "déplacement"],
        "reponse": (
            "TECHNIQUES de grimpe à l'aveugle.\n"
            "Exploration tactile : explore la zone à portée de main avant chaque mouvement.\n"
            "Pieds en premier : place tes pieds précisément, ils portent le corps.\n"
            "Trois points d'appui : garde toujours trois membres sur le mur.\n"
            "Respiration : expire à l'effort, inspire dans les positions stables.\n"
            "Mémorisation : construis mentalement une carte du mur en montant.\n"
            "Écoute du corps : tes sensations sont tes meilleures alliées."
        )
    },
    {
        "mots_cles": ["orientation", "repère", "repere", "carte", "position", "où je suis", "situer", "mur"],
        "reponse": (
            "S'ORIENTER sur le mur.\n"
            "Palpe les bords du mur pour t'ancrer au départ.\n"
            "L'assureur t'indique ta hauteur et le nombre de prises restantes.\n"
            "Méthode de la grille : imagine le mur en colonnes et lignes numérotées.\n"
            "Certaines salles placent des reliefs tactiles comme repères.\n"
            "Demande au staff de t'orienter avant de commencer."
        )
    },
    {
        "mots_cles": ["association", "club", "fédération", "federation", "handisport", "adapté", "adapte", "handicap"],
        "reponse": (
            "ASSOCIATIONS et ressources utiles.\n"
            "Handisport France : fédération officielle, sur handisport point org.\n"
            "FFME, commission Escalade Handisport, sur ffme point fr.\n"
            "AVH, Association Valentin Haüy, sur avh point asso point fr.\n"
            "Contacte la salle locale : beaucoup ont des créneaux adaptés."
        )
    },
    {
        "mots_cles": ["première fois", "premiere fois", "debut", "débuter", "commencer", "débutant", "novice", "jamais grimpé"],
        "reponse": (
            "TA PREMIÈRE SÉANCE.\n"
            "Appelle la salle à l'avance pour demander un moniteur formé.\n"
            "Arrive avec ton assureur et faites une visite tactile ensemble.\n"
            "Commencez par le bloc, c'est le mur bas sans corde.\n"
            "Définissez votre code de communication avant de poser les mains.\n"
            "Commence à un mètre du sol : l'objectif, c'est ressentir !\n"
            "Bonne première grimpe !"
        )
    },
    {
        "mots_cles": ["difficile", "dur", "peur", "panique", "fatigué", "fatigue", "découragé", "décourage", "abandonner"],
        "reponse": (
            "C'est normal de trouver ça difficile au début.\n"
            "Respire profondément avant chaque mouvement.\n"
            "Reste proche du sol, la confiance vient progressivement.\n"
            "Chaque centimètre gagné est une vraie victoire.\n"
            "Beaucoup de grimpeurs non-voyants atteignent des niveaux impressionnants.\n"
            "Continue !"
        )
    },
    {
        "mots_cles": ["vocabulaire", "mot", "terme", "jug", "réglette", "reglette", "bombe", "pince", "dégaine", "degaine", "nœud", "noeud"],
        "reponse": (
            "VOCABULAIRE de l'escalade.\n"
            "JUG : grosse prise facile, en forme de poignée.\n"
            "RÉGLETTE : prise plate et fine, juste pour les doigts.\n"
            "BOMBE : prise ronde qu'on enserre avec la main.\n"
            "PINCE : serrée entre le pouce et les doigts.\n"
            "BAUDRIER : harnais autour de la taille et des cuisses.\n"
            "NOEUD EN HUIT : noeud principal pour s'encorder.\n"
            "BLOC : mur bas sans corde. MOULINETTE : corde déjà en haut."
        )
    },
    {
        "mots_cles": ["droit", "accessibilité", "accessibilite", "loi", "discrimination", "accès", "acces", "tarif"],
        "reponse": (
            "DROITS et accessibilité.\n"
            "La loi du 11 février 2005 garantit l'accès des personnes handicapées\n"
            "aux établissements sportifs en France.\n"
            "En cas de refus, contacte le Défenseur des Droits au 0 809 849 849.\n"
            "Demande le tarif handisport en salle, et renseigne-toi auprès de ta mutuelle."
        )
    },
    {
        "mots_cles": ["au revoir", "bye", "à bientôt", "a bientot", "merci", "ciao", "tchao", "quitter", "fin", "arrêter", "arreter"],
        "reponse": (
            "À bientôt !\n"
            "Bonne chance dans ta pratique de l'escalade.\n"
            "N'oublie pas : chaque prise conquise est une victoire !\n"
            "Reviens quand tu veux."
        )
    },
]

REPONSE_DEFAUT = (
    "Je n'ai pas bien compris ta question.\n"
    "Tu peux me parler de : sécurité, équipement, communication,\n"
    "technique, orientation, association, première fois, vocabulaire, ou droits.\n"
    "Reformule ta question ou répète un de ces mots-clés."
)

MOTS_SORTIE = {
    "quitter", "quit", "exit", "bye", "au revoir", "a bientot",
    "à bientôt", "fin", "ciao", "tchao", "arrêter", "arreter"
}


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
