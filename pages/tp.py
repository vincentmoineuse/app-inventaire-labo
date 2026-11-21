import json

import streamlit as st

import database as db
import fiche_tp
from common import verifier_config, est_admin

verifier_config()
ADMIN = est_admin()

st.title("🧫 Travaux pratiques (TP)")
st.caption(
    "Prépare tes TP : matériel par poste, solutions, sécurité, fiche de préparation normalisée en PDF, "
    "vérification du stock de l'inventaire et envoi du manquant dans une commande. "
    "Les TP sont repérés par leur titre et classés par thème."
)

ETATS = {
    "ok": "✅ En stock",
    "insuffisant": "⚠️ Stock insuffisant",
    "verifier": "❓ Unité différente, à vérifier",
    "hors_inventaire": "🔎 Hors inventaire",
}


def _libelle_article(a):
    return f"{a['nom']} — {a['categorie']}"


def _options(liste, valeur):
    """Liste de choix complétée par la valeur actuelle si elle n'y figure pas."""
    return liste + ([valeur] if valeur and valeur not in liste else [])


def _index(liste, valeur, defaut=0):
    return liste.index(valeur) if valeur in liste else defaut


@st.cache_data(max_entries=20, show_spinner=False)
def _pdf(fiche_texte):
    """PDF fabriqué en mémoire sur le serveur Streamlit (aucun stockage, aucun trafic Supabase)."""
    return fiche_tp.generer_pdf(json.loads(fiche_texte))


def _champs_tp(prefixe, tp=None):
    """Champs communs aux formulaires de création et de modification (contenu durable du TP uniquement)."""
    tp = tp or {}
    titre = st.text_input("Titre du TP *", value=tp.get("titre") or "", key=f"{prefixe}_titre",
                          placeholder="ex : Titrage pH-métrique de l'acide chlorhydrique par la soude")
    c1, c2, c3 = st.columns(3)
    disc_opts = _options(db.DISCIPLINES_TP, tp.get("discipline"))
    theme_opts = _options(db.THEMES_TP, tp.get("theme"))
    niv_opts = _options(db.NIVEAUX_TP, tp.get("niveau"))
    discipline = c1.selectbox("Discipline", disc_opts, index=_index(disc_opts, tp.get("discipline")),
                              key=f"{prefixe}_disc")
    theme = c2.selectbox("Thème", theme_opts, index=_index(theme_opts, tp.get("theme")), key=f"{prefixe}_theme")
    niveau = c3.selectbox("Niveau", niv_opts, index=_index(niv_opts, tp.get("niveau"), 3), key=f"{prefixe}_niv")
    c1, c2, c3 = st.columns(3)
    postes = c1.number_input("Nombre de postes", min_value=1, max_value=60, step=1,
                             value=int(tp.get("postes") or db.POSTES_DEFAUT), key=f"{prefixe}_postes")
    duree = c2.text_input("Durée", value=tp.get("duree") or "", key=f"{prefixe}_duree", placeholder="ex : 2 h")
    enseignant = c3.text_input("Enseignant(e)", value=tp.get("enseignant") or "", key=f"{prefixe}_ens")
    return {"titre": titre.strip(), "discipline": discipline, "theme": theme, "niveau": niveau,
            "postes": int(postes), "duree": duree.strip() or None, "enseignant": enseignant.strip() or None}


onglets = ["📚 Liste des TP"] + (["➕ Nouveau TP", "📥 Importer une fiche"] if ADMIN else [])
tabs = st.tabs(onglets)
tab_liste = tabs[0]

# ---------- Nouveau TP (saisie manuelle) ----------
if ADMIN:
    with tabs[1]:
        if st.session_state.get("tp_cree"):
            st.success(f"✅ TP « {st.session_state.pop('tp_cree')} » créé. "
                       "Ajoute-lui maintenant son matériel depuis l'onglet **Liste des TP**.")
        st.caption("Pour une fiche complète (solutions, préparations, sécurité), le plus simple est de la faire "
                   "préparer par Claude puis de l'importer dans l'onglet **Importer une fiche**.")
        with st.form("nouveau_tp", clear_on_submit=True):
            champs = _champs_tp("new")
            notes = st.text_area("Notes internes")
            envoyer = st.form_submit_button("✅ Créer le TP", width="stretch")
        if envoyer:
            if not champs["titre"]:
                st.error("Merci de donner un titre au TP.")
            elif db.trouver_tp_par_titre(champs["titre"]):
                st.error(f"Un TP s'appelle déjà « {champs['titre']} ». Choisis un autre titre.")
            else:
                titre = champs.pop("titre")
                db.ajouter_tp(titre, notes=notes.strip() or None, **champs)
                st.session_state["tp_cree"] = titre
                st.rerun()

