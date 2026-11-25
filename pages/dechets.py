import streamlit as st
import pandas as pd
from datetime import date, timedelta
import database as db
from pictos import afficher_pictogrammes
from common import verifier_config, exiger_admin

verifier_config()
exiger_admin()

st.title("♻️ Évacuation des déchets")
st.caption("Un ticket par enlèvement du prestataire : on y ajoute les déchets au fur et à mesure "
           "(bidons de collecte, verrerie cassée, emballages souillés, produits périmés…), puis on le clôture "
           "le jour de l'enlèvement.")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def _fr(d):
    d = db._en_date(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def _libelle_ticket(e):
    icone = "🟡" if e["statut"] == "Ouvert" else "✅"
    quand = f"enlevé le {_fr(e.get('date_enlevement'))}" if e["statut"] == "Enlevé" else f"ouvert le {_fr(e['date_ouverture'])}"
    return f"{icone} {e['intitule']} — {quand} — {e['nb_entrees']} entrée(s)"


try:
    tickets = db.obtenir_enlevements()
except db.TablesDechetsManquantes:
    st.error("Les tables `dechets_enlevements` et `dechets_lignes` n'existent pas encore dans Supabase. "
             "Exécute le script SQL de la section **6 quater** de **SETUP.md** dans le *SQL Editor* de Supabase, "
             "puis recharge cette page.")
    st.stop()

message = st.session_state.pop("dechets_message", None)
if message:
    (st.warning if message[0] == "warning" else st.success)(message[1])

ouverts = [e for e in tickets if e["statut"] == "Ouvert"]

# ---------- Nouveau ticket ----------
with st.container(border=True):
    st.subheader("🎫 Nouveau ticket d'enlèvement")
    if ouverts:
        st.caption(f"{len(ouverts)} ticket(s) déjà ouvert(s). N'en ouvre un autre que si deux enlèvements "
                   "distincts sont prévus (par exemple deux prestataires).")
    if not ouverts or st.toggle("Ouvrir quand même un autre ticket", key="dec_autre_ticket"):
        with st.form("f_nouveau_ticket", clear_on_submit=True):
            auj = date.today()
            intitule = st.text_input("Intitulé *", value=f"Enlèvement {MOIS[auj.month - 1]} {auj.year}")
            c1, c2 = st.columns(2)
            prevue_connue = c1.checkbox("La date d'enlèvement est déjà connue")
            prevue = c1.date_input("Date d'enlèvement prévue", value=auj + timedelta(days=30), min_value=auj,
                                   format="DD/MM/YYYY")
            prestataire = c2.text_input("Prestataire (facultatif)")
            notes = st.text_input("Notes (n° de commande, contact, consignes de conditionnement…)")
            if st.form_submit_button("🎫 Ouvrir le ticket", type="primary"):
                if not intitule.strip():
                    st.error("L'intitulé est obligatoire.")
                else:
                    nouvel_id = db.creer_enlevement(intitule.strip(), date_prevue=prevue if prevue_connue else None,
                                                    prestataire=prestataire.strip() or None, notes=notes.strip() or None)
                    st.session_state["dec_ticket"] = nouvel_id
                    st.session_state["dechets_message"] = ("success", f"Ticket « {intitule.strip()} » ouvert. "
                                                           "Ajoute les déchets au fil de l'eau ci-dessous.")
                    st.rerun()

if not tickets:
    st.info("Aucun ticket pour le moment. Ouvre le premier ci-dessus.")
    st.stop()

# ---------- Choix du ticket ----------
par_id = {e["id"]: e for e in tickets}
ids = list(par_id)
defaut = st.session_state.get("dec_ticket")
choix = st.selectbox("Ticket affiché", ids, index=ids.index(defaut) if defaut in ids else 0,
                     format_func=lambda i: _libelle_ticket(par_id[i]))
st.session_state["dec_ticket"] = choix
ticket = par_id[choix]
OUVERT = ticket["statut"] == "Ouvert"
lignes = db.obtenir_lignes_dechets(ticket["id"])

# ---------- En-tête du ticket ----------
if OUVERT:
    j = ticket["jours_avant"]
    if j is None:
        st.info("📅 Date d'enlèvement pas encore fixée (à renseigner dans l'onglet ⚙️ Ticket dès qu'elle est connue).")
    elif j < 0:
        st.warning(f"📅 L'enlèvement était prévu le {_fr(ticket['date_prevue'])} (il y a {-j} j). "
                   "S'il a eu lieu, clôture le ticket dans l'onglet ⚙️ Ticket ; sinon, mets à jour la date.")
    else:
        st.info(f"📅 Enlèvement prévu le **{_fr(ticket['date_prevue'])}** (dans {j} j)"
                + (f" — prestataire : {ticket['prestataire']}" if ticket.get("prestataire") else ""))
else:
    st.success(f"✅ Déchets enlevés le **{_fr(ticket.get('date_enlevement'))}**"
               + (f" par {ticket['prestataire']}" if ticket.get("prestataire") else "")
               + (f" — BSDD n° {ticket['numero_bsd']}" if ticket.get("numero_bsd") else "")
               + ". Ticket en lecture seule (il peut être rouvert dans l'onglet ⚙️ Ticket).")

totaux = db.totaux_dechets(lignes)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Entrées", len(lignes))
m2.metric("Contenants", sum(int(l.get("nb_contenants") or 0) for l in lignes))
m3.metric("Liquides", f"{db.formater_quantite(totaux.get('L', 0))} L")
m4.metric("Solides", f"{db.formater_quantite(totaux.get('kg', 0))} kg")

# ---------- Contenu du ticket ----------
if lignes:
    df = pd.DataFrame([{
        "N°": i,
        "Ajouté le": _fr(l.get("date_ajout")),
        "Catégorie": l["categorie"],
        "Désignation / composition": l["designation"],
        "Code déchet": l.get("code_dechet") or "",
        "Contenant": f"{int(l.get('nb_contenants') or 1)} × {l.get('contenant') or '?'}",
        "Quantité": (f"{db.formater_quantite(l['quantite'])} {l.get('unite') or ''}"
                     if l.get("quantite") not in (None, "") else ""),
        "État": l.get("etat_physique") or "",
        "Dangers": ", ".join(p.strip()[:5] for p in str(l.get("pictogrammes") or "").split(",") if p.strip()),
        "Origine": l.get("origine") or "",
        "Remarques": l.get("notes") or "",
    } for i, l in enumerate(lignes, 1)])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Désignation / composition": st.column_config.TextColumn(width="large"),
                                "N°": st.column_config.NumberColumn(width="small")})

    if st.toggle("Récapitulatif par catégorie", key="dec_recap"):
        par_cat = {}
        for l in lignes:
            par_cat.setdefault((l["categorie"], l.get("code_dechet") or "à préciser"), []).append(l)
        st.dataframe(pd.DataFrame([{
            "Catégorie": cat, "Code déchet": code, "Entrées": len(ls),
            "Contenants": sum(int(l.get("nb_contenants") or 0) for l in ls),
            "Quantité totale": db.texte_totaux(db.totaux_dechets(ls)),
        } for (cat, code), ls in sorted(par_cat.items())]), hide_index=True, width="stretch")

    c1, c2 = st.columns(2)
    if c1.button("📄 Préparer le bordereau récapitulatif (PDF)", key=f"dec_pdf_{ticket['id']}"):
        from dechets_pdf import generer_pdf_enlevement
        st.session_state["dec_pdf"] = (ticket["id"], generer_pdf_enlevement(ticket, lignes))
    pdf = st.session_state.get("dec_pdf")
    if pdf and pdf[0] == ticket["id"]:
        c1.download_button("⬇️ Télécharger le PDF", pdf[1], f"enlevement_dechets_{db.nom_fichier_sur(ticket['intitule'], 'pdf')}",
                           "application/pdf", type="primary")
    c2.download_button("⬇️ Télécharger la liste (CSV)", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       f"dechets_{db.nom_fichier_sur(ticket['intitule'], 'csv')}", "text/csv")
