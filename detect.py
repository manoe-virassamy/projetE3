from ultralytics import YOLO 
import cv2
from tkinter import Tk
from tkinter.filedialog import askopenfilename

# Choisir une image
Tk().withdraw()
image_path = askopenfilename(
    title="Choisir une image",
    filetypes=[("Images", "*.jpg *.png *.jpeg")]
)

if not image_path:
    print("Aucune image sélectionnée")
    exit()

# Charger modèle entrainé 
model = YOLO("best.pt")

# Détection
results = model.predict(
    source=image_path,
    conf=0.25,
    save=True
)

# Affichage
annotated = results[0].plot()

cv2.imshow("Detection prises", annotated)
cv2.waitKey(0)
cv2.destroyAllWindows