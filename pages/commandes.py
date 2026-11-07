import streamlit as st
from datetime import date, datetime
import database as db
from common import verifier_config, est_admin

verifier_config()
ADMIN = est_admin()

st.title("🛒 Commandes")
st.caption("Prépare tes commandes de matériel et de produits, suis leur avancement et ajoute les quantités reçues au stock.")

EMOJI = {"À commander": "🛒", "Commandée": "🚚", "Reçue": "✅", "Annulée": "❌"}


def _date(valeur):
    try:
        return datetime.strptime(str(valeur)[:10], "%Y-%m-%d").date() if valeur else None
    except ValueError:
        return None


def _euros(x):
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


toutes = db.obtenir_commandes()
a_commander = [c for c in toutes if c["statut"] == "À commander"]
commandees = [c for c in toutes if c["statut"] == "Commandée"]

m1, m2, m3 = st.columns(3)
m1.metric("À commander", len(a_commander))
m2.metric("Commandées (en attente)", len(commandees))
if ADMIN:
    m3.metric("Montant estimé en cours", _euros(sum(db.total_commande(c["id"]) for c in a_commander + commandees)))

resultat = st.session_state.pop("recep_resultat", None)
if resultat:
    st.success(f"📦 Commande « {resultat[0]} » réceptionnée : les quantités des articles liés ont été ajoutées au stock.")
    if resultat[1]:
        st.warning("À mettre à jour manuellement (unités différentes) :\n\n- " + "\n- ".join(resultat[1]))

if ADMIN:
    tab_liste, tab_nouvelle = st.tabs(["📋 Commandes", "➕ Nouvelle commande"])
else:
    (tab_liste,) = st.tabs(["📋 Commandes"])

# ---------- Nouvelle commande ----------
if ADMIN:
    with tab_nouvelle:
        if st.session_state.get("cmd_creee"):
            st.success(f"✅ Commande « {st.session_state.pop('cmd_creee')} » créée. "
                       "Ajoute-lui des lignes depuis l'onglet **Commandes**.")
        with st.form("nouvelle_commande", clear_on_submit=True):
            titre = st.text_input("Titre *", placeholder="ex : Réactifs TP de chimie — novembre")
            fournisseur = st.text_input("Fournisseur", placeholder="ex : VWR, Jeulin, Sigma-Aldrich…")
            notes = st.text_area("Notes (n° de devis, référence du bon de commande…)")
            creer = st.form_submit_button("✅ Créer la commande", width="stretch")
        if creer:
            if not titre.strip():
                st.error("Merci de donner un titre à la commande.")
            else:
                db.creer_commande(titre.strip(), fournisseur.strip() or None, notes.strip() or None)
                st.session_state["cmd_creee"] = titre.strip()
                st.rerun()

