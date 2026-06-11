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
- **Assistant vocal** — questions/réponses sur l'escalade, guidance sur la prochaine prise, comptage des prises restantes
- **Mode micro continu** — écoute en boucle automatique, répond à voix haute, recommence ; dire « au revoir » pour arrêter
- **Recadrage interactif** — cliquer le premier coin, ajuster le rectangle avec deux sliders avant de lancer la détection

---

## Installation

### Prérequis

- Python 3.10+
- Webcam USB ou intégrée

### Dépendances

```bash
pip install streamlit ultralytics mediapipe opencv-python numpy
pip install streamlit-image-coordinates pyttsx3 SpeechRecognition pyaudio
```

> **Windows** : si la caméra ne s'ouvre pas, installer `pywin32` :
> ```bash
> pip install pywin32
> ```

### Modèle YOLO

Placer le fichier `best.pt` (modèle entraîné) à la racine du projet.

### Modèle MediaPipe

Le fichier `pose_landmarker.task` est téléchargé automatiquement au premier lancement.

---

## Lancement

```bash
streamlit run app.py
```

Accès depuis un téléphone sur le même réseau Wi-Fi :

```bash
streamlit run app.py --server.address 0.0.0.0
```

Puis ouvrir `http://<IP_du_PC>:8501` sur le téléphone.

---

## Utilisation

1. **Charger une photo du mur** — via fichier ou capture caméra (onglet *Prendre une photo*)
2. **Recadrer si besoin** — cliquer le premier coin, ajuster les sliders
3. **Lancer la détection** — YOLO détecte et classifie les prises
4. **Vérifier la cartographie** — modifier ou supprimer des prises si nécessaire
5. **Activer le live** — cocher *Activer le mode live vidéo*
6. **Se guider** — cliquer *Guider* ou activer le *Mode micro continu* pour une assistance vocale continue

---

## Structure du projet

| Fichier | Rôle |
|---|---|
| `app.py` | Interface Streamlit principale |
| `detect.py` | Détection YOLO + classification des prises |
| `detection_task.py` | Détection de pose MediaPipe (mode vidéo) |
| `path.py` | Algorithme de navigation (prise la plus proche par membre) |
| `homographie.py` | Suivi des prises par homographie ORB/RANSAC |
| `communication.py` | Synthèse vocale (pyttsx3) et reconnaissance vocale (Vosk/SpeechRecognition) |
| `best.pt` | Modèle YOLO entraîné *(non versionné)* |

---

## Auteurs

- QUIMPERT Matéo
- VIRASSAMY Manoé
- NANDAN Brayan
- MONDESIR Edeline
- PLACIDE Noam
- BIJOU Thomas

Projet ESIEE Paris — 2025/2026