else:
    st.info("Ce ticket ne contient encore aucune entrée." if OUVERT else "Ce ticket ne contient aucune entrée.")

st.divider()

# ---------- Actions ----------
if OUVERT:
    onglet_ajout, onglet_modif, onglet_ticket = st.tabs(["➕ Ajouter un déchet", "✏️ Modifier / supprimer", "⚙️ Ticket"])
else:
    (onglet_ticket,) = st.tabs(["⚙️ Ticket"])
    onglet_ajout = onglet_modif = None


def _champs_ligne(prefixe, categorie, l=None, article=None):
    """Champs communs à l'ajout et à la modification d'une entrée (la catégorie est choisie hors du
    formulaire, pour que le code déchet et l'état proposés suivent la catégorie). Renvoie un dict."""
    l = l or {}
    code_def, etat_def, pictos_def = db.CATEGORIES_DECHET.get(categorie, ("", "Solide", ""))
    meme_cat = bool(l) and l.get("categorie") == categorie
    prefixe = f"{prefixe}_{list(db.CATEGORIES_DECHET).index(categorie)}"

    designation_def = l.get("designation") or (article["nom"] + (f" (CAS {article['numero_cas']})" if article and article.get("numero_cas") else "") if article else "")
    designation = st.text_input("Désignation / composition *", value=designation_def, key=f"{prefixe}_des",
                                placeholder="ex. : solutions de sulfate de cuivre et de nitrate de plomb (TP 1re)")
    c1, c2, c3 = st.columns(3)
    code = c1.text_input("Code déchet", value=(l.get("code_dechet") or "") if meme_cat else code_def, key=f"{prefixe}_code",
                         help="Code indicatif proposé selon la catégorie ; c'est celui du prestataire sur le BSDD qui fait foi.")
    etats = db.ETATS_DECHET
    etat_val = (l.get("etat_physique") if meme_cat else None) or (("Liquide" if (article.get("unite") in ("L", "mL")) else "Solide") if article else etat_def)
    etat = c2.selectbox("État physique", etats, index=etats.index(etat_val) if etat_val in etats else 1, key=f"{prefixe}_etat")
    d_ajout = c3.date_input("Date d'ajout", value=db._en_date(l.get("date_ajout")) or date.today(), max_value=date.today(),
                            format="DD/MM/YYYY", key=f"{prefixe}_date")

    c4, c5, c6, c7 = st.columns([2, 1, 1, 1])
    conts = db.CONTENANTS_DECHET
    cont_val = l.get("contenant") or ("Flacon d'origine" if article else ("Bidon 10 L" if etat_def == "Liquide" else "Carton"))
    contenant = c4.selectbox("Contenant", conts, index=conts.index(cont_val) if cont_val in conts else len(conts) - 1,
                             key=f"{prefixe}_cont")
    nb = c5.number_input("Nombre", min_value=1, max_value=999, step=1, value=int(l.get("nb_contenants") or 1),
                         key=f"{prefixe}_nb")
    q_val = l.get("quantite") if l else (article.get("quantite") if article else None)
    quantite = c6.number_input("Quantité", min_value=0.0, step=0.1, format="%.3f",
                               value=float(q_val) if q_val not in (None, "") else 0.0, key=f"{prefixe}_q",
                               help="Volume ou masse de déchet (0 = non renseigné).")
    unites = db.UNITES_DECHET
    u_val = l.get("unite") or ((article.get("unite") if article else None) or ("L" if etat_def == "Liquide" else "kg"))
    unite = c7.selectbox("Unité", unites, index=unites.index(u_val) if u_val in unites else 0, key=f"{prefixe}_u")

    p_val = l.get("pictogrammes") if l else ((article.get("pictogrammes") if article else None) or pictos_def)
    pictos_choisis = [p for p in db.PICTOGRAMMES_GHS if p[:5] in str(p_val or "")]
    pictos = st.multiselect("Pictogrammes de danger", db.PICTOGRAMMES_GHS, default=pictos_choisis, key=f"{prefixe}_pic")
    c8, c9 = st.columns(2)
    origine = c8.text_input("Origine (salle, TP, classe…)", value=l.get("origine") or
                            ((article.get("salle") or "") if article else ""), key=f"{prefixe}_orig")
    notes = c9.text_input("Remarques", value=l.get("notes") or "", key=f"{prefixe}_notes")
    return {"categorie": categorie, "designation": designation.strip(), "code_dechet": code.strip() or None,
            "etat_physique": etat, "date_ajout": d_ajout, "contenant": contenant, "nb_contenants": int(nb),
            "quantite": float(quantite) if quantite else None, "unite": unite if quantite else None,
            "pictogrammes": ", ".join(pictos) or None, "origine": origine.strip() or None, "notes": notes.strip() or None}


