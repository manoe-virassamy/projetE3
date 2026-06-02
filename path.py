import cv2
from ultralytics import YOLO
import mediapipe as mp

# Charger le modèle de prises 
model = YOLO("best.pt")

def trouver_prochaine_prise(main_droite, main_gauche, prises):
    """
    main_droite : (x, y) ou None
    main_gauche : (x, y) ou None
    prises : liste de tuples [(x, y), ...]

    retourne :
        meilleure prise (x, y) ou None
    """

    candidates = []

    # ✅ tester les deux mains
    for main in [main_droite, main_gauche]:

        if main is None:
            continue

        mx, my = main

        for (px, py) in prises:

            # ✅ uniquement les prises au-dessus
            if py < my:

                distance = ((px - mx)**2 + (py - my)**2)**0.5

                # ✅ filtre distance
                if distance < 200:
                    candidates.append((distance, px, py, mx, my))

    if candidates:
        candidates.sort()

        # retourne (prise + main utilisée)
        _, px, py, mx, my = candidates[0]

        return (px, py), (mx, my)

    return None, None
                    

