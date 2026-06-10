import time
import urllib.request
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO

# =====================================================================
# 1. INITIALISATION ET CONFIGURATION DES MODÈLES
# =====================================================================

LIAISONS_CORPS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 31), (28, 32), (27, 29), (28, 30),
    (15, 17), (15, 19), (15, 21), (17, 19),
    (16, 18), (16, 20), (16, 22), (18, 20)
]

print("Chargement du modèle YOLOv8 (best.pt)...")
modele_yolo = YOLO("best.pt")

model_path = "pose_landmarker_full.task"
try:
    with open(model_path, "rb"): pass
except FileNotFoundError:
    print("Téléchargement du modèle IA MediaPipe Tasks...")
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
    urllib.request.urlretrieve(url, model_path)

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.VIDEO
)

# =====================================================================
# 2. VARIABLES DU RÉFÉRENTIEL MONDE
# =====================================================================
ref_frame_gray = None
ref_keypoints = None
ref_descriptors = None

# On stocke les 4 coins de chaque boîte de prise d'escalade dans le monde fixe
# Format pour chaque prise : [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
prises_contours_fixes = []

# Les 4 coins du cadre du référentiel initial (les bords de l'image d'origine)
cadre_initial_points = None

orb = cv2.ORB_create(nfeatures=1500)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

# =====================================================================
# 3. BOUCLE PRINCIPALE FLUX LIVE
# =====================================================================
cap = cv2.VideoCapture(0)