def _choix_categorie(prefixe, valeur=None):
    cats = list(db.CATEGORIES_DECHET)
    cat = st.selectbox("Catégorie de déchet", cats, key=f"{prefixe}_cat",
                       index=cats.index(valeur) if valeur in cats else 0)
    code, etat, _ = db.CATEGORIES_DECHET[cat]
    if cat == "Verrerie cassée souillée":
        st.caption("Verrerie **souillée** par des produits dangereux → filière déchets dangereux (code à fixer avec le "
                   "prestataire). Verrerie **propre** (rincée, non contaminée) : déchet non dangereux, pas besoin du prestataire.")
    elif code:
        st.caption(f"Code indicatif : **{code}** — état par défaut : {etat.lower()}.")
    return cat


# ----- Ajouter -----
if onglet_ajout is not None:
    with onglet_ajout:
        source = st.radio("Origine du déchet", ["Saisie libre (bidon de collecte, verrerie, emballage…)",
                                                "Produit de l'inventaire (périmé ou inutilisable)"],
                          key="dec_source", horizontal=True)
        article = None
        prefixe = "aj"
        if source.startswith("Produit"):
            produits = db.obtenir_articles(categorie=db.CATEGORIE_CHIMIE)
            recherche = st.text_input("🔎 Rechercher un produit", key="dec_rech_art")
            if recherche:
                produits = [a for a in produits if db._sans_accents(recherche) in db._sans_accents(a.get("nom"))]
            if not produits:
                st.info("Aucun produit chimique actif ne correspond.")
            else:
                par_art = {a["id"]: a for a in produits}
                art_id = st.selectbox("Produit", list(par_art), format_func=lambda i: (lambda a: (
                    f"{a['nom']} — {db.formater_quantite(a.get('quantite'))} {a.get('unite') or ''} — "
                    f"{a.get('salle') or '?'} / {a.get('armoire') or '?'}"
                    + (f" — périme le {_fr(a['date_peremption'])}" if a.get("date_peremption") else "")))(par_art[i]))
                article = par_art[art_id]
                if article.get("pictogrammes"):
                    afficher_pictogrammes(article["pictogrammes"], taille=36)
                prefixe = f"aj_art{article['id']}"
        if source.startswith("Saisie") or article:
            categorie = _choix_categorie(prefixe, "Produits périmés ou inutilisables" if article else None)
            with st.form(f"f_ajout_{prefixe}", clear_on_submit=True):
                champs = _champs_ligne(prefixe, categorie, article=article)
                retirer = False
                if article:
                    retirer = st.checkbox("Retirer ce produit de l'inventaire (il ne figurera plus dans la consultation)",
                                          value=True)
                if st.form_submit_button("➕ Ajouter au ticket", type="primary"):
                    if not champs["designation"]:
                        st.error("La désignation est obligatoire.")
                    else:
                        cat = champs.pop("categorie")
                        des = champs.pop("designation")
                        if article:
                            champs["article_id"] = article["id"]
                        db.ajouter_ligne_dechet(ticket["id"], cat, des, **champs)
                        texte = f"« {des} » ajouté au ticket."
                        if article and retirer:
                            note = f"Évacué en déchets (ticket « {ticket['intitule']} ») le {date.today():%d/%m/%Y}."
                            ancien = (article.get("notes") or "").strip()
                            db.modifier_article(article["id"], actif=False,
                                                notes=f"{ancien}\n{note}".strip() if ancien else note)
                            texte += " Le produit a été retiré de l'inventaire."
                        st.session_state["dechets_message"] = ("success", texte)
                        st.rerun()

