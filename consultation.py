import streamlit as st
import database as db
from common import verifier_config

verifier_config()

st.title("📋 Consultation de l'inventaire")

# --- Filtres ---
f1, f2, f3 = st.columns(3)
with f1:
    categorie = st.selectbox("Catégorie", ["Toutes"] + db.CATEGORIES)
with f2:
    salles = db.obtenir_salles()
    salle = st.selectbox("Salle", ["Toutes"] + salles)
with f3:
    recherche = st.text_input("Rechercher un article (nom)")

articles = db.obtenir_articles(categorie=categorie, salle=salle, recherche=recherche or None)

st.caption(f"{len(articles)} article(s) trouvé(s)")
st.divider()

if not articles:
    st.info("Aucun article ne correspond à ces critères.")
else:
    # Regrouper par catégorie pour affichage
    par_cat = {}
    for a in articles:
        par_cat.setdefault(a["categorie"], []).append(a)

    for cat, items in par_cat.items():
        with st.expander(f"**{cat}** ({len(items)})", expanded=(categorie != "Toutes")):
            for a in items:
                cols = st.columns([1, 3, 2, 2, 1])
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
                    if a["notes"]:
                        st.caption(a["notes"])
                    if a["categorie"] == db.CATEGORIE_CHIMIE:
                        infos = []
                        if a["numero_cas"]:
                            infos.append(f"CAS : {a['numero_cas']}")
                        if a["date_peremption"]:
                            infos.append(f"Péremption : {a['date_peremption']}")
                        if infos:
                            st.caption(" • ".join(infos))
                        if a["pictogrammes"]:
                            st.caption("⚠️ " + a["pictogrammes"])
                with cols[2]:
                    st.write(f"Qté : **{a['quantite']} {a['unite'] or ''}**")
                with cols[3]:
                    lieu = " / ".join(x for x in [a["salle"], a["armoire"]] if x)
                    st.write(f"📍 {lieu or 'non renseigné'}")
                with cols[4]:
                    if st.button("✏️", key=f"edit_{a['id']}", help="Modifier"):
                        st.session_state["edit_article_id"] = a["id"]
                st.divider()

# --- Formulaire d'édition ---
if "edit_article_id" in st.session_state:
    article = db.obtenir_article(st.session_state["edit_article_id"])
    if article:
        st.subheader(f"✏️ Modifier : {article['nom']}")
        with st.form("edit_form"):
            c1, c2 = st.columns(2)
            with c1:
                nom = st.text_input("Nom", value=article["nom"])
                categorie_e = st.selectbox("Catégorie", db.CATEGORIES,
                                            index=db.CATEGORIES.index(article["categorie"]))
                quantite = st.number_input("Quantité", min_value=0, value=article["quantite"])
                unite = st.text_input("Unité", value=article["unite"] or "unité(s)")
            with c2:
                salle_e = st.text_input("Salle", value=article["salle"] or "")
                armoire_e = st.text_input("Armoire / emplacement", value=article["armoire"] or "")
                notes = st.text_area("Notes", value=article["notes"] or "")

            numero_cas, pictos_str, date_perempt = article["numero_cas"], article["pictogrammes"], article["date_peremption"]
            if categorie_e == db.CATEGORIE_CHIMIE:
                st.markdown("**Champs sécurité (produit chimique)**")
                cc1, cc2 = st.columns(2)
                with cc1:
                    numero_cas = st.text_input("Numéro CAS", value=article["numero_cas"] or "")
                    import datetime as dt
                    val_date = None
                    if article["date_peremption"]:
                        try:
                            val_date = dt.datetime.strptime(article["date_peremption"], "%Y-%m-%d").date()
                        except ValueError:
                            val_date = None
                    date_input = st.date_input("Date de péremption", value=val_date)
                    date_perempt = date_input.isoformat() if date_input else None
                with cc2:
                    deja = (article["pictogrammes"] or "").split(", ") if article["pictogrammes"] else []
                    pictos = st.multiselect("Pictogrammes de danger", db.PICTOGRAMMES_GHS, default=[p for p in deja if p in db.PICTOGRAMMES_GHS])
                    pictos_str = ", ".join(pictos) if pictos else None

            nouvelle_photo = st.camera_input("Reprendre une photo (optionnel)")

            c3, c4 = st.columns(2)
            enregistrer = c3.form_submit_button("💾 Enregistrer", use_container_width=True)
            annuler = c4.form_submit_button("Annuler", use_container_width=True)
            supprimer = st.form_submit_button("🗑️ Supprimer cet article", use_container_width=True)

        if enregistrer:
            maj = dict(
                nom=nom, categorie=categorie_e, quantite=int(quantite), unite=unite,
                salle=salle_e, armoire=armoire_e, notes=notes,
                numero_cas=numero_cas if categorie_e == db.CATEGORIE_CHIMIE else None,
                pictogrammes=pictos_str if categorie_e == db.CATEGORIE_CHIMIE else None,
                date_peremption=date_perempt if categorie_e == db.CATEGORIE_CHIMIE else None,
            )
            if nouvelle_photo is not None:
                import time
                photo_filename = f"article_{article['id']}_{int(time.time())}.jpg"
                with st.spinner("Envoi de la photo..."):
                    photo_url = db.upload_photo(nouvelle_photo.getbuffer().tobytes(), photo_filename)
                maj["photo_path"] = photo_url
            db.modifier_article(article["id"], **maj)
            del st.session_state["edit_article_id"]
            st.success("Article mis à jour.")
            st.rerun()

        if annuler:
            del st.session_state["edit_article_id"]
            st.rerun()

        if supprimer:
            db.supprimer_article(article["id"])
            del st.session_state["edit_article_id"]
            st.success("Article supprimé.")
            st.rerun()
