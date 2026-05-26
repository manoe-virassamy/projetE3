from ultralytics import YOLO 

# Charger modèle entrainé 
model = YOLO("best.pt")

# Détection
def detect_image(image_path):
    results = model.predict(
        source=image_path,
        conf=0.25,
        save=True
    )

    return results[0].plot()