# ----- Modifier / supprimer -----
if onglet_modif is not None:
    with onglet_modif:
        if not lignes:
            st.info("Rien à modifier pour le moment.")
        else:
            numeros = {x["id"]: n for n, x in enumerate(lignes, 1)}
            par_ligne = {x["id"]: x for x in lignes}
            l = par_ligne[st.selectbox("Entrée", list(par_ligne), format_func=lambda i: (
                f"{numeros[i]}. {par_ligne[i]['designation']} ({par_ligne[i]['categorie']})"))]
            prefixe = f"mod{l['id']}"
            categorie = _choix_categorie(prefixe, l["categorie"])
            with st.form(f"f_modif_{l['id']}"):
                champs = _champs_ligne(prefixe, categorie, l=l)
                if st.form_submit_button("💾 Enregistrer les modifications", type="primary"):
                    if not champs["designation"]:
                        st.error("La désignation est obligatoire.")
                    else:
                        db.modifier_ligne_dechet(l["id"], **champs)
                        st.session_state["dechets_message"] = ("success", f"Entrée « {champs['designation']} » mise à jour.")
                        st.rerun()
            if st.toggle("🗑️ Supprimer cette entrée", key=f"dec_tog_sup_{l['id']}"):
                art = db.obtenir_article(l["article_id"]) if l.get("article_id") else None
                remettre = False
                if art and not art.get("actif", True):
                    remettre = st.checkbox(f"Remettre « {art['nom']} » dans l'inventaire", value=True,
                                           key=f"dec_remettre_{l['id']}")
                if st.button("Supprimer définitivement", key=f"dec_sup_{l['id']}"):
                    db.supprimer_ligne_dechet(l["id"])
                    if remettre:
                        db.modifier_article(art["id"], actif=True)
                    st.session_state["dechets_message"] = ("success", f"Entrée « {l['designation']} » supprimée.")
                    st.rerun()

