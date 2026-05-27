import streamlit as st
import cv2
import tempfile
from detect import detect_image

st.title("Détection de prises d'escalades")

if "message" in st.session_state:
    st.success(st.session_state.message)
    del st.session_state.message

# Télécharger une image
uploaded_file = st.file_uploader("Choisissez une image", type=["jpg", "jpeg", "png"])

# Initialisation mémoire 
if "result" not in st.session_state:
    st.session_state.result = None

if "prises" not in st.session_state:
    st.session_state.prises = None

if "original_prises" not in st.session_state:
    st.session_state.original_prises = None

if uploaded_file is not None:
    # Enregistrer l'image temporairement
    tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    tfile.write(uploaded_file.read())
    tfile.flush()

    # Afficher l'image originale
    st.image(uploaded_file, caption="Image originale")

    # Lancer la détection
    if st.button("Lancer la détection"):
        result, prises = detect_image(tfile.name)

        # Sauvegarder en mémoire
        st.session_state.result = result
        st.session_state.prises = prises
        st.session_state.original_prises = [p.copy() for p in prises]  # Sauvegarde originale pour réinitialisation

# Affichage toujours actif
if st.session_state.result is not None:

    prises = st.session_state.prises

    if st.session_state.prises:

        #  ---- MENU DÉROULANT ----
        options = [f"Prise {p['id']} (score {p['score']:.2f})" for p in st.session_state.prises]

        selected = st.selectbox("Sélectionnez une prise :", options)

        index = options.index(selected)
        p = st.session_state.prises[index]

        # ---- SURLIGNER LA PRISE SÉLECTIONNÉE ----
        img = st.session_state.result.copy()
        coords = p["coords"]

        if len(coords) == 4:
            x1, y1, x2, y2 = map(int, coords)

            # rectangle rouge pour la prise sélectionnée
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 4)

            # point central de la prise
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2) 
            cv2.circle(img, (cx, cy), 6, (0, 0, 255), -1)
        
        else:
            st.warning("⚠️ Coordonnées invalides pour la prise {p['id']}.")

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        st.image(img, caption=f"Prise {p['id']} sélectionnée")

        # ---- AFFICHAGE DES INFORMATIONS DE LA PRISE ----
        st.subheader("Informations sur la prise")
        st.write(" 📍 Coordonnées : ", p["coords"])
        st.write(" 🎨 Couleur : ", p["couleur"])
        st.write(" 📏 Taille : ", p["taille"], "pixels²")

        # ---- CORRECTION UTILISATEUR ----
        st.subheader("Corriger les informations")

        new_couleur = st.text_input("Nouvelle couleur :", value=p["couleur"])
        new_taille = st.number_input("Nouvelle taille (pixels²) :", value=int(p["taille"]))

        x1, y1, x2, y2 = p["coords"]

        new_x1 = st.number_input("x1 :", value=int(x1))
        new_y1 = st.number_input("y1 :", value=int(y1))
        new_x2 = st.number_input("x2 :", value=int(x2))
        new_y2 = st.number_input("y2 :", value=int(y2))

        # ---- SAUVEGARDE DES CORRECTIONS ----
        if st.button("Valider les modifications"):
            st.session_state.prises[index]["couleur"] = new_couleur
            st.session_state.prises[index]["taille"] = new_taille
            st.session_state.prises[index]["coords"] = (new_x1, new_y1, new_x2, new_y2)
            st.success("Modifications enregistrées avec succès ! ✅")
        
        # ---- RESET DES CORRECTIONS ----
        if st.button("Réinitialiser les informations de la prise"):
            st.session_state.prises[index] = st.session_state.original_prises[index].copy()
            st.success("Informations réinitialisées avec succès ! ✅")

        # ---- SUPPRESSION DE LA PRISE ----
        if st.button("Supprimer la prise"):
            st.session_state.prises.pop(index)
            
            for i, prise in enumerate(st.session_state.prises):
                prise["id"] = i + 1
            
            st.success("Prise supprimée avec succès ! ✅")
            st.rerun()  # Rafraîchir la page pour mettre à jour le menu déroulant
        
    else:
        st.write("❌ Aucune prise détectée.")

# ---- AJOUT D'UNE NOUVELLE PRISE ----
if st.session_state.result is not None and st.session_state.prises is not None:

    st.markdown("---")
    st.subheader("Ajouter une nouvelle prise")

    add_x1 = st.number_input("x1 nouvelle prise:", key="add_x1")
    add_y1 = st.number_input("y1 nouvelle prise:", key="add_y1")
    add_x2 = st.number_input("x2 nouvelle prise:", value=50, key="add_x2")
    add_y2 = st.number_input("y2 nouvelle prise:", value=0, key="add_y2")

    x1 = int(min(add_x1, add_x2))
    y1 = int(min(add_y1, add_y2))
    x2 = int(max(add_x1, add_x2))
    y2 = int(max(add_y1, add_y2))

    add_couleur = st.text_input("Couleur nouvelle prise:", value="inconnue", key="add_couleur")
    add_taille = st.number_input("Taille nouvelle prise (pixels²):", value=100, key="add_taille")

    if st.button("Ajouter la prise"):

        if st.session_state.prises is None:
            st.session_state.prises = []
                    
        new_id = len(st.session_state.prises) + 1
                    
        new_prise = {
            "id": new_id,
            "score": 1.0,  # Score par défaut pour les prises ajoutées
            "coords": (x1, y1, x2, y2),
            "couleur": add_couleur,
            "taille": int(add_taille)
        }

        st.session_state.prises.append(new_prise)
        st.session_state.message = f"Prise {new_id} ajoutée avec succès ! ✅"

        st.rerun()  # Rafraîchir la page pour afficher la nouvelle prise dans le menu déroulant
