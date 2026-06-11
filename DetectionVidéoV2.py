import time
import urllib.request
import cv2
import numpy as np
import mediapipe as mp
from ultralytics import YOLO
from sklearn.cluster import DBSCAN

# =====================================================================
# CHEMIN DE LA VIDÉO — à modifier
# =====================================================================
VIDEO_PATH = "ma_video.mp4"

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

COULEUR_MAIN_PIED = (0, 255, 0)
COULEUR_PIED_ONLY = (255, 100, 0)

SEUIL_BAS_MIXTE  = 0.05
SEUIL_HAUT_MIXTE = 0.95

print("Chargement du modèle YOLOv8 (best.pt)...")
modele_yolo = YOLO("best.pt")

model_path = "pose_landmarker_heavy.task"
try:
    with open(model_path, "rb"): pass
except FileNotFoundError:
    print("Téléchargement du modèle MediaPipe Heavy...")
    url = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task"
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

# Conseil courant
CONSEIL = {
    "phrase":  None,
    "membre":  None,
    "cible":   None,
    "timestamp": 0.0,
}

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
INTERVALLE_PRISES = 2.0
derniere_update   = 0.0
derniere_prises   = 0.0
zone_courante     = None

en_pause          = False  # contrôle lecture
vitesse           = 1.0    # multiplicateur : 1=normal, 2=2x, 0.5=ralenti

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

    # Seuil = 65e percentile (35% plus grandes prises = main+pied)
    seuil = float(np.percentile(surfaces, 65))

    print(f"[CLASSIFICATION] min={min(surfaces):.0f} | seuil_65p={seuil:.0f} | max={max(surfaces):.0f}")

    for i, p in enumerate(prises):
        p["type"] = "main_pied" if surfaces[i] >= seuil else "pied_only"

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

    print(f"[MUR PRINCIPAL] {len(indices_mur)} prises retenues.")
    return indices_mur, bbox_mur


# =====================================================================
# 6. FONCTIONS RÉFÉRENTIEL ET PRISES
# =====================================================================

def fixer_referentiel(frame, gray, w, h):
    global ref_frame_gray, ref_keypoints, ref_descriptors
    global cadre_initial_points, origine_mur

    print("\n[R] Détection du mur + fixation du référentiel...")
    results = modele_yolo(frame, verbose=False)
    boxes   = results[0].boxes

    if len(boxes) == 0:
        print("[ERREUR] Aucune prise détectée.")
        return

    indices_mur, bbox_mur = detecter_mur_principal(boxes, w, h)
    xmin_mur, ymin_mur, xmax_mur, ymax_mur = bbox_mur

    origine_mur          = (xmin_mur, ymax_mur)
    cadre_initial_points = np.array([
        [xmin_mur, ymin_mur], [xmax_mur, ymin_mur],
        [xmax_mur, ymax_mur], [xmin_mur, ymax_mur]
    ], dtype=np.float32)

    ref_frame_gray                 = gray.copy()
    ref_keypoints, ref_descriptors = orb.detectAndCompute(ref_frame_gray, None)
    print(f"[OK] Référentiel fixé. Appuyez sur D pour détecter les prises.")


