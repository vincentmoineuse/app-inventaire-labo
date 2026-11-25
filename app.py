import importlib
import os
import sys
import time

import streamlit as st


def _recharger_modules_modifies():
    """Streamlit Cloud relit les pages modifiées après un « git pull », mais garde en mémoire les
    modules déjà importés (database.py, fiche_tp.py…) : une page récente pourrait alors appeler une
    fonction que l'ancien module ne connaît pas (AttributeError). On recharge donc tout module dont
    le fichier a été modifié depuis son chargement."""
    try:   # date de démarrage du serveur (Linux / Streamlit Cloud)
        demarrage = os.stat(f"/proc/{os.getpid()}").st_ctime
    except OSError:
        demarrage = None
    for nom in ("database", "fiche_tp", "pictos", "fds_synth", "common"):
        mod = sys.modules.get(nom)
        fichier = getattr(mod, "__file__", None)
        if not fichier:
            continue
        try:
            modifie = os.path.getmtime(fichier)
        except OSError:
            continue
        charge = getattr(mod, "_charge_a", None) or demarrage
        if charge is None:
            mod._charge_a = time.time()
        elif modifie > charge:
            importlib.reload(mod)
            mod._charge_a = modifie


_recharger_modules_modifies()

from common import role_actuel, afficher_connexion  # noqa: E402

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
    pages += [
        st.Page("pages/filtres.py", title="Filtres", icon="🌀"),
        st.Page("pages/donnees_export.py", title="Données & Export", icon="💾"),
    ]

pg = st.navigation(pages)

with st.sidebar:
    st.caption("🔑 Connecté : administrateur" if role_actuel() == "admin" else "👀 Mode consultation (lecture seule)")
    if st.button("Se déconnecter", width="stretch"):
        for cle in ("role", "essais_echoues"):
            st.session_state.pop(cle, None)
        st.rerun()

pg.run()
