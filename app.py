import streamlit as st
from common import role_actuel, afficher_connexion

st.set_page_config(
    page_title="Inventaire Labo",
    page_icon="🧪",
    layout="wide",
)

if role_actuel() is None:
    afficher_connexion()

pages = [
    st.Page("pages/accueil.py", title="Accueil", icon="🧪", default=True),
    st.Page("pages/consultation.py", title="Consultation", icon="📋"),
]
if role_actuel() == "admin":
    pages += [
        st.Page("pages/ajouter_article.py", title="Ajouter un article", icon="➕"),
        st.Page("pages/session_inventaire.py", title="Session Inventaire", icon="🔍"),
    ]
pages += [
    st.Page("pages/tp.py", title="TP", icon="🧫"),
    st.Page("pages/commandes.py", title="Commandes", icon="🛒"),
    st.Page("pages/documents.py", title="Documents (FDS & notices)", icon="📄"),
    st.Page("pages/fiches_fds.py", title="Fiches FDS", icon="🗃️"),
]
if role_actuel() == "admin":
    pages.append(st.Page("pages/donnees_export.py", title="Données & Export", icon="💾"))

pg = st.navigation(pages)

with st.sidebar:
    st.caption("🔑 Connecté : administrateur" if role_actuel() == "admin" else "👀 Mode consultation (lecture seule)")
    if st.button("Se déconnecter", width="stretch"):
        for cle in ("role", "essais_echoues"):
            st.session_state.pop(cle, None)
        st.rerun()

pg.run()
