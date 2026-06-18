import time
import urllib.request
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
from sklearn.cluster import DBSCAN

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

COULEUR_MAIN_PIED = (0, 255, 0)    # vert
COULEUR_PIED_ONLY = (255, 100, 0)  # bleu

SEUIL_BAS_MIXTE  = 0.05
SEUIL_HAUT_MIXTE = 0.95

print("Chargement du modèle YOLOv8 (best.pt)...")
modele_yolo = YOLO("best.pt")

# "Lite" plutôt que "Heavy" : en mode live, la silhouette doit suivre le
# grimpeur en temps réel — "Heavy" est plus précis mais trop lent sur CPU,
# ce qui faisait prendre du retard aux landmarks (silhouette visiblement
# désynchronisée par rapport à la vidéo, perçu comme de la latence et une
# mauvaise détection).
model_path = "pose_landmarker_lite.task"
try:
    with open(model_path, "rb"): pass
except FileNotFoundError:
    print("Téléchargement du modèle MediaPipe Lite...")
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
    urllib.request.urlretrieve(url, model_path)

BaseOptions           = mp.tasks.BaseOptions
PoseLandmarker        = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode     = mp.tasks.vision.RunningMode

options = PoseLandmarkerOptions(
    base_options=BaseOptions(model_asset_path=model_path),
    running_mode=VisionRunningMode.VIDEO,
    min_pose_detection_confidence=0.3,
    min_pose_presence_confidence=0.3,
    min_tracking_confidence=0.3,
)

# =====================================================================
# 2. STRUCTURES DE DONNÉES CENTRALISÉES
# =====================================================================

PRISES = []
PRISES_PROCHES = []

POSITION_GRIMPEUR = {
    "main_droite":  None,
    "main_gauche":  None,
    "pied_droit":   None,
    "pied_gauche":  None,
    "timestamp":    None,
}

MEMBRES = {
    16: "main_droite",
    15: "main_gauche",
    28: "pied_droit",
    27: "pied_gauche",
}

MARGE_ZONE = 80

# =====================================================================
# 3. VARIABLES INTERNES
# =====================================================================
ref_frame_gray        = None
ref_keypoints         = None
ref_descriptors       = None
cadre_initial_points  = None
image_prises          = None
origine_mur           = None

orb = cv2.ORB_create(nfeatures=1500)
bf  = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

UPSCALE           = 1.5
INTERVALLE_UPDATE = 2.0
INTERVALLE_PRISES = 3.0
derniere_update   = 0.0
derniere_prises   = 0.0
zone_courante     = None

# =====================================================================
# 4. CLASSIFICATION DES PRISES
# =====================================================================

