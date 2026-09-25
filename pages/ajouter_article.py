import streamlit as st
import time
import database as db
from common import verifier_config

verifier_config()

st.title("➕ Ajouter un article à l'inventaire")

categorie = st.selectbox("Catégorie", db.CATEGORIES, key="add_categorie")

if "photo_uploader_key" not in st.session_state:
    st.session_state.photo_uploader_key = 0

st.markdown("**Photo de l'article ou de l'étiquette**")
st.markdown("""
<style>
[data-testid="stFileUploaderDropzoneInstructions"] { display: none !important; }
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] { display: none !important; }
[data-testid="stFileUploaderDropzone"] button p { font-size: 0; }
[data-testid="stFileUploaderDropzone"] button p::after {
    content: "📷 Prendre ou importer une photo";
    font-size: 1rem;
    font-weight: 600;
}
[data-testid="stFileUploaderDropzone"] { justify-content: center !important; padding: 0.5rem !important; }
[data-testid="stFileUploaderDropzone"] button { width: 100%; padding: 0.75rem !important; }
</style>
""", unsafe_allow_html=True)
photo_upload = st.file_uploader(
    "📷 Prendre ou importer une photo", type=["jpg", "jpeg", "png"],
    key=f"photo_upload_{st.session_state.photo_uploader_key}",
    label_visibility="collapsed",
)
if photo_upload is not None:
    st.image(photo_upload, width=150, caption="Photo sélectionnée")

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

    submit = st.form_submit_button("✅ Ajouter à l'inventaire", use_container_width=True)

if submit:
    if not nom or not salle:
        st.error("Merci de renseigner au minimum le **nom** et la **salle**.")
    else:
        photo_path = None
        if photo_upload is not None:
            filename = f"article_{int(time.time())}_{nom[:20].replace(' ', '_')}.jpg"
            filename = "".join(c for c in filename if c.isalnum() or c in "._-")
            with st.spinner("Envoi de la photo..."):
                photo_path = db.upload_photo(photo_upload.getvalue(), filename)

        db.ajouter_article(
            nom=nom, categorie=categorie, quantite=int(quantite), unite=unite,
            salle=salle, armoire=armoire, photo_path=photo_path,
            numero_cas=numero_cas, pictogrammes=pictos_str, date_peremption=date_perempt,
            notes=notes or None,
        )
        st.session_state.photo_uploader_key += 1
        st.session_state.article_ajoute = f"{nom} ({categorie})"
        st.rerun()

if st.session_state.get("article_ajoute"):
    st.success(f"✅ « {st.session_state.article_ajoute} » ajouté à l'inventaire.")
    st.balloons()
    del st.session_state["article_ajoute"]

st.divider()
st.caption("Astuce : pour pointer/mettre à jour les quantités d'articles déjà existants, utilise plutôt la page **🔍 Session Inventaire**.")
