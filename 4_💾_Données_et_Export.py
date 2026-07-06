import streamlit as st
import pandas as pd
from datetime import datetime
import database as db
from common import verifier_config

st.set_page_config(page_title="Données & Export", page_icon="💾", layout="wide")
verifier_config()

st.title("💾 Données & export")

st.markdown("""
Les données de l'inventaire sont stockées **en direct dans Supabase** (base Postgres + stockage
des photos) : il n'y a donc rien à sauvegarder manuellement, elles restent disponibles même si
l'application redémarre. Tu peux aussi consulter ou modifier les tables directement depuis le
tableau de bord Supabase si besoin.
""")

supabase_url = st.secrets.get("supabase_url", "")
project_ref = None
if supabase_url:
    # https://<project_ref>.supabase.co -> extraire project_ref
    try:
        project_ref = supabase_url.split("//")[1].split(".")[0]
    except IndexError:
        project_ref = None

if project_ref:
    st.link_button("🔗 Ouvrir l'éditeur de tables Supabase",
                    f"https://supabase.com/dashboard/project/{project_ref}/editor",
                    use_container_width=True)
    st.link_button("🔗 Ouvrir le stockage des photos (bucket 'photos')",
                    f"https://supabase.com/dashboard/project/{project_ref}/storage/buckets/{db.PHOTOS_BUCKET}",
                    use_container_width=True)

st.divider()

st.subheader("⬇️ Export CSV")
st.caption("Utile pour une analyse dans un tableur, une impression, ou une sauvegarde ponctuelle hors ligne.")

articles = db.obtenir_articles()
if articles:
    df = pd.DataFrame(articles)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Télécharger l'inventaire complet (.csv)",
        data=csv,
        file_name=f"inventaire_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        use_container_width=True,
    )
else:
    st.info("Aucun article à exporter pour le moment.")

st.divider()

st.subheader("📈 État actuel des données")
stats = db.statistiques()
c1, c2 = st.columns(2)
c1.metric("Articles enregistrés", stats["total"])
c2.metric("Catégories utilisées", len(stats["par_categorie"]))

sessions = db.obtenir_sessions()
if sessions:
    st.markdown("**Historique des sessions d'inventaire**")
    for s in sessions:
        statut = "🟢 en cours" if not s.get("date_fin") else "✅ clôturée"
        try:
            debut = datetime.fromisoformat(s["date_debut"]).strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            debut = s["date_debut"]
        st.write(f"- Session #{s['id']} — {debut} — {statut}" + (f" — *{s['notes']}*" if s.get("notes") else ""))