def classifier_prises_par_taille(prises):
    if len(prises) < 2:
        for p in prises:
            p["type"] = "main_pied"
        return

    surfaces = []
    for p in prises:
        c = p["coins"]
        surfaces.append((c[1][0] - c[0][0]) * (c[3][1] - c[0][1]))

    surfaces_np = np.array(surfaces, dtype=np.float32).reshape(-1, 1)
    criteria    = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, _, centers = cv2.kmeans(surfaces_np, 2, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

    s_min      = float(min(centers))
    s_max      = float(max(centers))
    ecart      = s_max - s_min
    seuil_bas  = s_min + ecart * SEUIL_BAS_MIXTE
    seuil_haut = s_min + ecart * SEUIL_HAUT_MIXTE

    for i, p in enumerate(prises):
        p["type"] = "pied_only" if surfaces[i] < seuil_bas else \
                    "main_pied" if surfaces[i] > seuil_haut else "pied_only"

    nb_mp = sum(1 for p in prises if p["type"] == "main_pied")
    nb_p  = sum(1 for p in prises if p["type"] == "pied_only")
    print(f"[CLASSIFICATION] main+pied={nb_mp} | pied seul={nb_p}")


def couleur_prise(type_prise):
    return COULEUR_MAIN_PIED if type_prise == "main_pied" else COULEUR_PIED_ONLY


def dessiner_prise(img, coins, type_prise):
    cv2.polylines(img, [coins.astype(np.int32)], isClosed=True,
                  color=couleur_prise(type_prise), thickness=2)


# =====================================================================
# 5. DÉTECTION DU MUR PRINCIPAL
# =====================================================================

def detecter_mur_principal(boxes, w, h):
    if len(boxes) == 0:
        return [], None

    centres = []
    for box in boxes:
        xyxy = box.xyxy[0].cpu().numpy()
        centres.append([(xyxy[0] + xyxy[2]) / 2, (xyxy[1] + xyxy[3]) / 2])
    centres = np.array(centres)

    eps        = max(w, h) * 0.25
    clustering = DBSCAN(eps=eps, min_samples=1).fit(centres)
    labels     = clustering.labels_

    cx_img, cy_img         = w / 2, h / 2
    meilleur_label, meilleur_score = -1, -1

    for label in set(labels):
        if label == -1:
            continue
        indices     = np.where(labels == label)[0]
        score_total = 0
        for i in indices:
            xyxy      = boxes[i].xyxy[0].cpu().numpy()
            surface   = (xyxy[2] - xyxy[0]) * (xyxy[3] - xyxy[1])
            dist_norm = np.sqrt((centres[i][0] - cx_img)**2 + (centres[i][1] - cy_img)**2) \
                        / (np.sqrt(w**2 + h**2) / 2)
            score_total += surface * (1 - dist_norm * 0.5)
        if score_total / len(indices) > meilleur_score:
            meilleur_score = score_total / len(indices)
            meilleur_label = label

    indices_mur = list(np.where(labels == meilleur_label)[0])
    xs = [boxes[i].xyxy[0].cpu().numpy()[[0, 2]] for i in indices_mur]
    ys = [boxes[i].xyxy[0].cpu().numpy()[[1, 3]] for i in indices_mur]
    bbox_mur = (min(x[0] for x in xs), min(y[0] for y in ys),
                max(x[1] for x in xs), max(y[1] for y in ys))

    print(f"[MUR PRINCIPAL] {len(indices_mur)} prises dans le cluster retenu.")
    return indices_mur, bbox_mur


# =====================================================================
# 6. FONCTIONS UTILITAIRES
# =====================================================================

def mettre_a_jour_grimpeur(landmarks_valides, H_inv):
    global POSITION_GRIMPEUR, derniere_update
    now = time.time()
    if now - derniere_update < INTERVALLE_UPDATE:
        return
    derniere_update = now
    if H_inv is None:
        return
    for idx_mp, cle in MEMBRES.items():
        if idx_mp in landmarks_valides:
            pt       = np.array([[landmarks_valides[idx_mp]]], dtype=np.float32)
            pt_monde = cv2.perspectiveTransform(pt, H_inv)[0][0]
            POSITION_GRIMPEUR[cle] = (float(pt_monde[0]), float(pt_monde[1]))
        else:
            POSITION_GRIMPEUR[cle] = None
    POSITION_GRIMPEUR["timestamp"] = now


def mettre_a_jour_prises_proches(landmarks_valides, H):
    global PRISES_PROCHES, derniere_prises, zone_courante
    now = time.time()
    if now - derniere_prises < INTERVALLE_PRISES:
        return
    derniere_prises = now

    if not landmarks_valides:
        PRISES_PROCHES = []
        zone_courante  = None
        return

    xs    = [pt[0] for pt in landmarks_valides.values()]
    ys    = [pt[1] for pt in landmarks_valides.values()]
    x_min = max(0, min(xs) - MARGE_ZONE)
    x_max = max(xs) + MARGE_ZONE
    y_min = max(0, min(ys) - MARGE_ZONE)
    y_max = max(ys) + MARGE_ZONE
    zone_courante = (int(x_min), int(y_min), int(x_max), int(y_max))

    PRISES_PROCHES = []
    for prise in PRISES:
        if H is not None:
            centre_ecran = cv2.perspectiveTransform(
                np.array([[prise["centre"]]], dtype=np.float32), H
            )[0][0]
            cx, cy = centre_ecran
        else:
            cx, cy = prise["centre"]

        if x_min <= cx <= x_max and y_min <= cy <= y_max:
            coins_ecran = (
                cv2.perspectiveTransform(prise["coins"].reshape(-1, 1, 2), H).reshape(-1, 2)
                if H is not None else prise["coins"]
            )
            PRISES_PROCHES.append({
                "id":          prise["id"],
                "coins_ecran": coins_ecran,
                "conf":        prise["conf"],
                "type":        prise["type"],
            })


def fixer_referentiel(frame, gray, w, h):
    """R — détecte le mur principal et fixe le référentiel ORB."""
    global ref_frame_gray, ref_keypoints, ref_descriptors
    global cadre_initial_points, origine_mur

    print("\n[R] Détection du mur principal + fixation du référentiel...")
    results    = modele_yolo(frame, verbose=False)
    boxes      = results[0].boxes

    if len(boxes) == 0:
        print("[ERREUR] Aucune prise détectée. Recadrez le mur.")
        return False

    indices_mur, bbox_mur = detecter_mur_principal(boxes, w, h)
    xmin_mur, ymin_mur, xmax_mur, ymax_mur = bbox_mur

    origine_mur          = (xmin_mur, ymax_mur)
    cadre_initial_points = np.array([
        [xmin_mur, ymin_mur], [xmax_mur, ymin_mur],
        [xmax_mur, ymax_mur], [xmin_mur, ymax_mur]
    ], dtype=np.float32)

    ref_frame_gray                 = gray.copy()
    ref_keypoints, ref_descriptors = orb.detectAndCompute(ref_frame_gray, None)

    print(f"[OK] Référentiel fixé sur le mur ({len(indices_mur)} prises détectées).")
    print("[INFO] Appuyez sur D pour détecter et classer les prises.")
    return True


def detecter_et_classer_prises(frame, w, h):
    """D — détecte les prises dans le référentiel déjà fixé et génère le snapshot."""
    global PRISES, image_prises

    print("\n[D] Détection et classification des prises...")
    results = modele_yolo(frame, verbose=False)
    boxes   = results[0].boxes

    if len(boxes) == 0:
        print("[ERREUR] Aucune prise détectée.")
        return

    indices_mur, bbox_mur = detecter_mur_principal(boxes, w, h)

    PRISES = []
    for rank, i in enumerate(indices_mur):
        xyxy = boxes[i].xyxy[0].cpu().numpy()
        xmin, ymin, xmax, ymax = xyxy
        coins = np.array(
            [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]],
            dtype=np.float32
        )
        PRISES.append({
            "id":     rank + 1,
            "centre": ((xmin + xmax) / 2, (ymin + ymax) / 2),
            "coins":  coins,
            "conf":   float(boxes[i].conf[0]),
            "type":   "pied_only",
        })
    classifier_prises_par_taille(PRISES)

    # Snapshot
    xmin_mur, ymin_mur, xmax_mur, ymax_mur = bbox_mur
    image_prises = frame.copy()
    for i, box in enumerate(boxes):
        if i not in indices_mur:
            xyxy = box.xyxy[0].cpu().numpy()
            cv2.rectangle(image_prises,
                          (int(xyxy[0]), int(xyxy[1])),
                          (int(xyxy[2]), int(xyxy[3])),
                          (50, 50, 50), 1)
    for prise in PRISES:
        dessiner_prise(image_prises, prise["coins"], prise["type"])
    cv2.rectangle(image_prises,
                  (int(xmin_mur), int(ymin_mur)),
                  (int(xmax_mur), int(ymax_mur)),
                  (200, 200, 200), 2)
    orig = (int(xmin_mur), int(ymax_mur))
    cv2.circle(image_prises, orig, 8, (255, 100, 0), -1)
    cv2.putText(image_prises, "VERT=main+pied  BLEU=pied seul",
                (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    print(f"[OK] {len(PRISES)} prises classifiées et enregistrées.")


# =====================================================================
# 7. INSTANCE MEDIAPIPE + FONCTION detect_corps (interface pour app.py)
# =====================================================================
landmarker   = PoseLandmarker.create_from_options(options)
_frame_count = 0


def detect_corps(frame):
    """Interface compatible avec app.py — remplace detection_task.py."""
    global _frame_count
    _frame_count += 1
    h, w     = frame.shape[:2]
    frame_up = cv2.resize(
        cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        (int(w * UPSCALE), int(h * UPSCALE)),
    )
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_up)
    result   = landmarker.detect_for_video(mp_image, _frame_count)
    if result.pose_landmarks and len(result.pose_landmarks) > 0:
        return [
            {'x': lm.x, 'y': lm.y, 'visibility': lm.visibility}
            for lm in result.pose_landmarks[0]
        ], (w, h)
    return None, None


# =====================================================================
# 8. BOUCLE PRINCIPALE (exécution directe uniquement)
# =====================================================================
if __name__ == "__main__":
    cap         = cv2.VideoCapture(0)
    frame_count = 0

    print("\n--- PROGRAMME PRÊT ---")
    print("R : Détecter le mur + fixer le référentiel (réappuyez pour actualiser)")
    print("D : Détecter et classer les prises du mur")
    print("Q : Quitter")
    print("Légende : VERT=main+pied  BLEU=pied seul\n")

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        H     = None
        H_inv = None

        # --- HOMOGRAPHIE ---
        if ref_frame_gray is not None:
            kp_actuel, des_actuel = orb.detectAndCompute(gray, None)
            if des_actuel is not None and len(des_actuel) > 10:
                matches      = bf.match(ref_descriptors, des_actuel)
                matches      = sorted(matches, key=lambda x: x.distance)
                good_matches = matches[:60]
                if len(good_matches) > 15:
                    pts_ref     = np.float32([ref_keypoints[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                    pts_actuels = np.float32([kp_actuel[m.trainIdx].pt    for m in good_matches]).reshape(-1, 1, 2)
                    H, _        = cv2.findHomography(pts_ref, pts_actuels, cv2.RANSAC, 5.0)
                    if H is not None:
                        H_inv = np.linalg.inv(H)

        # FENÊTRE 1 : SNAPSHOT PRISES
        if image_prises is not None:
            cv2.imshow("Prises — Mur principal", image_prises)

        # FENÊTRE 2 : FLUX VIDÉO + SQUELETTE + PRISES PROCHES
        frame_up  = cv2.resize(frame, (int(w * UPSCALE), int(h * UPSCALE)))
        frame_rgb = cv2.cvtColor(frame_up, cv2.COLOR_BGR2RGB)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        frame_count += 1
        detection_result = landmarker.detect_for_video(mp_image, frame_count)

        landmarks_valides = {}

        if detection_result.pose_landmarks:
            landmarks = detection_result.pose_landmarks[0]
            for idx in range(11, 33):
                lm = landmarks[idx]
                if lm.visibility > 0.3:
                    landmarks_valides[idx] = (int(lm.x * w), int(lm.y * h))

            for p1, p2 in LIAISONS_CORPS:
                if p1 in landmarks_valides and p2 in landmarks_valides:
                    cv2.line(frame, landmarks_valides[p1], landmarks_valides[p2], (255, 255, 0), 2)

            for idx, (cx, cy) in landmarks_valides.items():
                cv2.circle(frame, (cx, cy), 5,
                           (0, 140, 255) if idx in MEMBRES else (0, 255, 255), -1)

            if PRISES:
                mettre_a_jour_grimpeur(landmarks_valides, H_inv)
                mettre_a_jour_prises_proches(landmarks_valides, H)

        # Zone pointillée cyan
        if zone_courante is not None:
            zx1, zy1, zx2, zy2 = zone_courante
            dash = 10
            for x in range(zx1, zx2, dash * 2):
                cv2.line(frame, (x, zy1), (min(x + dash, zx2), zy1), (0, 255, 255), 1)
                cv2.line(frame, (x, zy2), (min(x + dash, zx2), zy2), (0, 255, 255), 1)
            for y in range(zy1, zy2, dash * 2):
                cv2.line(frame, (zx1, y), (zx1, min(y + dash, zy2)), (0, 255, 255), 1)
                cv2.line(frame, (zx2, y), (zx2, min(y + dash, zy2)), (0, 255, 255), 1)

        for prise in PRISES_PROCHES:
            dessiner_prise(frame, prise["coins_ecran"], prise["type"])

        # Statut
        nb_pts = len(landmarks_valides)
        if ref_frame_gray is None:
            cv2.putText(frame, "R : detecter mur + referentiel", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        elif not PRISES:
            cv2.putText(frame, "Referentiel OK — D : detecter les prises", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
        else:
            statut  = f"ACTIF | {nb_pts}/22 pts | Prises proches : {len(PRISES_PROCHES)}"
            couleur = (0, 255, 0) if nb_pts > 10 else (0, 165, 255)
            cv2.putText(frame, statut, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, couleur, 2)

        cv2.putText(frame, "R=referentiel  D=prises  Q=quitter",
                    (15, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)
        cv2.imshow("Flux video — Squelette + Prises proches", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("r"):
            fixer_referentiel(frame, gray, w, h)
        elif key == ord("d"):
            if ref_frame_gray is None:
                print("[ERREUR] Fixez d'abord le référentiel avec R.")
            else:
                detecter_et_classer_prises(frame, w, h)

    cap.release()
    cv2.destroyAllWindows()
