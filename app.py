import streamlit as st

st.set_page_config(
    page_title="Inventaire Labo",
    page_icon="🧪",
    layout="wide",
)

pg = st.navigation([
    st.Page("pages/accueil.py", title="Accueil", icon="🧪", default=True),
    st.Page("pages/consultation.py", title="Consultation", icon="📋"),
    st.Page("pages/ajouter_article.py", title="Ajouter un article", icon="➕"),
    st.Page("pages/session_inventaire.py", title="Session Inventaire", icon="🔍"),
    st.Page("pages/donnees_export.py", title="Données & Export", icon="💾"),
])
pg.run()
