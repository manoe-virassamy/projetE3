#%pip install "numpy<2" "mediapipe==0.10.21" "opencv-python==4.8.1.78" --user --force-reinstall

import cv2
import mediapipe as mp
import matplotlib.pyplot as plt
import numpy as np

print("NumPy version:", np.__version__)
print("OpenCV version:", cv2.__version__)
print("MediaPipe version:", mp.__version__)
print("Tout est parfait ! mp.solutions existe :", hasattr(mp, "solutions"))


#-------------------------------------------------------------------------------------------------------------------------------------------------

# 1. Initialisation des modules de MediaPipe
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# --- FILTRAGE DES CONNEXIONS POUR SUPPRIMER LE VISAGE ---
# On crée une liste personnalisée qui exclut toutes les lignes liées au visage (index 0 à 10)
connexions_corps = [
    conn for conn in mp_pose.POSE_CONNECTIONS
    if conn[0] >= 11 and conn[1] >= 11
]

# 2. Configuration des styles de dessin
style_points = mp_drawing.DrawingSpec(
    color=(0, 255, 255), thickness=3, circle_radius=6
)  # Jaune
style_lignes = mp_drawing.DrawingSpec(
    color=(255, 255, 0), thickness=3
)  # Bleu turquoise

# 3. Chargement et conversion de l'image
img_bgr = cv2.imread("test5.jpg")
img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
img_out = img_rgb.copy()

# 4. Configuration de l'IA pour une image fixe
with mp_pose.Pose(static_image_mode=True) as pose:
    
    # Analyse de l'image par l'IA
    results = pose.process(img_rgb)

    # 5. Si un corps est détecté
    if results.pose_landmarks:
        
        # --- FILTRAGE DES POINTS DU VISAGE ---
        # On passe la visibilité des points 0 à 10 à 0 pour que l'outil de dessin les ignore
        for idx in range(0, 11):
            results.pose_landmarks.landmark[idx].visibility = 0

        # Dessin du squelette filtré sur l'image de sortie
        mp_drawing.draw_landmarks(
            img_out,
            results.pose_landmarks,
            connections=connexions_corps,  # On utilise notre liste sans visage
            landmark_drawing_spec=style_points,
            connection_drawing_spec=style_lignes,
        )

# 6. Affichage du résultat final avec Matplotlib
plt.imshow(img_out)
plt.axis("off")
plt.show()
