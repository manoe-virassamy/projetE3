#python -m pip install numpy<2 mediapipe==0.10.21 opencv-python==4.8.1.78 --force-reinstall

import cv2
import mediapipe as mp
import matplotlib.pyplot as plt
import numpy as np

print("NumPy version:", np.__version__)
print("OpenCV version:", cv2.__version__)
print("MediaPipe version:", mp.__version__)
print("Tout est parfait ! mp.solutions existe :", hasattr(mp, "solutions"))



#--------------------------------------------------------------------------------------------------------------------

mp_pose = mp.solutions.pose

pose = mp_pose.Pose(
    static_image_mode=False,
    min_detection_confidence=0.6,
    min_tracking_confidence=0.5
)

LIAISONS_CORPS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 31), (28, 32), (27, 29), (28, 30),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (16, 18), (16, 20), (16, 22), (18, 20)
]

def detect_corps(frame):

    h, w, _ = frame.shape

    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(img_rgb)

    if results.pose_landmarks:

        landmarks = results.pose_landmarks.landmark

        coordonnees_pixels = {}

        for idx, landmark in enumerate(landmarks):
            cx = int(landmark.x * w)
            cy = int(landmark.y * h)
            coordonnees_pixels[idx] = (cx, cy)

        # ✅ Dessin squelette (comme ton code)
        for idx in range(11, 33):
            if landmarks[idx].visibility > 0.5:
                cx, cy = coordonnees_pixels[idx]
                cv2.circle(frame, (cx, cy), 6, (0, 255, 255), -1)

        for p1, p2 in LIAISONS_CORPS:
            if landmarks[p1].visibility > 0.5 and landmarks[p2].visibility > 0.5:
                pt1 = coordonnees_pixels[p1]
                pt2 = coordonnees_pixels[p2]
                cv2.line(frame, pt1, pt2, (255, 255, 0), 3)

        # ✅ récupérer mains
        main_droite = coordonnees_pixels.get(16)
        main_gauche = coordonnees_pixels.get(15)

        return main_droite, main_gauche

    return None, None