# ---------- Importer une fiche (JSON du skill Claude) ----------
if ADMIN:
    with tabs[2]:
        if st.session_state.get("tp_importe"):
            st.success(st.session_state.pop("tp_importe"))
        st.markdown(
            "Importe le fichier **JSON** d'une fiche préparée par Claude (skill « fiche-tp-labo »). "
            "Le matériel est relié automatiquement aux articles de l'inventaire qui portent **exactement** "
            "le même nom (accents et majuscules ignorés) ; les autres lignes restent « hors inventaire » "
            "et peuvent être reliées ensuite."
        )
        fichier = st.file_uploader("Fichier JSON de la fiche", type=["json"], key="imp_fichier")
        texte = st.text_area("… ou colle ici le contenu JSON", height=120, key="imp_texte")
        brut = fichier.getvalue().decode("utf-8-sig") if fichier else texte.strip()
        if brut:
            try:
                fiche = json.loads(brut)
                champs, fiche_json, lignes_imp = fiche_tp.preparer_import(fiche, db.obtenir_articles())
            except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
                st.error(f"Ce contenu n'est pas une fiche valide : {e}")
            else:
                st.markdown(f"**{champs['titre']}** — {champs.get('theme') or 'thème non précisé'} · "
                            f"{champs.get('niveau') or ''} · v{champs['version']} · {champs['postes']} poste(s)")
                lies = sum(1 for l in lignes_imp if l["article"])
                st.caption(f"{len(lignes_imp)} ligne(s) de matériel, dont {lies} reliée(s) à l'inventaire ; "
                           f"{len(fiche_json.get('solutions') or [])} solution(s).")
                st.dataframe(
                    [{"Emplacement": db.EMPLACEMENTS_TP[l["emplacement"]], "Désignation": l["designation"],
                      "Qté": db.formater_quantite(l["quantite"]),
                      "Inventaire": f"✅ {l['article']['nom']}" if l["article"] else "🔎 hors inventaire"}
                     for l in lignes_imp],
                    hide_index=True, width="stretch")
                existant = db.trouver_tp_par_titre(champs["titre"])
                if existant:
                    st.warning(f"Un TP porte déjà ce titre (v{existant.get('version') or 1}). L'import "
                               "**remplacera** ce TP et tout son matériel par le contenu de la fiche.")
                if st.button("🔄 Mettre à jour le TP existant" if existant else "📥 Importer la fiche",
                             type="primary", key="imp_go"):
                    db.importer_fiche_tp(champs, fiche_json, lignes_imp,
                                         remplacer_id=existant["id"] if existant else None)
                    st.session_state["tp_importe"] = (f"✅ Fiche « {champs['titre']} » "
                                                      f"{'mise à jour' if existant else 'importée'}. "
                                                      "Retrouve-la dans l'onglet **Liste des TP**.")
                    for cle in ("imp_texte", "imp_fichier"):
                        st.session_state.pop(cle, None)
                    st.rerun()

