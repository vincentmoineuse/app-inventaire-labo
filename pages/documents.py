import streamlit as st
import database as db
from common import verifier_config

verifier_config()

st.title("📄 Documents : FDS & notices")
st.caption(
    "Retrouve ici tous les PDF déjà rattachés à un article, et attache facilement une FDS "
    "ou une notice existante (par exemple depuis ton dossier de FDS) à un article de l'inventaire."
)

tous_les_articles = db.obtenir_articles()

tab_fds, tab_notices = st.tabs(["🧪 Fiches de Données de Sécurité (FDS)", "📘 Notices"])

# ---------- Onglet FDS ----------
with tab_fds:
    produits_chimiques = [a for a in tous_les_articles if a["categorie"] == db.CATEGORIE_CHIMIE]
    avec_fds = [a for a in produits_chimiques if a.get("fds_path")]
    sans_fds = [a for a in produits_chimiques if not a.get("fds_path")]

    st.subheader(f"FDS déjà attachées ({len(avec_fds)})")
    if avec_fds:
        for a in sorted(avec_fds, key=lambda x: x["nom"]):
            c1, c2 = st.columns([4, 1])
            cas = f" — CAS {a['numero_cas']}" if a.get("numero_cas") else ""
            c1.write(f"**{a['nom']}**{cas}")
            c2.link_button("📄 Ouvrir", a["fds_path"], use_container_width=True)
    else:
        st.info("Aucune FDS attachée pour le moment.")

    st.divider()
    st.subheader(f"Attacher une FDS à un produit chimique ({len(sans_fds)} sans FDS)")
    if not produits_chimiques:
        st.info("Aucun produit chimique dans l'inventaire pour le moment.")
    else:
        options = sans_fds if sans_fds else produits_chimiques
        choix = st.selectbox(
            "Produit chimique", options,
            format_func=lambda a: f"{a['nom']}" + (f" (CAS {a['numero_cas']})" if a.get("numero_cas") else ""),
            key="choix_fds",
        )
        pdf_fds = st.file_uploader("Fichier PDF de la FDS", type=["pdf"], key="upload_fds_doc")
        if st.button("📤 Attacher cette FDS", disabled=pdf_fds is None, key="btn_attacher_fds"):
            with st.spinner("Envoi en cours..."):
                url = db.upload_document(pdf_fds.getvalue(), f"{choix['nom']}.pdf", "fds")
                db.modifier_article(choix["id"], fds_path=url)
            st.success(f"FDS attachée à « {choix['nom']} ».")
            st.rerun()

# ---------- Onglet Notices ----------
with tab_notices:
    avec_notice = [a for a in tous_les_articles if a.get("notice_path")]
    sans_notice = [a for a in tous_les_articles if not a.get("notice_path")]

    st.subheader(f"Notices déjà attachées ({len(avec_notice)})")
    if avec_notice:
        for a in sorted(avec_notice, key=lambda x: (x["categorie"], x["nom"])):
            c1, c2 = st.columns([4, 1])
            c1.write(f"**{a['nom']}** — {a['categorie']}")
            c2.link_button("📄 Ouvrir", a["notice_path"], use_container_width=True)
    else:
        st.info("Aucune notice attachée pour le moment.")

    st.divider()
    st.subheader(f"Attacher une notice à un article ({len(sans_notice)} sans notice)")
    if not tous_les_articles:
        st.info("Aucun article dans l'inventaire pour le moment.")
    else:
        options = sans_notice if sans_notice else tous_les_articles
        choix = st.selectbox(
            "Article", options,
            format_func=lambda a: f"{a['nom']} ({a['categorie']})",
            key="choix_notice",
        )
        pdf_notice = st.file_uploader("Fichier PDF de la notice", type=["pdf"], key="upload_notice_doc")
        if st.button("📤 Attacher cette notice", disabled=pdf_notice is None, key="btn_attacher_notice"):
            with st.spinner("Envoi en cours..."):
                url = db.upload_document(pdf_notice.getvalue(), f"{choix['nom']}.pdf", "notices")
                db.modifier_article(choix["id"], notice_path=url)
            st.success(f"Notice attachée à « {choix['nom']} ».")
            st.rerun()
