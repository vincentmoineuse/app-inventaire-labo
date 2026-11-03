import streamlit as st
from datetime import date, datetime
import database as db
from common import verifier_config

verifier_config()

st.title("🧫 Travaux pratiques (TP)")
st.caption(
    "Prépare tes TP : liste le matériel et les produits nécessaires, vérifie le stock de l'inventaire "
    "et envoie le manquant dans une commande."
)

ETATS = {
    "ok": "✅ En stock",
    "insuffisant": "⚠️ Stock insuffisant",
    "verifier": "❓ Unité différente, à vérifier",
    "hors_inventaire": "🔎 Hors inventaire",
}


def _date(valeur):
    try:
        return datetime.strptime(str(valeur)[:10], "%Y-%m-%d").date() if valeur else None
    except ValueError:
        return None


def _libelle_article(a):
    return f"{a['nom']} — {a['categorie']}"


tab_liste, tab_nouveau = st.tabs(["📚 Liste des TP", "➕ Nouveau TP"])

# ---------- Nouveau TP ----------
with tab_nouveau:
    if st.session_state.get("tp_cree"):
        st.success(f"✅ TP « {st.session_state.pop('tp_cree')} » créé. "
                   "Ajoute-lui maintenant son matériel depuis l'onglet **Liste des TP**.")
    with st.form("nouveau_tp", clear_on_submit=True):
        titre = st.text_input("Titre du TP *", placeholder="ex : Dosage par titrage colorimétrique")
        c1, c2, c3 = st.columns(3)
        discipline = c1.selectbox("Discipline", db.DISCIPLINES_TP)
        niveau = c2.selectbox("Niveau", db.NIVEAUX_TP, index=2)
        date_prevue = c3.date_input("Date prévue", value=None)
        notes = st.text_area("Notes (classe, nombre de groupes, remarques…)")
        envoyer = st.form_submit_button("✅ Créer le TP", width="stretch")
    if envoyer:
        if not titre.strip():
            st.error("Merci de donner un titre au TP.")
        else:
            db.ajouter_tp(titre.strip(), discipline, niveau,
                          date_prevue.isoformat() if date_prevue else None, notes.strip() or None)
            st.session_state["tp_cree"] = titre.strip()
            st.rerun()