# ---------- Liste ----------
with tab_liste:
    f1, f2, f3 = st.columns(3)
    theme_f = f1.selectbox("Thème", ["Tous"] + db.THEMES_TP, key="f_theme")
    niv = f2.selectbox("Niveau", ["Tous"] + db.NIVEAUX_TP, key="f_niv")
    rech = f3.text_input("Rechercher dans les titres", key="f_rech")
    tps = db.obtenir_tps(theme_f, niv, rech or None)
    st.caption(f"{len(tps)} TP")

    articles = db.obtenir_articles()
    commandes_ouvertes = db.obtenir_commandes(["À commander"]) if ADMIN else []
    fiches_ouvertes = st.session_state.setdefault("tp_fiches_ouvertes", set())

    if not tps:
        st.info("Aucun TP pour le moment. Importe une fiche ou crée un TP dans les autres onglets.")

    for tp in tps:
        postes = int(tp.get("postes") or db.POSTES_DEFAUT)
        entete = f"**{tp['titre']}** — " + " · ".join(x for x in (tp.get("theme"), tp.get("niveau")) if x)
        lignes = db.obtenir_materiel_tp(tp["id"])
        with st.expander(f"{entete} ({len(lignes)} ligne(s))"):
            infos = [f"v{tp.get('version') or 1}", f"{postes} poste(s)"]
            infos += [x for x in (tp.get("discipline"), tp.get("enseignant"), tp.get("duree")) if x]
            st.caption(" · ".join(infos))
            if tp.get("notes"):
                st.caption(tp["notes"])

            # --- fiche normalisée (chargée et fabriquée seulement à la demande) ---
            if tp["id"] not in fiches_ouvertes:
                if st.button("📄 Préparer la fiche PDF", key=f"pdf_prep_{tp['id']}"):
                    fiches_ouvertes.add(tp["id"])
                    st.rerun()
            else:
                fiche = fiche_tp.fiche_depuis_tp(
                    tp, lignes, {str(a["id"]): a for a in db.obtenir_articles(inclure_inactifs=True)},
                    db.obtenir_fiche_tp(tp["id"]))
                texte_fiche = json.dumps(fiche, ensure_ascii=False, indent=1)
                c1, c2 = st.columns(2)
                c1.download_button("⬇️ Télécharger la fiche PDF", _pdf(texte_fiche),
                                   file_name=fiche_tp.nom_fichier(fiche), mime="application/pdf",
                                   key=f"pdf_dl_{tp['id']}", type="primary", width="stretch")
                if ADMIN:
                    c2.download_button("⬇️ JSON (pour modifier la fiche avec Claude)",
                                       texte_fiche.encode("utf-8"),
                                       file_name=fiche_tp.nom_fichier(fiche).replace(".pdf", ".json"),
                                       mime="application/json", key=f"json_dl_{tp['id']}", width="stretch")

            # --- matériel du TP ---
            manquants = []
            if lignes:
                for l in lignes:
                    etat, stock, manque = db.disponibilite_ligne(l, postes)
                    article = db.obtenir_article(l["article_id"]) if l.get("article_id") else None
                    nom = article["nom"] if article else (l.get("libelle") or "?")
                    cols = st.columns([4, 2, 3, 1])
                    cols[0].write(f"**{nom}**" + (f"  \n{l['caracteristiques']}" if l.get("caracteristiques") else ""))
                    u = l.get("unite") or ""
                    if l.get("emplacement") == "bureau":
                        cols[1].write(f"{db.formater_quantite(l['quantite'])} {u}  \n🧑‍🏫 bureau")
                    else:
                        cols[1].write(f"{db.formater_quantite(l['quantite'])} {u} / poste  \n"
                                      f"= {db.formater_quantite(db.besoin_ligne(l, postes))} {u}")
                    detail = ETATS[etat]
                    if etat in ("ok", "insuffisant") and stock is not None:
                        detail += f" ({db.formater_quantite(stock)} dispo)"
                    cols[2].write(detail)
                    if ADMIN and cols[3].button("🗑️", key=f"suppr_l_{l['id']}", help="Retirer cette ligne"):
                        db.supprimer_materiel_tp(l["id"])
                        st.rerun()
                    if etat == "insuffisant":
                        manquants.append((article, nom, manque, l.get("unite")))
                    elif etat == "hors_inventaire":
                        manquants.append((None, nom, manque, l.get("unite")))
            else:
                st.info("Aucun matériel pour l'instant.")

            # --- commander le manquant ---
            if manquants and ADMIN:
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

            if ADMIN:
                # --- ajouter du matériel ---
                st.markdown("**Ajouter du matériel ou un produit**")
                with st.form(f"ajout_mat_{tp['id']}", clear_on_submit=True):
                    choix = st.selectbox(
                        "Article de l'inventaire (tape pour chercher)", [None] + articles,
                        format_func=lambda a: "— Hors inventaire (saisie libre) —" if a is None else _libelle_article(a),
                        key=f"mat_art_{tp['id']}",
                    )
                    c1, c2 = st.columns([3, 2])
                    libelle = c1.text_input("Désignation (si hors inventaire)", key=f"mat_lib_{tp['id']}")
                    caracteristiques = c2.text_input("Caractéristiques", key=f"mat_car_{tp['id']}",
                                                     placeholder="ex : 25 mL, classe A")
                    c1, c2, c3 = st.columns([2, 1, 1])
                    emplacement = c1.radio("Emplacement", list(db.EMPLACEMENTS_TP), horizontal=True,
                                           format_func=db.EMPLACEMENTS_TP.get, key=f"mat_emp_{tp['id']}")
                    quantite = c2.number_input("Quantité", min_value=0.0, value=1.0, step=0.5, format="%g",
                                               key=f"mat_q_{tp['id']}", help="Par poste si « Par poste »")
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
                                               libelle=None if choix else libelle.strip(),
                                               caracteristiques=caracteristiques.strip() or None,
                                               emplacement=emplacement)
                        st.rerun()

                # --- modifier / supprimer le TP ---
                if st.toggle("✏️ Modifier ou supprimer ce TP", key=f"tog_tp_{tp['id']}"):
                    with st.form(f"edit_tp_{tp['id']}"):
                        champs = _champs_tp(f"edit_{tp['id']}", tp)
                        ve = st.number_input("Version", min_value=1, step=1, value=int(tp.get("version") or 1),
                                             key=f"edit_{tp['id']}_ver")
                        no = st.text_area("Notes internes", value=tp.get("notes") or "")
                        enreg = st.form_submit_button("💾 Enregistrer")
                    if enreg:
                        autre = db.trouver_tp_par_titre(champs["titre"])
                        if not champs["titre"]:
                            st.error("Le titre ne peut pas être vide.")
                        elif autre and autre["id"] != tp["id"]:
                            st.error(f"Un autre TP s'appelle déjà « {champs['titre']} ».")
                        else:
                            db.modifier_tp(tp["id"], notes=no.strip() or None, version=int(ve), **champs)
                            st.rerun()
                    st.caption("Solutions, préparations et sécurité se modifient avec Claude : télécharge le JSON, "
                               "fais-le corriger, puis réimporte-le (même titre = mise à jour).")
                    if st.checkbox("Je confirme vouloir supprimer ce TP", key=f"conf_tp_{tp['id']}"):
                        if st.button("🗑️ Supprimer ce TP", key=f"suppr_tp_{tp['id']}"):
                            db.supprimer_tp(tp["id"])
                            st.rerun()
