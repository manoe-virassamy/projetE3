import cv2
import numpy as np
import threading
import time

# Résolution de travail pour l'extraction de features
_REF_W, _REF_H = 640, 480


def preparer_reference(img_bgr):
    """
    Extrait les features ORB de l'image de référence (photo originale du mur).
    Retourne un dict {kp, desc, orig_w, orig_h}.
    """
    h, w = img_bgr.shape[:2]
    img_r = cv2.resize(img_bgr, (_REF_W, _REF_H))
    orb   = cv2.ORB_create(nfeatures=4000)
    gray  = cv2.cvtColor(img_r, cv2.COLOR_BGR2GRAY)
    kp, desc = orb.detectAndCompute(gray, None)
    return {'kp': kp, 'desc': desc, 'orig_w': w, 'orig_h': h}


def _calculer_H(kp_ref, desc_ref, frame_live, orb, bf):
    """
    Calcule H : espace ref_640x480 → espace live.
    Utilise le ratio test de Lowe (0.75) — plus robuste aux changements d'angle
    que le filtre par distance fixe.
    Retourne None si insuffisamment de correspondances cohérentes.
    """
    gray = cv2.cvtColor(frame_live, cv2.COLOR_BGR2GRAY)
    kp_l, desc_l = orb.detectAndCompute(gray, None)

    if desc_l is None or len(kp_l) < 10:
        return None

    # Ratio test de Lowe : garde les correspondances où le meilleur match
    # est nettement meilleur que le deuxième → bien plus robuste que crossCheck
    raw = bf.knnMatch(desc_ref, desc_l, k=2)
    good = []
    for pair in raw:
        if len(pair) == 2:
            m, n = pair
            if m.distance < 0.75 * n.distance:
                good.append(m)

    if len(good) < 10:
        return None

    pts_r = np.float32([kp_ref[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    pts_l = np.float32([kp_l[m.trainIdx].pt   for m in good]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(pts_r, pts_l, cv2.RANSAC, 5.0)
    if H is None or mask is None:
        return None

    # Au moins 10 inliers RANSAC pour valider la cohérence géométrique
    if int(mask.sum()) < 10:
        return None

    # Rejeter les homographies trop déformantes (déterminant aberrant)
    det = abs(np.linalg.det(H[:2, :2]))
    return H if 0.05 < det < 20.0 else None


def transformer_prises(prises_ref, H, orig_w, orig_h, live_w, live_h):
    """
    Projette les centres des prises (espace image originale) vers l'espace live.

    Si H est disponible  : projection homographique précise, suit le mur.
    Si H est None        : mise à l'échelle simple (fallback proportionnel).

    Retourne une liste de {'coords': (px, py) | None, 'usage': str}.
    coords = None quand la prise est hors du champ de la caméra.
    """
    if not prises_ref:
        return []

    sx = _REF_W / orig_w
    sy = _REF_H / orig_h

    centres = np.float32([
        [p['ref_cx'] * sx, p['ref_cy'] * sy]
        for p in prises_ref
    ]).reshape(-1, 1, 2)

    if H is not None:
        pts = cv2.perspectiveTransform(centres, H)
    else:
        # Fallback : mise à l'échelle directe ref → live
        pts = centres * np.float32([live_w / _REF_W, live_h / _REF_H])

    result = []
    for i, pt in enumerate(pts):
        px, py = int(pt[0][0]), int(pt[0][1])
        visible = (0 <= px < live_w) and (0 <= py < live_h)
        result.append({
            'coords': (px, py) if visible else None,
            'usage':  prises_ref[i]['usage'],
        })
    return result


class HomographyWorker:
    """
    Thread de fond qui maintient la dernière homographie valide.
    La dernière H valide est conservée indéfiniment — évite le fallback statique
    lors d'occultations temporaires (grimpeur devant le mur, etc.).
    """

    def __init__(self, ref_data):
        self._kp      = ref_data['kp']
        self._desc    = ref_data['desc']
        self._H       = None
        self._pending = None
        self._lock    = threading.Lock()
        self.running  = True
        # ORB et BFMatcher instanciés une seule fois pour le thread de fond
        self._orb     = cv2.ORB_create(nfeatures=4000)
        self._bf      = cv2.BFMatcher(cv2.NORM_HAMMING)
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, frame):
        with self._lock:
            self._pending = frame.copy()

    def _worker(self):
        while self.running:
            frame = None
            with self._lock:
                frame, self._pending = self._pending, None
            if frame is not None:
                H = _calculer_H(self._kp, self._desc, frame, self._orb, self._bf)
                if H is not None:
                    with self._lock:
                        self._H = H
            else:
                time.sleep(0.005)

    def fixer_repere(self, frame):
        """
        Prend frame comme nouveau référentiel ORB.
        Réinitialise H à None — sera recalculé dès la prochaine frame soumise.
        Retourne (orig_w, orig_h) de la frame de référence.
        """
        ref_data = preparer_reference(frame)
        with self._lock:
            self._kp   = ref_data['kp']
            self._desc = ref_data['desc']
            self._H    = None
        return ref_data['orig_w'], ref_data['orig_h']

    def get_H(self):
        with self._lock:
            return self._H

    def stop(self):
        self.running = False