# ----- Ticket : date, prestataire, clôture -----
with onglet_ticket:
    if OUVERT:
        with st.form(f"f_ticket_{ticket['id']}"):
            intitule = st.text_input("Intitulé", value=ticket["intitule"])
            c1, c2 = st.columns(2)
            prevue_actuelle = db._en_date(ticket.get("date_prevue"))
            fixer = c1.checkbox("Date d'enlèvement fixée", value=prevue_actuelle is not None)
            prevue = c1.date_input("Date d'enlèvement prévue", value=prevue_actuelle or date.today() + timedelta(days=30),
                                   format="DD/MM/YYYY")
            prestataire = c2.text_input("Prestataire", value=ticket.get("prestataire") or "")
            notes = st.text_input("Notes", value=ticket.get("notes") or "")
            if st.form_submit_button("💾 Enregistrer"):
                db.modifier_enlevement(ticket["id"], intitule=intitule.strip() or ticket["intitule"],
                                       date_prevue=prevue if fixer else None,
                                       prestataire=prestataire.strip() or None, notes=notes.strip() or None)
                st.session_state["dechets_message"] = ("success", "Ticket mis à jour.")
                st.rerun()

        st.markdown("##### ✅ Clôturer : les déchets ont été enlevés")
        with st.form(f"f_cloture_{ticket['id']}"):
            c1, c2, c3 = st.columns(3)
            d_enl = c1.date_input("Date de l'enlèvement", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
            presta = c2.text_input("Prestataire", value=ticket.get("prestataire") or "")
            bsd = c3.text_input("N° de BSDD (Trackdéchets)", value=ticket.get("numero_bsd") or "",
                                help="Numéro du bordereau de suivi des déchets dangereux, visible sur Trackdéchets.")
            if st.form_submit_button("✅ Clôturer le ticket", type="primary"):
                db.cloturer_enlevement(ticket["id"], d_enl, presta.strip(), bsd.strip())
                st.session_state["dechets_message"] = ("success", f"Ticket « {ticket['intitule']} » clôturé "
                                                       f"(enlèvement du {d_enl:%d/%m/%Y}).")
                st.rerun()
    else:
        with st.form(f"f_apres_{ticket['id']}"):
            st.caption("Compléter après coup (le n° de BSDD arrive parfois quelques jours après l'enlèvement).")
            c1, c2 = st.columns(2)
            presta = c1.text_input("Prestataire", value=ticket.get("prestataire") or "")
            bsd = c2.text_input("N° de BSDD (Trackdéchets)", value=ticket.get("numero_bsd") or "")
            if st.form_submit_button("💾 Enregistrer"):
                db.modifier_enlevement(ticket["id"], prestataire=presta.strip() or None, numero_bsd=bsd.strip() or None)
                st.session_state["dechets_message"] = ("success", "Ticket mis à jour.")
                st.rerun()
        if st.button("↩️ Rouvrir ce ticket (clôture faite par erreur)", key=f"dec_rouvrir_{ticket['id']}"):
            db.rouvrir_enlevement(ticket["id"])
            st.session_state["dechets_message"] = ("success", "Ticket rouvert.")
            st.rerun()

    if st.toggle("🗑️ Supprimer ce ticket", key=f"dec_tog_sup_ticket_{ticket['id']}"):
        st.caption("Le ticket disparaît de la liste, mais ses données restent dans la base (suppression douce).")
        if st.checkbox("Je confirme la suppression", key=f"dec_conf_sup_ticket_{ticket['id']}"):
            if st.button("Supprimer le ticket", key=f"dec_sup_ticket_{ticket['id']}"):
                db.supprimer_enlevement(ticket["id"])
                st.session_state.pop("dec_ticket", None)
                st.session_state["dechets_message"] = ("success", f"Ticket « {ticket['intitule']} » supprimé.")
                st.rerun()

st.divider()

# ---------- Registre (tous les tickets clôturés) ----------
st.subheader("📒 Registre des déchets évacués")
if st.toggle("Afficher le registre (tous les enlèvements clôturés)", key="dec_registre"):
    noms = {e["id"]: e for e in tickets}
    clos = [e for e in tickets if e["statut"] == "Enlevé"]
    toutes = [l for l in db.obtenir_lignes_dechets() if l["enlevement_id"] in noms
              and noms[l["enlevement_id"]]["statut"] == "Enlevé"]
    if not toutes:
        st.info("Aucun enlèvement clôturé pour le moment.")
    else:
        dfr = pd.DataFrame([{
            "Date d'expédition": _fr(noms[l["enlevement_id"]].get("date_enlevement")),
            "Ticket": noms[l["enlevement_id"]]["intitule"],
            "Code déchet": l.get("code_dechet") or "",
            "Dénomination": f"{l['categorie']} — {l['designation']}",
            "Quantité": (f"{db.formater_quantite(l['quantite'])} {l.get('unite') or ''}"
                         if l.get("quantite") not in (None, "") else ""),
            "Contenants": f"{int(l.get('nb_contenants') or 1)} × {l.get('contenant') or '?'}",
            "Prestataire": noms[l["enlevement_id"]].get("prestataire") or "",
            "N° BSDD": noms[l["enlevement_id"]].get("numero_bsd") or "",
        } for l in toutes])
        st.caption(f"{len(clos)} enlèvement(s) clôturé(s), {len(toutes)} entrée(s).")
        st.dataframe(dfr, hide_index=True, width="stretch")
        st.download_button("⬇️ Exporter le registre (CSV)", dfr.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           f"registre_dechets_{date.today():%Y-%m-%d}.csv", "text/csv")

with st.expander("📘 Rappels réglementaires"):
    st.markdown("""
- En collège et lycée, les déchets chimiques sont en général des **déchets dangereux diffus (DDD)**,
  anciennement « DTQD » : petites quantités, mais filière de déchets dangereux obligatoire.
- **Trackdéchets** : depuis le **1er janvier 2022** (décret n° 2021-321), le bordereau de suivi des déchets
  dangereux (**BSDD**) est dématérialisé. Le prestataire le crée ; l'établissement (producteur) le signe sur la
  plateforme. Note son numéro dans le ticket à la clôture.
- **Registre chronologique des déchets sortants** (art. R541-43 du code de l'environnement, arrêté du
  31 mai 2021) : date d'expédition, code déchet, dénomination, quantité, prestataire, n° de bordereau…
  À **conserver au moins 3 ans**. L'export CSV du registre ci-dessus en reprend l'essentiel.
- **Codes déchets** (liste européenne, art. R541-8) : l'astérisque marque un déchet dangereux. Codes indicatifs
  proposés : 16 05 06* produits chimiques de laboratoire, 14 06 02* solvants halogénés, 14 06 03* autres solvants,
  15 01 10* emballages souillés, 15 02 02* matériaux filtrants souillés. Le code retenu par le prestataire fait foi.
- **Ne jamais mélanger** dans un même bidon des familles incompatibles (acides / bases, oxydants / solvants…),
  et ne pas mélanger solvants **halogénés** et **non halogénés** (filières de traitement différentes).
""")
