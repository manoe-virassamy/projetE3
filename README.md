<h1>BlindClimb Assist<br>
<sub><i>La voix qui vous guide pour une montée en confiance !</i></sub></h1>

Application d'assistance à la navigation sur mur d'escalade pour grimpeurs malvoyants ou aveugles.  
Développée dans le cadre d'un projet étudiant à l'ESIEE Paris.

---

## Fonctionnalités

- **Détection automatique des prises** — modèle YOLO entraîné sur des prises d'escalade, classification automatique en *mains+pieds* (grandes prises) et *pieds seulement* (petites prises)
- **Cartographie interactive du mur** — visualisation des prises détectées, sélection, modification et suppression manuelle
- **Flux vidéo live** — caméra en temps réel avec squelette MediaPipe superposé
- **Suivi des prises par homographie** — les points restent ancrés sur le mur même si la caméra bouge (ORB + RANSAC)
- **Guidage vocal** — flèches de direction par membre (main droite/gauche, pied droit/gauche) avec retour vocal
- **Assistant vocal** — questions/réponses sur l'escalade, guidance sur la prochaine prise, comptage des prises restantes ; micro et synthèse vocale fonctionnent directement dans le navigateur (PC ou téléphone)
- **Recadrage interactif** — cliquer le premier coin, ajuster le rectangle avec deux sliders avant de lancer la détection

---

## Installation

### Prérequis

- Python 3.10+
- Webcam USB ou intégrée

### Dépendances

```bash
pip install -r requirements.txt
```

### Modèle YOLO

Placer le fichier `best.pt` (modèle entraîné) à la racine du projet.

### Modèle MediaPipe

Le fichier `pose_landmarker.task` est téléchargé automatiquement au premier lancement.

---

## Lancement

L'utilisation du micro et de la caméra depuis un navigateur (PC ou téléphone) exige une
connexion **HTTPS**. Avant le tout premier lancement, générer un certificat local auto-signé :

```bash
python generate_cert.py
```

(à relancer uniquement si l'IP locale du PC change, par exemple en changeant de réseau Wi-Fi).

Puis lancer l'app normalement :

```bash
streamlit run app.py
```

Accès depuis un téléphone sur le même réseau Wi-Fi :

```bash
streamlit run app.py --server.address 0.0.0.0
```

Puis ouvrir **`https://<IP_du_PC>:8501`** sur le téléphone (l'IP exacte est affichée par
`generate_cert.py`). Le navigateur affiche un avertissement « connexion non privée » la
première fois (certificat auto-signé) :
- **Chrome (Android)** : cliquer sur *Avancé*, puis *Continuer vers le site*.
- **Safari (iPhone)** : cliquer sur *Afficher les détails*, puis *Visiter ce site web*.

Cet avertissement n'apparaît qu'une fois par appareil/navigateur.

### Icône sur l'écran d'accueil du téléphone

Les icônes (générées une fois pour toutes via `python generate_icons.py`, à relancer
uniquement si `Logo.jpg` change) sont déjà fournies. En ajoutant la page à l'écran
d'accueil (*Partager → Sur l'écran d'accueil* sur Safari/iPhone, ou menu *⋮ → Ajouter
à l'écran d'accueil* sur Chrome/Android), c'est le logo BCA qui est utilisé comme icône
plutôt qu'une capture d'écran de la page.

Chrome et Safari ne détectent les balises d'icône que si elles sont présentes dans le
HTML dès le chargement initial — Streamlit ne permettant pas de modifier son `<head>`
autrement, ces balises sont insérées directement dans le `index.html` installé avec
Streamlit. Ce patch est appliqué **automatiquement au démarrage de `app.py`**
(`patch_streamlit_pwa.py`, appelé une seule fois par processus via
`@st.cache_resource`) — aucune action manuelle requise, y compris après une
réinstallation de Streamlit ou sur Streamlit Community Cloud.

---

## Utilisation

1. **Charger une photo du mur** — via fichier ou capture caméra (onglet *Prendre une photo*)
2. **Recadrer si besoin** — cliquer le premier coin, ajuster les sliders
3. **Lancer la détection** — YOLO détecte et classifie les prises
4. **Vérifier la cartographie** — modifier ou supprimer des prises si nécessaire
5. **Activer le live** — cocher *Activer le mode live vidéo*
6. **Se guider** — cliquer *Guider*, ou poser une question par écrit ou à voix haute (micro du navigateur) à l'assistant

---

## Structure du projet

| Fichier | Rôle |
|---|---|
| `app.py` | Interface Streamlit principale |
| `detect.py` | Détection YOLO + classification des prises |
| `path.py` | Algorithme de navigation (prise la plus proche par membre) |
| `homographie.py` | Suivi des prises par homographie ORB/RANSAC |
| `communication.py` | Reconnaissance vocale (Vosk/SpeechRecognition) et chatbot CLI autonome |
| `voice_browser.py` | Synthèse vocale côté navigateur (voix neuronale edge-tts, repli `window.speechSynthesis`) |
| `generate_cert.py` | Génère le certificat HTTPS local auto-signé |
| `generate_icons.py` | Génère les icônes d'écran d'accueil (`static/icons/`, `static/manifest.json`) |
| `patch_streamlit_pwa.py` | Insère les balises PWA dans le `index.html` installé avec Streamlit |
| `best.pt` | Modèle YOLO entraîné |

---

## Auteurs

- QUIMPERT Matéo
- VIRASSAMY Manoé
- NANDAN Brayan
- MONDESIR Edeline
- PLACIDE Noam
- BIJOU Thomas

Projet ESIEE Paris — 2025/2026