# ---------- Liste ----------
with tab_liste:
    filtre = st.selectbox("Afficher", ["En cours", "À commander", "Commandée", "Reçue", "Annulée", "Toutes"])
    if filtre == "En cours":
        commandes = [c for c in toutes if c["statut"] in ("À commander", "Commandée")]
    elif filtre == "Toutes":
        commandes = toutes
    else:
        commandes = [c for c in toutes if c["statut"] == filtre]
    st.caption(f"{len(commandes)} commande(s)")
    if not commandes:
        st.info("Aucune commande dans cette sélection.")

    articles = db.obtenir_articles()

    for c in commandes:
        lignes = db.obtenir_lignes_commande(c["id"])
        total = db.total_commande(c["id"])
        titre_exp = f"{EMOJI.get(c['statut'], '')} **{c['titre']}**"
        if c.get("fournisseur"):
            titre_exp += f" — {c['fournisseur']}"
        titre_exp += f" — {c['statut']} ({len(lignes)} ligne(s))"
        with st.expander(titre_exp):
            if c.get("notes"):
                st.caption(c["notes"])
            infos = []
            if _date(c.get("date_commande")):
                infos.append(f"Commandée le {_date(c['date_commande']).strftime('%d/%m/%Y')}")
            if _date(c.get("date_livraison_prevue")):
                infos.append(f"Livraison prévue le {_date(c['date_livraison_prevue']).strftime('%d/%m/%Y')}")
            if infos:
                st.caption(" • ".join(infos))

            # --- lignes ---
            if lignes:
                for l in lignes:
                    cols = st.columns([4, 2, 2, 1])
                    ref = f" (réf. {l['reference_fournisseur']})" if l.get("reference_fournisseur") else ""
                    lie = " 🔗" if l.get("article_id") else ""
                    recu = " ✅" if l.get("recu") else ""
                    cols[0].write(f"**{l['designation']}**{ref}{lie}{recu}")
                    cols[1].write(f"{db.formater_quantite(l['quantite'])} {l.get('unite') or ''}")
                    if ADMIN and l.get("prix_unitaire") is not None:
                        cols[2].write(_euros(float(l["quantite"]) * float(l["prix_unitaire"])))
                    if ADMIN and cols[3].button("🗑️", key=f"suppr_lc_{l['id']}", help="Retirer cette ligne"):
                        db.supprimer_ligne_commande(l["id"])
                        st.rerun()
                if total and ADMIN:
                    st.markdown(f"**Total estimé : {_euros(total)}**")
                st.caption("🔗 = lié à un article de l'inventaire (le stock sera mis à jour à la réception).")
            else:
                st.info("Aucune ligne pour l'instant.")

            if ADMIN:
                # --- statut ---
                s1, s2 = st.columns([2, 3])
                nouveau_statut = s1.selectbox("Statut", db.STATUTS_COMMANDE,
                                              index=db.STATUTS_COMMANDE.index(c["statut"]) if c["statut"] in db.STATUTS_COMMANDE else 0,
                                              key=f"statut_{c['id']}")
                d_liv = s2.date_input("Livraison prévue (optionnel)", value=_date(c.get("date_livraison_prevue")),
                                      key=f"liv_{c['id']}")
                b1, b2 = st.columns(2)
                if b1.button("💾 Enregistrer le statut", key=f"maj_{c['id']}", width="stretch"):
                    maj = {"statut": nouveau_statut,
                           "date_livraison_prevue": d_liv.isoformat() if d_liv else None}
                    if nouveau_statut == "Commandée" and not c.get("date_commande"):
                        maj["date_commande"] = date.today().isoformat()
                    db.modifier_commande(c["id"], **maj)
                    st.rerun()
                if c["statut"] != "Reçue" and lignes:
                    if b2.button("📦 Réceptionner et ajouter au stock", key=f"recep_{c['id']}", width="stretch"):
                        non_ajoutees = db.receptionner_commande(c["id"])
                        st.session_state["recep_resultat"] = (c["titre"], non_ajoutees)
                        st.rerun()

                # --- ajouter une ligne ---
                st.markdown("**Ajouter une ligne**")
                with st.form(f"ajout_ligne_{c['id']}", clear_on_submit=True):
                    choix = st.selectbox(
                        "Article de l'inventaire (tape pour chercher)", [None] + articles,
                        format_func=lambda a: "— Nouvel article / hors inventaire —" if a is None else f"{a['nom']} — {a['categorie']}",
                        key=f"lc_art_{c['id']}",
                    )
                    c1, c2 = st.columns([3, 2])
                    designation = c1.text_input("Désignation (si hors inventaire)", key=f"lc_des_{c['id']}")
                    reference = c2.text_input("Référence fournisseur", key=f"lc_ref_{c['id']}")
                    c3, c4, c5 = st.columns(3)
                    quantite = c3.number_input("Quantité", min_value=0.0, value=1.0, step=0.5, format="%g", key=f"lc_q_{c['id']}")
                    unite = c4.text_input("Unité", key=f"lc_u_{c['id']}", help="Vide = unité de l'article choisi")
                    prix = c5.number_input("Prix unitaire (€, 0 = inconnu)", min_value=0.0, value=0.0, step=0.5,
                                           format="%.2f", key=f"lc_p_{c['id']}")
                    ajouter = st.form_submit_button("➕ Ajouter à la commande")
                if ajouter:
                    if choix is None and not designation.strip():
                        st.error("Choisis un article ou saisis une désignation.")
                    else:
                        u = unite.strip() or (choix.get("unite") if choix else None) or "unité(s)"
                        db.ajouter_ligne_commande(
                            c["id"], choix["nom"] if choix else designation.strip(), float(quantite), u,
                            article_id=choix["id"] if choix else None,
                            reference_fournisseur=reference.strip() or None,
                            prix_unitaire=float(prix) if prix > 0 else None,
                        )
                        st.rerun()

                # --- suppression ---
                if st.toggle("🗑️ Supprimer cette commande", key=f"tog_cmd_{c['id']}"):
                    if st.checkbox("Je confirme la suppression", key=f"conf_cmd_{c['id']}"):
                        if st.button("Supprimer définitivement", key=f"suppr_cmd_{c['id']}"):
                            db.supprimer_commande(c["id"])
                            st.rerun()
