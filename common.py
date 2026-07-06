import streamlit as st
import database as db


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
