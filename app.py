import streamlit as st
import cv2
import tempfile
from detect import detect_image

st.title("Détection de prises d'escalades")

# Télécharger une image
uploaded_file = st.file_uploader("Choisissez une image", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Enregistrer l'image temporairement
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tfile.write(uploaded_file.read())
    tfile.flush()

    # Afficher l'image originale
    st.image(uploaded_file, caption="Image originale")

    # Lancer la détection
    if st.button("Lancer la détection"):
        result = detect_image(tfile.name)

    # Convertir l'image annotée en format compatible avec Streamlit
        result = cv2.cvtColor(result, cv2.COLOR_BGR2RGB) 

    # Afficher l'image annotée
        st.image(result, caption="Résultat")