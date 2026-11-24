import streamlit as st
import pandas as pd
from datetime import date
import database as db
from common import verifier_config, exiger_admin

verifier_config()
exiger_admin()

st.title("🌀 Filtres")
st.caption("Suivi des filtres des hottes à filtration, des armoires filtrantes et des caissons du plateau scientifique.")

COULEURS = {
    "Saturé": "background-color:#f8d7da;color:#842029;font-weight:600",
    "En retard": "background-color:#f8d7da;color:#842029;font-weight:600",
    "Bientôt": "background-color:#fff3cd;color:#664d03;font-weight:600",
    "À renseigner": "background-color:#e2e3e5;color:#41464b",
    "OK": "background-color:#d1e7dd;color:#0f5132",
}
EMOJI = {"Saturé": "🔴", "En retard": "🔴", "Bientôt": "🟠", "À renseigner": "⚪", "OK": "🟢"}


def _fr(d):
    d = db._en_date(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def _reste(f):
    j = f["jours_restants"]
    if j is None:
        return ""
    return f"dépassée de {-j} j" if j < 0 else f"dans {j} j"


try:
    filtres = db.obtenir_filtres()
except db.TablesFiltresManquantes:
    st.error("Les tables `filtres` et `filtres_evenements` n'existent pas encore dans Supabase. "
             "Exécute le script SQL de la section **6 ter** de **SETUP.md** dans le *SQL Editor* de Supabase, "
             "puis recharge cette page.")
    st.stop()

message = st.session_state.pop("filtres_message", None)
if message:
    (st.warning if message[0] == "warning" else st.success)(message[1])

# ---------- Synthèse ----------
compte = {s: sum(1 for f in filtres if f["statut"] == s) for s in db.STATUTS_FILTRE}
m1, m2, m3, m4 = st.columns(4)
m1.metric("🔴 En retard / saturés", compte["En retard"] + compte["Saturé"])
m2.metric(f"🟠 Bientôt (≤ {db.DELAI_BIENTOT_JOURS} j)", compte["Bientôt"])
m3.metric("⚪ À renseigner", compte["À renseigner"])
m4.metric("🟢 OK", compte["OK"])

# ---------- Tableau ----------
lignes = [{
    "Appareil": f["appareil"],
    "Filtre de remplacement": f.get("filtre_reference") or "",
    "Date de pose": _fr(f.get("date_pose")),
    "Prochaine échéance": (f"{_fr(f['echeance'])} ({_reste(f)})" if f["echeance"] else "—"),
    "Statut": f["statut"],
    "Dernier test de saturation": (f"{_fr(f['dernier_test_date'])} – {f.get('dernier_test_resultat') or '?'}"
                                   if f.get("dernier_test_date") else "—"),
    "Périodicité (mois)": f.get("periodicite_mois"),
    "Type d'appareil": f.get("type_appareil") or "",
    "Dimensions": f.get("dimensions") or "",
    "Fiabilité réf.": f.get("fiabilite_reference") or "",
    "Remarques": f.get("remarques") or "",
} for f in filtres]

if lignes:
    df = pd.DataFrame(lignes)
    st.dataframe(
        df.style.map(lambda v: COULEURS.get(v, ""), subset=["Statut"]),
        hide_index=True, width="stretch",
        column_config={
            "Appareil": st.column_config.TextColumn(width="medium"),
            "Remarques": st.column_config.TextColumn(width="large"),
            "Périodicité (mois)": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.download_button("⬇️ Télécharger le tableau (CSV)", df.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       f"suivi_filtres_{date.today():%Y-%m-%d}.csv", "text/csv")
else:
    st.info("Aucun appareil suivi. Ajoute-en un ci-dessous.")

st.caption(f"Échéance = date de pose + périodicité. « Bientôt » : {db.DELAI_BIENTOT_JOURS} jours ou moins avant l'échéance. "
           "« Saturé » : le dernier test de saturation, fait après la pose du filtre, est positif → remplacer sans attendre.")

st.divider()

# ---------- Actions ----------
st.subheader("✍️ Enregistrer une intervention")
onglet_rempl, onglet_test, onglet_modif, onglet_ajout = st.tabs(
    ["🔁 Remplacement", "🧪 Test de saturation", "✏️ Modifier un appareil", "➕ Ajouter un appareil"])


def _choix_appareil(cle):
    return st.selectbox("Appareil", filtres, key=cle,
                        format_func=lambda f: f"{EMOJI[f['statut']]} {f['appareil']} — {f.get('filtre_reference') or 'filtre ?'}")


with onglet_rempl:
    if filtres:
        st.caption("Pose d'un filtre neuf (ou première saisie de la date de pose du filtre en place). "
                   "La date de pose est mise à jour et l'intervention est inscrite dans l'historique.")
        with st.form("f_remplacement", clear_on_submit=True):
            f = _choix_appareil("rempl_app")
            d = st.date_input("Date de pose", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
            notes = st.text_input("Notes (n° de lot, fournisseur, élimination du filtre usagé…)")
            if st.form_submit_button("🔁 Enregistrer le remplacement", type="primary"):
                db.enregistrer_remplacement(f["id"], d, notes.strip())
                st.session_state["filtres_message"] = ("success", f"Remplacement enregistré pour « {f['appareil']} » "
                                                       f"(pose le {_fr(d)}).")
                st.rerun()

with onglet_test:
    if filtres:
        st.caption("Test de saturation (à faire régulièrement : rappel toutes les 60 h de fonctionnement selon Erlab "
                   "et Trionyx, ou à l'alarme du détecteur).")
        with st.form("f_test", clear_on_submit=True):
            f = _choix_appareil("test_app")
            c1, c2 = st.columns(2)
            d = c1.date_input("Date du test", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
            resultat = c2.radio("Résultat", db.RESULTATS_TEST, horizontal=True)
            notes = st.text_input("Notes (méthode, produit testé, valeur lue…)")
            if st.form_submit_button("🧪 Enregistrer le test", type="primary"):
                db.enregistrer_test_saturation(f["id"], d, resultat, notes.strip())
                if resultat == "Saturé":
                    st.session_state["filtres_message"] = ("warning", f"Test « saturé » enregistré pour « {f['appareil']} » : "
                                                           "remplace le filtre sans attendre l'échéance.")
                else:
                    st.session_state["filtres_message"] = ("success", f"Test conforme enregistré pour « {f['appareil']} ».")
                st.rerun()


def _champs_appareil(prefixe, f=None):
    f = f or {}
    appareil = st.text_input("Appareil *", value=f.get("appareil", ""), key=f"{prefixe}_app")
    c1, c2 = st.columns(2)
    types = db.TYPES_APPAREIL_FILTRE
    type_app = c1.selectbox("Type d'appareil", types, key=f"{prefixe}_type",
                            index=types.index(f["type_appareil"]) if f.get("type_appareil") in types else 0)
    periodicite = c2.number_input("Périodicité maximale (mois)", min_value=1, max_value=60, step=1,
                                  value=int(f.get("periodicite_mois") or 12), key=f"{prefixe}_per")
    reference = st.text_input("Filtre de remplacement (référence)", value=f.get("filtre_reference") or "", key=f"{prefixe}_ref")
    c3, c4 = st.columns(2)
    dimensions = c3.text_input("Dimensions", value=f.get("dimensions") or "", key=f"{prefixe}_dim")
    fiab = db.FIABILITES_REFERENCE
    fiabilite = c4.selectbox("Fiabilité de la référence", fiab, key=f"{prefixe}_fiab",
                             index=fiab.index(f["fiabilite_reference"]) if f.get("fiabilite_reference") in fiab else 2)
    remarques = st.text_area("Remarques", value=f.get("remarques") or "", key=f"{prefixe}_rem")
    return {"appareil": appareil.strip(), "type_appareil": type_app, "periodicite_mois": int(periodicite),
            "filtre_reference": reference.strip() or None, "dimensions": dimensions.strip() or None,
            "fiabilite_reference": fiabilite, "remarques": remarques.strip() or None}


with onglet_modif:
    if filtres:
        f = _choix_appareil("modif_app")
        with st.form(f"f_modif_{f['id']}"):
            champs = _champs_appareil(f"m{f['id']}", f)
            pose_actuelle = db._en_date(f.get("date_pose"))
            corriger = st.checkbox("Corriger la date de pose (erreur de saisie, sans l'inscrire comme remplacement)")
            pose = st.date_input("Date de pose corrigée", value=pose_actuelle or date.today(), max_value=date.today(),
                                 format="DD/MM/YYYY")
            if st.form_submit_button("💾 Enregistrer les modifications", type="primary"):
                if not champs["appareil"]:
                    st.error("Le nom de l'appareil est obligatoire.")
                else:
                    if corriger:
                        champs["date_pose"] = pose
                    db.modifier_filtre(f["id"], **champs)
                    st.session_state["filtres_message"] = ("success", f"« {champs['appareil']} » mis à jour.")
                    st.rerun()
        if st.toggle("🗑️ Retirer cet appareil du suivi (appareil réformé)", key=f"tog_retrait_{f['id']}"):
            st.caption("L'appareil disparaît du tableau, mais sa ligne et son historique restent dans la base.")
            if st.checkbox("Je confirme le retrait", key=f"conf_retrait_{f['id']}"):
                if st.button("Retirer définitivement du suivi", key=f"retrait_{f['id']}"):
                    db.retirer_filtre(f["id"])
                    st.session_state["filtres_message"] = ("success", f"« {f['appareil']} » retiré du suivi.")
                    st.rerun()

with onglet_ajout:
    with st.form("f_ajout", clear_on_submit=True):
        champs = _champs_appareil("ajout")
        if st.form_submit_button("➕ Ajouter l'appareil", type="primary"):
            if not champs["appareil"]:
                st.error("Le nom de l'appareil est obligatoire.")
            else:
                appareil = champs.pop("appareil")
                db.ajouter_filtre(appareil, ordre=len(filtres) + 1, **champs)
                st.session_state["filtres_message"] = ("success", f"« {appareil} » ajouté. Saisis sa date de pose "
                                                       "dans l'onglet 🔁 Remplacement.")
                st.rerun()

st.divider()

# ---------- Historique (chargé seulement à la demande) ----------
st.subheader("📜 Historique des interventions")
if st.toggle("Afficher l'historique (remplacements et tests de saturation)", key="voir_historique"):
    noms = {f["id"]: f["appareil"] for f in filtres}
    choix = st.selectbox("Appareil", [None] + filtres, key="histo_app",
                         format_func=lambda f: "Tous les appareils" if f is None else f["appareil"])
    evts = db.obtenir_evenements_filtres(choix["id"] if choix else None)
    if evts:
        dfh = pd.DataFrame([{
            "Date": _fr(e["date_evt"]),
            "Appareil": noms.get(e["filtre_id"], f"(appareil retiré n°{e['filtre_id']})"),
            "Intervention": e["type_evt"],
            "Résultat": e.get("resultat") or "",
            "Notes": e.get("notes") or "",
        } for e in evts])
        st.dataframe(dfh, hide_index=True, width="stretch")
        st.download_button("⬇️ Exporter l'historique (CSV, pour le dossier de maintenance)",
                           dfh.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           f"historique_filtres_{date.today():%Y-%m-%d}.csv", "text/csv")
    else:
        st.info("Aucune intervention enregistrée pour le moment.")

# ---------- Aide réglementaire ----------
with st.expander("📘 Rappels réglementaires"):
    st.markdown("""
- **Sorbonnes à recirculation** (hottes à filtration) : norme **NF X 15-211 (2009)**. Faire un **test de saturation**
  régulier : rappel toutes les **60 h de fonctionnement** selon Erlab et Trionyx, ou suivre l'alarme du détecteur s'il y en a un.
- **Erlab** : sans certificat Valipass, remplacer le **filtre moléculaire au minimum tous les 12 mois** et le
  **filtre HEPA au minimum tous les 36 mois**. Remplacer **immédiatement** si un produit est détecté en aval du filtre.
- **Arrêté du 8 octobre 1987** : contrôle **annuel** des installations d'aspiration, **semestriel** quand l'air est
  recyclé. Les résultats sont à noter dans le **dossier de maintenance** (l'export CSV de l'historique peut y être joint).
- Un **filtre usagé est un déchet chimique** : l'éliminer par une filière qui assure la traçabilité.
""")