# ---------- Liste ----------
with tab_liste:
    f1, f2, f3 = st.columns(3)
    disc = f1.selectbox("Discipline", ["Toutes"] + db.DISCIPLINES_TP, key="f_disc")
    niv = f2.selectbox("Niveau", ["Tous"] + db.NIVEAUX_TP, key="f_niv")
    rech = f3.text_input("Rechercher un TP", key="f_rech")
    tps = db.obtenir_tps(disc, niv, rech or None)
    st.caption(f"{len(tps)} TP")

    articles = db.obtenir_articles()
    commandes_ouvertes = db.obtenir_commandes(["À commander"])

    if not tps:
        st.info("Aucun TP pour le moment. Crée-en un dans l'onglet **Nouveau TP**.")

    for tp in tps:
        d = _date(tp.get("date_prevue"))
        entete = f"**{tp['titre']}** — {tp.get('discipline') or ''} {tp.get('niveau') or ''}"
        if d:
            entete += f" — {d.strftime('%d/%m/%Y')}"
        lignes = db.obtenir_materiel_tp(tp["id"])
        with st.expander(f"{entete} ({len(lignes)} ligne(s))"):
            if tp.get("notes"):
                st.caption(tp["notes"])

            # --- matériel du TP ---
            manquants = []
            if lignes:
                for l in lignes:
                    etat, stock, manque = db.disponibilite_ligne(l)
                    article = db.obtenir_article(l["article_id"]) if l.get("article_id") else None
                    nom = article["nom"] if article else (l.get("libelle") or "?")
                    cols = st.columns([4, 2, 3, 1])
                    cols[0].write(f"**{nom}**")
                    cols[1].write(f"{db.formater_quantite(l['quantite'])} {l.get('unite') or ''}")
                    detail = ETATS[etat]
                    if etat in ("ok", "insuffisant") and stock is not None:
                        detail += f" ({db.formater_quantite(stock)} dispo)"
                    cols[2].write(detail)
                    if cols[3].button("🗑️", key=f"suppr_l_{l['id']}", help="Retirer cette ligne"):
                        db.supprimer_materiel_tp(l["id"])
                        st.rerun()
                    if etat == "insuffisant":
                        manquants.append((article, nom, manque, l.get("unite")))
                    elif etat == "hors_inventaire":
                        manquants.append((None, nom, manque, l.get("unite")))
            else:
                st.info("Aucun matériel pour l'instant.")

            # --- commander le manquant ---
            if manquants:
                st.warning(f"{len(manquants)} ligne(s) à compléter (stock insuffisant ou hors inventaire).")
                choix_cmd = st.selectbox(
                    "Envoyer le manquant dans…",
                    [None] + commandes_ouvertes,
                    format_func=lambda c: "➕ Nouvelle commande" if c is None else f"🛒 {c['titre']}",
                    key=f"cmd_cible_{tp['id']}",
                )
                if st.button("🛒 Commander le manquant", key=f"cmd_btn_{tp['id']}"):
                    cmd_id = choix_cmd["id"] if choix_cmd else db.creer_commande(f"Matériel TP : {tp['titre']}")
                    for article, nom, manque, unite in manquants:
                        db.ajouter_ligne_commande(cmd_id, nom, manque, unite,
                                                  article_id=article["id"] if article else None)
                    st.success("Manquant ajouté à la commande (voir la rubrique **Commandes**).")
                    st.rerun()

            # --- ajouter du matériel ---
            st.markdown("**Ajouter du matériel ou un produit**")
            with st.form(f"ajout_mat_{tp['id']}", clear_on_submit=True):
                choix = st.selectbox(
                    "Article de l'inventaire (tape pour chercher)", [None] + articles,
                    format_func=lambda a: "— Hors inventaire (saisie libre) —" if a is None else _libelle_article(a),
                    key=f"mat_art_{tp['id']}",
                )
                c1, c2, c3 = st.columns([3, 1, 1])
                libelle = c1.text_input("Désignation (si hors inventaire)", key=f"mat_lib_{tp['id']}")
                quantite = c2.number_input("Quantité", min_value=0.0, value=1.0, step=0.5, format="%g",
                                           key=f"mat_q_{tp['id']}")
                unite = c3.text_input("Unité", key=f"mat_u_{tp['id']}",
                                      help="Vide = unité de l'article choisi")
                ajouter = st.form_submit_button("➕ Ajouter au TP")
            if ajouter:
                if choix is None and not libelle.strip():
                    st.error("Choisis un article ou saisis une désignation.")
                else:
                    u = unite.strip() or (choix.get("unite") if choix else None) or "unité(s)"
                    db.ajouter_materiel_tp(tp["id"], float(quantite), u,
                                           article_id=choix["id"] if choix else None,
                                           libelle=None if choix else libelle.strip())
                    st.rerun()

            # --- modifier / supprimer le TP ---
            if st.toggle("✏️ Modifier ou supprimer ce TP", key=f"tog_tp_{tp['id']}"):
                with st.form(f"edit_tp_{tp['id']}"):
                    t = st.text_input("Titre", value=tp["titre"])
                    c1, c2, c3 = st.columns(3)
                    disc_opts = db.DISCIPLINES_TP + ([tp["discipline"]] if tp.get("discipline") not in db.DISCIPLINES_TP and tp.get("discipline") else [])
                    niv_opts = db.NIVEAUX_TP + ([tp["niveau"]] if tp.get("niveau") not in db.NIVEAUX_TP and tp.get("niveau") else [])
                    di = c1.selectbox("Discipline", disc_opts,
                                      index=disc_opts.index(tp["discipline"]) if tp.get("discipline") in disc_opts else 0)
                    ni = c2.selectbox("Niveau", niv_opts,
                                      index=niv_opts.index(tp["niveau"]) if tp.get("niveau") in niv_opts else 0)
                    da = c3.date_input("Date prévue", value=d)
                    no = st.text_area("Notes", value=tp.get("notes") or "")
                    enreg = st.form_submit_button("💾 Enregistrer")
                if enreg:
                    db.modifier_tp(tp["id"], titre=t.strip() or tp["titre"], discipline=di, niveau=ni,
                                   date_prevue=da.isoformat() if da else None, notes=no.strip() or None)
                    st.rerun()
                if st.checkbox("Je confirme vouloir supprimer ce TP", key=f"conf_tp_{tp['id']}"):
                    if st.button("🗑️ Supprimer ce TP", key=f"suppr_tp_{tp['id']}"):
                        db.supprimer_tp(tp["id"])
                        st.rerun()
