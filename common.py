import hmac
import time

import streamlit as st
import database as db

MAX_ESSAIS = 5


def role_actuel():
    """'admin', 'lecture' ou None (pas encore connecté)."""
    return st.session_state.get("role")


def est_admin():
    return role_actuel() == "admin"


def exiger_admin():
    """À appeler en haut des pages réservées à l'administrateur."""
    if not est_admin():
        st.error("🔒 Cette page est réservée à l'administrateur.")
        st.stop()


def _secret(nom):
    try:
        return str(st.secrets.get(nom, "") or "")
    except Exception:
        return ""


def _identiques(a, b):
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def afficher_connexion():
    """Écran d'accès : consultation seule, ou administrateur avec mot de passe.
    Appelle st.stop() tant que personne n'est connecté."""
    st.title("🧪 Inventaire du laboratoire")
    st.caption("Cité scolaire du Hainaut")

    echecs = st.session_state.get("essais_echoues", 0)
    if echecs >= MAX_ESSAIS:
        st.error("Trop de tentatives incorrectes. Recharge la page pour réessayer.")
        st.stop()

    onglet_lecture, onglet_admin = st.tabs(["👀 Consultation", "🔑 Administrateur"])

    with onglet_lecture:
        st.write("Accès en **lecture seule** : inventaire, commandes, fiches FDS, documents et TP.")
        code_requis = _secret("code_consultation")
        with st.form("connexion_lecture"):
            code = st.text_input("Code d'accès", type="password") if code_requis else ""
            entrer = st.form_submit_button("Entrer en consultation", width="stretch")
        if entrer:
            if code_requis and not _identiques(code, code_requis):
                st.session_state["essais_echoues"] = echecs + 1
                time.sleep(1)
                st.error("Code incorrect.")
            else:
                st.session_state["role"] = "lecture"
                st.rerun()

    with onglet_admin:
        mdp_admin = _secret("mot_de_passe_admin")
        if not mdp_admin:
            st.warning("Aucun mot de passe administrateur n'est configuré. Ajoute `mot_de_passe_admin` "
                       "dans les *Secrets* de Streamlit Cloud (voir SETUP.md, section 7).")
        with st.form("connexion_admin"):
            mdp = st.text_input("Mot de passe administrateur", type="password")
            entrer_admin = st.form_submit_button("Se connecter", width="stretch")
        if entrer_admin:
            if mdp_admin and _identiques(mdp, mdp_admin):
                st.session_state["role"] = "admin"
                st.rerun()
            else:
                st.session_state["essais_echoues"] = echecs + 1
                time.sleep(1)
                st.error("Mot de passe incorrect.")
    st.stop()


def verifier_config():
    """À appeler en haut de chaque page. Affiche un message clair si la
    configuration Supabase n'est pas encore renseignée, plutôt qu'une
    erreur technique brute."""
    try:
        db.init_db()
    except db.ConfigurationManquante as e:
        st.error(
            "⚙️ **Configuration Supabase incomplète.**\n\n"
            f"{e}\n\n"
            "Consulte le fichier **SETUP.md** du dépôt pour la procédure complète "
            "(création du projet Supabase, script SQL, bucket photos, puis "
            "renseignement des *Secrets* dans Streamlit Cloud)."
        )
        st.stop()
    except Exception as e:
        st.error(f"⚙️ Impossible de contacter Supabase : {e}")
        st.stop()
