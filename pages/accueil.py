import streamlit as st
import pandas as pd
from datetime import datetime
import database as db
from pictos import afficher_pictogrammes
from common import verifier_config, est_admin

verifier_config()
ADMIN = est_admin()

st.title("🧪 Inventaire du matériel de laboratoire")
st.caption("Physique • Chimie • SVT • Informatique")

stats = db.statistiques()

col1, col2, col3 = st.columns(3)
col1.metric("Articles actifs", stats["total"])
col2.metric("Catégories utilisées", len(stats["par_categorie"]))
col3.metric("Péremptions < 60 jours", len(stats["peremption_proche"]))

st.divider()

c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("📊 Répartition par catégorie")
    if stats["par_categorie"]:
        df = pd.DataFrame(
            [{"Catégorie": r["categorie"], "Nombre d'articles": r["n"], "Quantité totale": r["qte"]}
             for r in stats["par_categorie"]]
        )
        st.bar_chart(df.set_index("Catégorie")["Nombre d'articles"])
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("Aucun article enregistré pour le moment. Rends-toi dans **➕ Ajouter un article** pour commencer.")

with c2:
    st.subheader("⚠️ Péremptions proches")
    if stats["peremption_proche"]:
        for a in stats["peremption_proche"]:
            jours = (datetime.strptime(a["date_peremption"], "%Y-%m-%d").date() - datetime.now().date()).days
            urgence = "🔴" if jours < 0 else ("🟠" if jours <= 14 else "🟡")
            statut = "**PÉRIMÉ**" if jours < 0 else f"{jours} j restants"
            st.markdown(f"{urgence} **{a['nom']}** — {a['date_peremption']} ({statut})")
            if a.get("pictogrammes"):
                afficher_pictogrammes(a["pictogrammes"], taille=32)
    else:
        st.success("Aucune péremption proche 👍")

    st.subheader("🛒 Commandes en cours")
    nb_commandes = len(db.obtenir_commandes(["À commander", "Commandée"]))
    if nb_commandes:
        st.markdown(f"🟡 **{nb_commandes}** commande{'s' if nb_commandes > 1 else ''} en cours — voir **🛒 Commandes**")
    else:
        st.success("Aucune commande en cours 👍")

st.divider()

session_ouverte = db.obtenir_session_ouverte()
if session_ouverte and ADMIN:
    st.warning(
        f"📝 Une session d'inventaire est en cours depuis le "
        f"{datetime.fromisoformat(session_ouverte['date_debut']).strftime('%d/%m/%Y %H:%M')}. "
        f"Rends-toi dans **🔍 Session Inventaire** pour la continuer."
    )

st.markdown("### Navigation")
menu = [
    "- **📋 Consultation** — parcourir, rechercher et filtrer l'inventaire",
]
if ADMIN:
    menu += [
        "- **➕ Ajouter un article** — ajouter un nouvel article (avec photo)",
        "- **🔍 Session Inventaire** — faire le point sur le matériel existant, salle par salle",
    ]
menu += [
    "- **🧫 TP** — " + ("préparer les travaux pratiques : matériel nécessaire, vérification du stock" if ADMIN
                       else "consulter les travaux pratiques et le matériel nécessaire"),
    "- **🛒 Commandes** — " + ("suivre les commandes de matériel et de produits, réception au stock" if ADMIN
                             else "voir les commandes en cours"),
    "- **📄 Documents (FDS & notices)** — " + ("consulter et attacher les fiches de sécurité et notices" if ADMIN
                                              else "consulter les fiches de sécurité et notices"),
]
menu.append("- **🗃️ Fiches FDS** — " + ("rédiger, valider et imprimer les fiches FDS synthétiques A4" if ADMIN
                                       else "consulter et télécharger les fiches FDS synthétiques validées"))
if ADMIN:
    menu.append("- **💾 Données & Export** — accès direct au tableau de bord Supabase, export CSV, historique des sessions")
st.markdown("Utilise le menu à gauche :\n" + "\n".join(menu))
