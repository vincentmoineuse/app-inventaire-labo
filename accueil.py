import streamlit as st
import pandas as pd
from datetime import datetime
import database as db
from common import verifier_config

verifier_config()

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
        st.dataframe(df, use_container_width=True, hide_index=True)
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
    else:
        st.success("Aucune péremption proche 👍")

st.divider()

session_ouverte = db.obtenir_session_ouverte()
if session_ouverte:
    st.warning(
        f"📝 Une session d'inventaire est en cours depuis le "
        f"{datetime.fromisoformat(session_ouverte['date_debut']).strftime('%d/%m/%Y %H:%M')}. "
        f"Rends-toi dans **🔍 Session Inventaire** pour la continuer."
    )

st.markdown("""
### Navigation
Utilise le menu à gauche :
- **📋 Consultation** — parcourir, rechercher et filtrer l'inventaire
- **➕ Ajouter un article** — ajouter un nouvel article (avec photo)
- **🔍 Session Inventaire** — faire le point sur le matériel existant, salle par salle
- **💾 Données & Export** — accès direct au tableau de bord Supabase, export CSV, historique des sessions
""")
