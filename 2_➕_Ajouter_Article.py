import streamlit as st
import time
import database as db
from common import verifier_config

st.set_page_config(page_title="Ajouter un article", page_icon="➕", layout="wide")
verifier_config()

st.title("➕ Ajouter un article à l'inventaire")

categorie = st.selectbox("Catégorie", db.CATEGORIES, key="add_categorie")

with st.form("ajout_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        nom = st.text_input("Nom de l'article *")
        quantite = st.number_input("Quantité *", min_value=0, value=1)
        unite = st.text_input("Unité", value="unité(s)", help="ex : unité(s), boîte(s), L, mL, kg, g...")
    with c2:
        salle = st.text_input("Salle *", placeholder="ex : Labo Physique 1")
        armoire = st.text_input("Armoire / emplacement", placeholder="ex : Armoire 3, étagère B")
        notes = st.text_area("Notes (optionnel)")

    numero_cas = pictos_str = date_perempt = None
    if categorie == db.CATEGORIE_CHIMIE:
        st.markdown("**Champs sécurité (produit chimique)**")
        cc1, cc2 = st.columns(2)
        with cc1:
            numero_cas = st.text_input("Numéro CAS", placeholder="ex : 64-17-5")
            date_input = st.date_input("Date de péremption", value=None)
            date_perempt = date_input.isoformat() if date_input else None
        with cc2:
            pictos = st.multiselect("Pictogrammes de danger (SGH)", db.PICTOGRAMMES_GHS)
            pictos_str = ", ".join(pictos) if pictos else None

    st.markdown("**Photo de l'article ou de l'étiquette**")
    photo_cam = st.camera_input("Prendre une photo")
    photo_upload = st.file_uploader("...ou importer une photo existante", type=["jpg", "jpeg", "png"])

    submit = st.form_submit_button("✅ Ajouter à l'inventaire", use_container_width=True)

if submit:
    if not nom or not salle:
        st.error("Merci de renseigner au minimum le **nom** et la **salle**.")
    else:
        photo_path = None
        source_photo = photo_cam or photo_upload
        if source_photo is not None:
            filename = f"article_{int(time.time())}_{nom[:20].replace(' ', '_')}.jpg"
            filename = "".join(c for c in filename if c.isalnum() or c in "._-")
            with st.spinner("Envoi de la photo..."):
                photo_path = db.upload_photo(source_photo.getbuffer().tobytes(), filename)

        db.ajouter_article(
            nom=nom, categorie=categorie, quantite=int(quantite), unite=unite,
            salle=salle, armoire=armoire, photo_path=photo_path,
            numero_cas=numero_cas, pictogrammes=pictos_str, date_peremption=date_perempt,
            notes=notes or None,
        )
        st.success(f"✅ « {nom} » ajouté à la catégorie {categorie}.")
        st.balloons()

st.divider()
st.caption("Astuce : pour pointer/mettre à jour les quantités d'articles déjà existants, utilise plutôt la page **🔍 Session Inventaire**.")