with PoseLandmarker.create_from_options(options) as landmarker:
    print("\n--- PROGRAMME PRÊT ---")
    print("1. Cadrez le mur d'escalade.")
    print("2. Appuyez sur 'R' pour lancer la détection YOLO et fixer le cadre.")
    
    while cap.isOpened():
        success, frame = cap.read()
        if not success: break
        
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        H_inv = None 
        H = None
        
        # --- CALCUL DU MOUVEMENT DE LA CAMÉRA ---
        if ref_frame_gray is not None:
            kp_actuel, des_actuel = orb.detectAndCompute(gray, None)
            
            if des_actuel is not None and len(des_actuel) > 10:
                matches = bf.match(ref_descriptors, des_actuel)
                matches = sorted(matches, key=lambda x: x.distance)
                good_matches = matches[:60]
                
                if len(good_matches) > 15:
                    pts_ref = np.float32([ref_keypoints[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                    pts_actuels = np.float32([kp_actuel[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                    
                    H, mask = cv2.findHomography(pts_ref, pts_actuels, cv2.RANSAC, 5.0)
                    if H is not None:
                        H_inv = np.linalg.inv(H)

        # --- DESSIN DU CADRE DU RÉFÉRENTIEL À L'ÉCRAN ---
        if ref_frame_gray is not None and cadre_initial_points is not None:
            if H is not None:
                # On déplace virtuellement le cadre initial selon le mouvement caméra
                cadre_ecran = cv2.perspectiveTransform(cadre_initial_points.reshape(-1, 1, 2), H).reshape(-1, 2)
            else:
                cadre_ecran = cadre_initial_points
            
            # Dessiner les lignes du grand cadre bleu (Référentiel d'origine)
            pts_cadre = cadre_ecran.astype(np.int32)
            cv2.polylines(frame, [pts_cadre], isClosed=True, color=(255, 0, 0), thickness=3)
            # Marquer l'origine (0,0) en haut à gauche du cadre
            cv2.circle(frame, (pts_cadre[0][0], pts_cadre[0][1]), 8, (255, 100, 0), -1)
            cv2.putText(frame, "ORIGINE (0,0) DU MUR", (pts_cadre[0][0] + 15, pts_cadre[0][1] + 20), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 100, 0), 2)

        # --- DESSIN DU CONTOUR DES PRISES SUR L'ÉCRAN ---
        if len(prises_contours_fixes) > 0:
            for i, contour_fixe in enumerate(prises_contours_fixes):
                if H is not None:
                    # On transforme les 4 coins de la boîte pour suivre le mur
                    contour_ecran = cv2.perspectiveTransform(contour_fixe.reshape(-1, 1, 2), H).reshape(-1, 2)
                else:
                    contour_ecran = contour_fixe
                
                # Dessin du rectangle de contour en vert brillant autour de la prise
                pts_contour = contour_ecran.astype(np.int32)
                cv2.polylines(frame, [pts_contour], isClosed=True, color=(0, 255, 0), thickness=2)
                
                # Petit texte d'identification au coin supérieur gauche de la boîte
                cv2.putText(frame, f"Prise {i+1}", (pts_contour[0][0], pts_contour[0][1] - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        # --- DÉTECTION ET PROJECTION DU STICKMAN ---
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        timestamp_ms = int(time.time() * 1000)
        detection_result = landmarker.detect_for_video(mp_image, timestamp_ms)
        
        if detection_result.pose_landmarks:
            landmarks = detection_result.pose_landmarks[0]
            points_stickman_ecran = []
            landmarks_valides = {}
            
            for idx in range(11, 33):
                if landmarks[idx].visibility > 0.5:
                    cx, cy = int(landmarks[idx].x * w), int(landmarks[idx].y * h)
                    points_stickman_ecran.append([cx, cy])
                    landmarks_valides[idx] = (cx, cy)
                    cv2.circle(frame, (cx, cy), 5, (0, 255, 255), -1)

            for p1, p2 in LIAISONS_CORPS:
                if p1 in landmarks_valides and p2 in landmarks_valides:
                    cv2.line(frame, landmarks_valides[p1], landmarks_valides[p2], (255, 255, 0), 2)

            # Envoi des données du stickman dans l'espace stable du mur
            if H_inv is not None and len(points_stickman_ecran) > 0:
                pts_stickman_reshape = np.array(points_stickman_ecran, dtype=np.float32).reshape(-1, 1, 2)
                points_stickman_monde = cv2.perspectiveTransform(pts_stickman_reshape, H_inv).reshape(-1, 2)
                
                if 16 in landmarks_valides:  # Main droite
                    idx_main = list(landmarks_valides.keys()).index(16)
                    coord_fixe_main = points_stickman_monde[idx_main]
                    # Ces coordonnées ne changent pas si on bouge la caméra sans bouger la main
                    print(f"[RÉFÉRENTIEL REPERE] Main Droite dans le Cadre : X={int(coord_fixe_main[0])}, Y={int(coord_fixe_main[1])}")

        # UI
        if ref_frame_gray is None:
            cv2.putText(frame, "STATUT : REPERE INACTIF (Pressez 'R')", (15, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        else:
            cv2.putText(frame, "STATUT : CADRE & SUIVI MONDE ACTIFS", (15, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
        cv2.imshow("Referentiel Stable Escalade", frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("r"):
            print("\n[INFO] Analyse YOLOv8 et fixation des frontières du référentiel...")
            results = modele_yolo(frame, verbose=False)
            
            prises_contours_fixes = []
            for box in results[0].boxes:
                xyxy = box.xyxy[0].cpu().numpy()
                # Définition des 4 coins de la boîte de détection de la prise
                xmin, ymin, xmax, ymax = xyxy[0], xyxy[1], xyxy[2], xyxy[3]
                box_corners = np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=np.float32)
                prises_contours_fixes.append(box_corners)
            
            if len(prises_contours_fixes) > 0:
                # Enregistrement du grand cadre (les 4 coins de l'écran à cet instant T)
                cadre_initial_points = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
                
                ref_frame_gray = gray.copy()
                ref_keypoints, ref_descriptors = orb.detectAndCompute(ref_frame_gray, None)
                print(f"[OK] Le référentiel démarre ici. {len(prises_contours_fixes)} contours de prises verrouillés.")
            else:
                print("[ERREUR] YOLO n'a détecté aucune prise. Cadre non verrouillé.")

cap.release()
cv2.destroyAllWindows()
