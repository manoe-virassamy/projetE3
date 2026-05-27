#%pip install "numpy<2" "mediapipe==0.10.21" "opencv-python==4.8.1.78" --user --force-reinstall

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

# Liste de connexions simplifiée (uniquement des entiers) ---
# On définit directement les liaisons du corps à dessiner (on évite de filtrer en boucle)
LIAISONS_CORPS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), # Épaules et bras
    (11, 23), (12, 24), (23, 24),                     # Torse
    (23, 25), (25, 27), (24, 26), (26, 28),           # Jambes
    (27, 31), (28, 32), (27, 29), (28, 30),            # Pieds
    (15, 17), (15, 19), (15, 21), (17, 19),           # Main gauche
    (16, 18), (16, 20), (16, 22), (18, 20)            # Main droite
]

cap = cv2.VideoCapture(0)

# Ajustement des paramètres de l'IA ---
# On baisse légèrement la confiance à 0.6 pour éviter que l'IA ne force des calculs
# de correction trop lourds si le flux est rapide.
with mp_pose.Pose(
    static_image_mode=False, 
    min_detection_confidence=0.6, 
    min_tracking_confidence=0.5
) as pose:

    while cap.isOpened():
        success, frame = cap.read()
        if not success: break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(img_rgb)

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark

            # Dessin direct avec OpenCV (Rapide)

            pt_min = 11
            pt_max = 32

            # 1. On trace les points du corps (uniquement à partir de l'index 11 (entre 0 et 10 = visage) )
            for idx in range(pt_min, pt_max+1):
                if landmarks[idx].visibility > 0.5:

                    #Les coordonnées fournies par MediaPipe sont dites 'normalisées',
                    # c'est-à-dire qu'elles s'expriment par un pourcentage entre 0.0 et 1.0 par rapport à la taille de l'image.
                    #Pour qu'OpenCV puisse dessiner le squelette, nous devons convertir ces valeurs en pixels réels.
                    #Pour cela, nous multiplions la coordonnée X par la largeur de la frame (w) et la coordonnée Y par sa hauteur.
                    
                    cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                    cv2.circle(frame, (cx, cy), 6, (0, 255, 255), -1) # Jaune

            # 2. On trace les lignes du corps
            for p1, p2 in LIAISONS_CORPS:
                # On vérifie si les points sont visibles à l'écran
                if landmarks[p1].visibility > 0.5 and landmarks[p2].visibility > 0.5:
                    pt1 = (int(landmarks[p1].x * w), int(landmarks[p1].y * h))
                    pt2 = (int(landmarks[p2].x * w), int(landmarks[p2].y * h))
                    cv2.line(frame, pt1, pt2, (255, 255, 0), 3) # Bleu turquoise

        cv2.imshow("MediaPipe Pose - Live ", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

cap.release()
cv2.destroyAllWindows()