def detecter_et_classer_prises(frame, w, h):
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

    xmin_mur, ymin_mur, xmax_mur, ymax_mur = bbox_mur
    image_prises = frame.copy()
    for i, box in enumerate(boxes):
        if i not in indices_mur:
            xyxy = box.xyxy[0].cpu().numpy()
            cv2.rectangle(image_prises,
                          (int(xyxy[0]), int(xyxy[1])),
                          (int(xyxy[2]), int(xyxy[3])), (50, 50, 50), 1)
    for prise in PRISES:
        dessiner_prise(image_prises, prise["coins"], prise["type"])
    cv2.rectangle(image_prises,
                  (int(xmin_mur), int(ymin_mur)),
                  (int(xmax_mur), int(ymax_mur)), (200, 200, 200), 2)
    orig = (int(xmin_mur), int(ymax_mur))
    cv2.circle(image_prises, orig, 8, (255, 100, 0), -1)
    cv2.putText(image_prises, "VERT=main+pied  BLEU=pied seul",
                (15, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    print(f"[OK] {len(PRISES)} prises classifiées.")


# =====================================================================
# 7. FONCTIONS UTILITAIRES
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
    """
    Zone d'action par membre calculée dynamiquement depuis les landmarks :
    - Mains  : rayon = distance poignet -> épaule
    - Pieds  : rayon = distance cheville -> hanche, limité verticalement à la hanche
    """
    global PRISES_PROCHES, derniere_prises, zone_courante
    now = time.time()
    if now - derniere_prises < INTERVALLE_PRISES:
        return
    derniere_prises = now

    if not landmarks_valides:
        PRISES_PROCHES = []
        zone_courante  = None
        return

    def dist(a, b):
        return np.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

    def pt(idx):
        return landmarks_valides.get(idx)

    rayon_main_d = dist(pt(16), pt(12)) if pt(16) and pt(12) else MARGE_ZONE
    rayon_main_g = dist(pt(15), pt(11)) if pt(15) and pt(11) else MARGE_ZONE
    rayon_pied_d = dist(pt(28), pt(24)) if pt(28) and pt(24) else MARGE_ZONE
    rayon_pied_g = dist(pt(27), pt(23)) if pt(27) and pt(23) else MARGE_ZONE

    limite_y_pied_d = pt(24)[1] if pt(24) else None
    limite_y_pied_g = pt(23)[1] if pt(23) else None

    xs = [p[0] for p in landmarks_valides.values()]
    ys = [p[1] for p in landmarks_valides.values()]
    x_min = max(0, min(xs) - MARGE_ZONE)
    x_max = max(xs) + MARGE_ZONE
    y_min = max(0, min(ys) - MARGE_ZONE)
    y_max = max(ys) + MARGE_ZONE

    if pt(11) and pt(12):
        cx_split = (pt(11)[0] + pt(12)[0]) / 2
    else:
        cx_split = (x_min + x_max) / 2

    epaules_y = [landmarks_valides[i][1] for i in [11, 12] if i in landmarks_valides]
    hanches_y = [landmarks_valides[i][1] for i in [23, 24] if i in landmarks_valides]
    if epaules_y and hanches_y:
        cy_split = (sum(epaules_y)/len(epaules_y) + sum(hanches_y)/len(hanches_y)) / 2
    else:
        cy_split = (y_min + y_max) / 2

    zone_courante = (int(x_min), int(y_min), int(x_max), int(y_max),
                     int(cx_split), int(cy_split))

    MEMBRE_CONFIG = {
        "main_droite": {"origine": pt(16), "rayon": rayon_main_d, "limite_y": None},
        "main_gauche": {"origine": pt(15), "rayon": rayon_main_g, "limite_y": None},
        "pied_droit":  {"origine": pt(28), "rayon": rayon_pied_d, "limite_y": limite_y_pied_d},
        "pied_gauche": {"origine": pt(27), "rayon": rayon_pied_g, "limite_y": limite_y_pied_g},
    }

    PRISES_PROCHES = []
    vus = set()

    for zone_nom, cfg in MEMBRE_CONFIG.items():
        if cfg["origine"] is None:
            continue
        ox, oy   = cfg["origine"]
        rayon    = cfg["rayon"]
        limite_y = cfg["limite_y"]

        for prise in PRISES:
            if H is not None:
                centre_ecran = cv2.perspectiveTransform(
                    np.array([[prise["centre"]]], dtype=np.float32), H
                )[0][0]
                cx, cy = centre_ecran
            else:
                cx, cy = prise["centre"]

            if dist((ox, oy), (cx, cy)) > rayon:
                continue
            if limite_y is not None and cy < limite_y:
                continue

            coins_ecran = (
                cv2.perspectiveTransform(prise["coins"].reshape(-1, 1, 2), H).reshape(-1, 2)
                if H is not None else prise["coins"]
            )

            if cx < cx_split and cy < cy_split:
                zone = "main_gauche"
            elif cx >= cx_split and cy < cy_split:
                zone = "main_droite"
            elif cx < cx_split and cy >= cy_split:
                zone = "pied_gauche"
            else:
                zone = "pied_droit"

            key = (prise["id"], zone_nom)
            if key not in vus:
                vus.add(key)
                PRISES_PROCHES.append({
                    "id":          prise["id"],
                    "coins_ecran": coins_ecran,
                    "conf":        prise["conf"],
                    "type":        prise["type"],
                    "zone":        zone,
                    "membre":      zone_nom,
                })

    print(f"[PRISES PROCHES] {len(PRISES_PROCHES)} prises atteignables.")


def calculer_conseil(landmarks_valides, H_inv):
    global CONSEIL

    if not PRISES_PROCHES or not landmarks_valides:
        CONSEIL["phrase"] = None
        return

    pos_membres = {}
    for idx, cle in MEMBRES.items():
        if idx in landmarks_valides:
            pos_membres[cle] = landmarks_valides[idx]

    if not pos_membres:
        CONSEIL["phrase"] = None
        return

    QUADRANT_MEMBRE = {
        "main_droite":  "main_droite",
        "main_gauche":  "main_gauche",
        "pied_droit":   "pied_droit",
        "pied_gauche":  "pied_gauche",
    }

    meilleur_score  = -1e9
    meilleur_membre = None
    meilleure_prise = None

    for membre, zone_cible in QUADRANT_MEMBRE.items():
        if membre not in pos_membres:
            continue
        mx, my = pos_membres[membre]
        prises_zone = [p for p in PRISES_PROCHES if p["zone"] == zone_cible]
        if not prises_zone:
            continue

        for prise in prises_zone:
            cx = float(np.mean(prise["coins_ecran"][:, 0]))
            cy = float(np.mean(prise["coins_ecran"][:, 1]))
            progression  = my - cy
            penalite_lat = abs(cx - mx) * 0.2
            dist = np.sqrt((cx - mx)**2 + (cy - my)**2)
            if dist < 20:
                continue
            bonus_type = 10 if prise["type"] == "main_pied" else 0
            score = progression - penalite_lat + bonus_type
            if score > meilleur_score:
                meilleur_score  = score
                meilleur_membre = membre
                meilleure_prise = prise

    if meilleur_membre is None:
        CONSEIL["phrase"] = None
        return

    cx_cible = float(np.mean(meilleure_prise["coins_ecran"][:, 0]))
    cy_cible = float(np.mean(meilleure_prise["coins_ecran"][:, 1]))

    NOMS = {
        "main_droite":  "main droite",
        "main_gauche":  "main gauche",
        "pied_droit":   "pied droit",
        "pied_gauche":  "pied gauche",
    }
    mx, my = pos_membres[meilleur_membre]
    dx = cx_cible - mx
    dy = cy_cible - my

    if abs(dy) > abs(dx):
        direction = "en haut" if dy < 0 else "en bas"
    else:
        direction = "à droite" if dx > 0 else "à gauche"

    CONSEIL["phrase"]    = f"{NOMS[meilleur_membre].capitalize()} : {direction}"
    CONSEIL["membre"]    = meilleur_membre
    CONSEIL["cible"]     = (int(cx_cible), int(cy_cible))
    CONSEIL["timestamp"] = time.time()

# =====================================================================
# 8. BOUCLE PRINCIPALE
# =====================================================================
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print(f"[ERREUR] Impossible d'ouvrir la vidéo : {VIDEO_PATH}")
    exit()

fps_video   = cap.get(cv2.CAP_PROP_FPS) or 30
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frame_count  = 0
frame_index  = 0   # position dans la vidéo

with PoseLandmarker.create_from_options(options) as landmarker:
    print("\n--- PROGRAMME PRÊT ---")
    print(f"Vidéo : {VIDEO_PATH}  ({total_frames} frames, {fps_video:.0f} fps)")
    print("R       : Détecter mur + fixer référentiel (réappuyable)")
    print("D       : Détecter et classer les prises")
    print("ESPACE  : Pause / Reprendre")
    print("→ / ←   : Avancer / reculer de 30 frames (en pause)")
    print("Q       : Quitter")
    print("Légende : VERT=main+pied  BLEU=pied seul\n")

    while cap.isOpened():

        if not en_pause:
            success, frame = cap.read()
            if not success:
                print("[FIN] Vidéo terminée.")
                break
            frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        # En pause : on réutilise le dernier frame (frame déjà défini)

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

        # ==============================================================
        # FENÊTRE 1 : SNAPSHOT PRISES
        # ==============================================================
        if image_prises is not None:
            cv2.imshow("Prises — Mur principal", image_prises)

        # ==============================================================
        # FENÊTRE 2 : FLUX VIDÉO + SQUELETTE + PRISES PROCHES
        # ==============================================================
        display = frame.copy()

        # Squelette (uniquement si pas en pause pour ne pas re-inférer)
        if not en_pause:
            frame_up  = cv2.resize(frame, (int(w * UPSCALE), int(h * UPSCALE)))
            frame_rgb = cv2.cvtColor(frame_up, cv2.COLOR_BGR2RGB)
            mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            frame_count += 1
            # Timestamp basé sur la position dans la vidéo (en ms)
            timestamp_ms = int((frame_index / fps_video) * 1000)
            detection_result = landmarker.detect_for_video(mp_image, max(timestamp_ms, frame_count))

            landmarks_valides = {}
            if detection_result.pose_landmarks:
                landmarks = detection_result.pose_landmarks[0]
                for idx in range(11, 33):
                    lm = landmarks[idx]
                    if lm.visibility > 0.3:
                        landmarks_valides[idx] = (int(lm.x * w), int(lm.y * h))

                for p1, p2 in LIAISONS_CORPS:
                    if p1 in landmarks_valides and p2 in landmarks_valides:
                        cv2.line(display, landmarks_valides[p1], landmarks_valides[p2], (255, 255, 0), 2)
                for idx, (cx, cy) in landmarks_valides.items():
                    cv2.circle(display, (cx, cy), 5,
                               (0, 140, 255) if idx in MEMBRES else (0, 255, 255), -1)

                if PRISES:
                    mettre_a_jour_grimpeur(landmarks_valides, H_inv)
                    mettre_a_jour_prises_proches(landmarks_valides, H)
                    calculer_conseil(landmarks_valides, H_inv)

        # Zone en 4 quadrants
        if zone_courante is not None and len(zone_courante) == 6:
            zx1, zy1, zx2, zy2, zcx, zcy = zone_courante
            dash = 10
            LABELS_ZONE = {
                "main_gauche": (zx1 + 4,  zy1 + 14),
                "main_droite": (zcx + 4,  zy1 + 14),
                "pied_gauche": (zx1 + 4,  zcy + 14),
                "pied_droit":  (zcx + 4,  zcy + 14),
            }
            COULEURS_ZONE = {
                "main_gauche": (0, 200, 255),
                "main_droite": (0, 200, 255),
                "pied_gauche": (255, 180, 0),
                "pied_droit":  (255, 180, 0),
            }
            for label, pos in LABELS_ZONE.items():
                cv2.putText(display, label.replace("_", " "),
                            pos, cv2.FONT_HERSHEY_SIMPLEX, 0.32,
                            COULEURS_ZONE[label], 1)
            for x in range(zx1, zx2, dash * 2):
                cv2.line(display, (x, zy1), (min(x + dash, zx2), zy1), (0, 255, 255), 1)
                cv2.line(display, (x, zy2), (min(x + dash, zx2), zy2), (0, 255, 255), 1)
            for y in range(zy1, zy2, dash * 2):
                cv2.line(display, (zx1, y), (zx1, min(y + dash, zy2)), (0, 255, 255), 1)
                cv2.line(display, (zx2, y), (zx2, min(y + dash, zy2)), (0, 255, 255), 1)
            cv2.line(display, (zcx, zy1), (zcx, zy2), (200, 200, 200), 1)
            cv2.line(display, (zx1, zcy), (zx2, zcy), (200, 200, 200), 1)

        for prise in PRISES_PROCHES:
            dessiner_prise(display, prise["coins_ecran"], prise["type"])

        # Barre de progression
        progress = int((frame_index / max(total_frames, 1)) * w)
        cv2.rectangle(display, (0, h - 6), (progress, h), (100, 100, 255), -1)
        cv2.putText(display, f"{frame_index}/{total_frames}",
                    (w - 130, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

        # Icône pause
        if en_pause:
            cv2.putText(display, "|| PAUSE  <- -> : frame par frame",
                        (15, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)

        # Statut
        if ref_frame_gray is None:
            cv2.putText(display, "R : detecter mur + referentiel", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        elif not PRISES:
            cv2.putText(display, "Referentiel OK — D : detecter les prises", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 2)
        else:
            nb_pts  = len(landmarks_valides) if not en_pause else "-"
            statut  = f"ACTIF | {nb_pts}/22 pts | Prises proches : {len(PRISES_PROCHES)}"
            cv2.putText(display, statut, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        cv2.putText(display, f"R=ref  D=prises  ESPACE=pause  +/-=vitesse(x{vitesse:.1f})  Q=quitter",
                    (15, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

        # --- CONSEIL : flèche + texte ---
        if CONSEIL["phrase"] and CONSEIL["cible"] and CONSEIL["membre"]:
            membre_idx = {v: k for k, v in MEMBRES.items()}.get(CONSEIL["membre"])
            if membre_idx and membre_idx in landmarks_valides:
                pt_depart = landmarks_valides[membre_idx]
                pt_cible  = CONSEIL["cible"]
                cv2.arrowedLine(display, pt_depart, pt_cible, (0, 255, 255), 2,
                                tipLength=0.25)
                cv2.circle(display, pt_cible, 10, (0, 255, 255), 2)
            phrase = CONSEIL["phrase"]
            (tw, th), _ = cv2.getTextSize(phrase, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            tx, ty = 15, h - 45
            cv2.rectangle(display, (tx - 5, ty - th - 8), (tx + tw + 8, ty + 8),
                          (0, 0, 0), -1)
            cv2.putText(display, phrase, (tx, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.imshow("Vidéo — Squelette + Prises proches", display)

        # --- TOUCHES ---
        # En pause : attente longue pour ne pas consommer le CPU
        wait_ms = 0 if en_pause else max(1, int(1000 / (fps_video * vitesse)))
        key = cv2.waitKey(wait_ms) & 0xFF

        if key == ord("q"):
            break

        elif key == ord(" "):
            en_pause = not en_pause
            print(f"[{'PAUSE' if en_pause else 'LECTURE'}]")

        elif key == ord("+") or key == 171:  # + ou pavé num +
            vitesse = min(vitesse * 2, 16.0)
            print(f"[VITESSE] x{vitesse:.1f}")

        elif key == ord("-") or key == 173:  # - ou pavé num -
            vitesse = max(vitesse / 2, 0.25)
            print(f"[VITESSE] x{vitesse:.1f}")

        elif key == ord("r"):
            fixer_referentiel(frame, gray, w, h)

        elif key == ord("d"):
            if ref_frame_gray is None:
                print("[ERREUR] Fixez d'abord le référentiel avec R.")
            else:
                detecter_et_classer_prises(frame, w, h)

        # Navigation frame par frame (seulement en pause)
        elif key == 83 or key == ord("d") and en_pause:  # flèche droite
            if en_pause:
                new_pos = min(frame_index + 30, total_frames - 1)
                cap.set(cv2.CAP_PROP_POS_FRAMES, new_pos)
                success, frame = cap.read()
                if success:
                    frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

        elif key == 81:  # flèche gauche
            if en_pause:
                new_pos = max(frame_index - 32, 0)
                cap.set(cv2.CAP_PROP_POS_FRAMES, new_pos)
                success, frame = cap.read()
                if success:
                    frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

cap.release()
cv2.destroyAllWindows()
