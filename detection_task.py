
import cv2
import mediapipe as mp
import urllib.request
import os

# === Télécharger le modèle automatiquement si absent ===
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "pose_landmarker.task")

if not os.path.exists(MODEL_PATH):
    print("Téléchargement du modèle MediaPipe...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("Modèle téléchargé avec succès ! ✅")
    except Exception as e:
        raise RuntimeError(f"Impossible de télécharger le modèle : {e}")

# === Configuration de MediaPipe en Mode VIDÉO ===
BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=MODEL_PATH),
    running_mode=VisionRunningMode.VIDEO
)

landmarker = PoseLandmarker.create_from_options(options)

# Compteur global de timestamps (strictement croissant)
_timestamp_counter = 0

def detect_corps(frame):
    global _timestamp_counter
    _timestamp_counter += 1

    h, w, _ = frame.shape

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    small = cv2.resize(frame_rgb, (320, 240))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=small)

    result = landmarker.detect_for_video(mp_image, _timestamp_counter)

    if result.pose_landmarks and len(result.pose_landmarks) > 0:
        points_utiles = []
        for lm in result.pose_landmarks[0]:
            points_utiles.append({'x': lm.x, 'y': lm.y})
        return points_utiles, (w, h)

    return None, None