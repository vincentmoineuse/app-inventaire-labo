import streamlit as st
import database as db
from pictos import afficher_pictogrammes
from datetime import datetime
from common import verifier_config

verifier_config()

st.title("🔍 Session d'inventaire")

session = db.obtenir_session_ouverte()

if session is None:
    st.info("Aucune session en cours. Démarre une nouvelle session pour commencer à pointer le matériel.")
    with st.form("nouvelle_session"):
        notes = st.text_input("Note sur cette session (optionnel)", placeholder="ex : Inventaire annuel labo physique")
        lancer = st.form_submit_button("▶️ Démarrer une session d'inventaire", width="stretch")
    if lancer:
        db.creer_session(notes=notes or None)
        st.rerun()
    st.stop()

# --- Session en cours ---
debut = datetime.fromisoformat(session["date_debut"]).strftime("%d/%m/%Y %H:%M")
st.success(f"📝 Session en cours depuis le {debut}" + (f" — *{session['notes']}*" if session["notes"] else ""))

col_a, col_b = st.columns([3, 1])
with col_b:
    if st.button("🏁 Clôturer la session", width="stretch"):
        db.cloturer_session(session["id"])
        st.success("Session clôturée. Bravo pour l'inventaire !")
        st.rerun()

# Filtres pour cibler la zone à pointer
f1, f2 = st.columns(2)
with f1:
    categorie = st.selectbox("Catégorie à pointer", ["Toutes"] + db.CATEGORIES)
with f2:
    salles = db.obtenir_salles()
    salle = st.selectbox("Salle à pointer", ["Toutes"] + salles)

articles = db.obtenir_articles(categorie=categorie, salle=salle)
deja_pointes = db.articles_pointes_session(session["id"])

restants = [a for a in articles if str(a["id"]) not in deja_pointes]
faits = [a for a in articles if str(a["id"]) in deja_pointes]

st.caption(f"✅ {len(faits)} pointé(s) — ⏳ {len(restants)} restant(s) sur cette sélection")
progress = len(faits) / len(articles) if articles else 0
st.progress(progress)

st.divider()

if not restants:
    st.success("Tous les articles de cette sélection ont été pointés ! Change de filtre ou clôture la session.")
else:
    st.subheader(f"À pointer ({len(restants)})")
    for a in restants:
        with st.container(border=True):
            cols = st.columns([1, 3, 2, 2])
            with cols[0]:
                if a["photo_path"]:
                    try:
                        st.image(a["photo_path"], width=80)
                    except Exception:
                        st.write("📦")
                else:
                    st.write("📦")
            with cols[1]:
                st.markdown(f"**{a['nom']}**")
                st.caption(a["categorie"])
                lieu = " / ".join(x for x in [a["salle"], a["armoire"]] if x)
                st.caption(f"📍 {lieu or 'non renseigné'}")
                if a.get("pictogrammes"):
                    afficher_pictogrammes(a["pictogrammes"], taille=36)
            with cols[2]:
                nouvelle_qte = st.number_input(
                    "Quantité constatée", min_value=0, value=a["quantite"],
                    key=f"qte_{a['id']}"
                )
                nouvelle_armoire = st.text_input(
                    "Armoire / emplacement", value=a["armoire"] or "", key=f"arm_{a['id']}"
                )
            with cols[3]:
                st.write("")
                st.write("")
                if st.button("✔️ Valider ce pointage", key=f"valider_{a['id']}", width="stretch"):
                    db.pointer_article(session["id"], a["id"], a["quantite"], int(nouvelle_qte))
                    if nouvelle_armoire.strip() != (a["armoire"] or ""):
                        db.modifier_article(a["id"], armoire=nouvelle_armoire.strip())
                    st.rerun()

if faits:
    with st.expander(f"✅ Articles déjà pointés dans cette session ({len(faits)})"):
        for a in faits:
            st.write(f"- **{a['nom']}** — quantité pointée : {a['quantite']} {a['unite'] or ''}")
