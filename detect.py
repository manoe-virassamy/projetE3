from ultralytics import YOLO
import cv2
import numpy as np
import os 
import requests

# Charger le modèle
model = YOLO("best.pt")

# Détection
def detect_image(image_path, conf=0.1):
    results = model.predict(
        source=image_path,
        conf=conf,
        save=True
    )

    img = results[0].orig_img.copy()
    boxes = results[0].boxes

    prises = []

    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        score = float(box.conf[0])

        # Zone de la prise
        roi = img[y1:y2, x1:x2]

        # ---- COULEUR PRÉCISE ----
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Moyenne HSV 
        mean_hue = hsv[:, :, 0].mean()

        # Détection de la couleur selon HUE
        if mean_hue < 10 or mean_hue > 170:
            couleur = "Rouge"
        elif 10 <= mean_hue < 25:
            couleur = "Orange"
        elif 25 <= mean_hue < 35:
            couleur = "Jaune"
        elif 35 <= mean_hue < 50:
            couleur = "Jaune-Vert"
        elif 50 <= mean_hue < 85:
            couleur = "Vert"
        elif 85 <= mean_hue < 125:
            couleur = "Bleu"
        elif 125 <= mean_hue < 170:
            couleur = "Violet"
        else:
            couleur = "Inconnue"
        
        # ---- FORMES + TAILLE ----
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        taille = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 50:
                taille += area
        
        bbox_area = (x2 - x1) * (y2 - y1)

        # ---- STOCKAGE DES INFORMATIONS DE LA PRISE ----
        prises.append({
            "id": i+1,
            "score": score,
            "coords": (x1, y1, x2, y2),
            "couleur": couleur,
            "taille": int(taille),
            "_bbox_area": bbox_area,
            "usage": "Mains+Pieds",   # sera recalculé ci-dessous
        })

    # ---- USAGE : mains ou pieds selon la taille relative entre prises ----
    # Les prises >= médiane des surfaces → Mains ; les plus petites → Pieds.
    # Cette approche s'adapte à toute résolution d'image.
    if prises:
        areas = sorted(p["_bbox_area"] for p in prises)
        mediane = areas[len(areas) // 2]
        for p in prises:
            p["usage"] = "Mains+Pieds" if p["_bbox_area"] >= mediane else "Pieds"
            del p["_bbox_area"]

    return img, prises