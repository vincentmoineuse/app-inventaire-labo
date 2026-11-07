"""Page Streamlit : fiches FDS synthétiques (une fiche par produit chimique).

À placer avec fds_synth.py, clp_textes.py et le dossier pictos/ dans ton appli,
puis déclarer la page dans st.navigation, par exemple :
    st.Page("fiches_fds.py", title="Fiches FDS")

Dépendances : streamlit, supabase, reportlab, qrcode[pil]
Secrets attendus (adapte get_client() si ton appli a déjà un client Supabase) :
    SUPABASE_URL, SUPABASE_KEY
"""
import datetime
import re

import streamlit as st
from supabase import create_client

from common import est_admin
from pictos import afficher_pictogrammes
from clp_textes import H_TEXTES, P_TEXTES, texte_h, texte_p
from extraire_fds import extraire, traiter_article
from fds_synth import fiche_depuis_ligne, generer_pdf

ADMIN = est_admin()

PICTOS = {
    "GHS01": "GHS01 - Explosif",
    "GHS02": "GHS02 - Inflammable",
    "GHS03": "GHS03 - Comburant",
    "GHS04": "GHS04 - Gaz sous pression",
    "GHS05": "GHS05 - Corrosif",
    "GHS06": "GHS06 - Toxique",
    "GHS07": "GHS07 - Nocif / Irritant",
    "GHS08": "GHS08 - Danger pour la santé",
    "GHS09": "GHS09 - Danger pour l'environnement",
}


@st.cache_resource
def get_client():
    def secret(*noms):
        for n in noms:
            try:
                if n in st.secrets:
                    return st.secrets[n]
                if "supabase" in st.secrets and n in st.secrets["supabase"]:
                    return st.secrets["supabase"][n]
            except Exception:
                pass
        return None

    url = secret("supabase_url", "SUPABASE_URL", "url")
    cle = secret("supabase_key", "SUPABASE_KEY", "key")
    if not (url and cle):
        st.error("Identifiants Supabase introuvables dans les secrets de l'appli "
                 "(attendus : supabase_url et supabase_key).")
        st.stop()
    return create_client(url, cle)


def pictos_depuis_texte(txt):
    """'GHS05 - Corrosif, GHS07 - Nocif / Irritant' -> ['GHS05', 'GHS07']"""
    return sorted(set(re.findall(r"GHS0[1-9]", txt or "")))


def charger_produits():
    r = (get_client().table("articles")
         .select("id, nom, numero_cas, pictogrammes, fds_path")
         .eq("categorie", "Produits chimiques").eq("actif", True)
         .order("nom").execute())
    return r.data


def charger_fiche(article_id):
    r = (get_client().table("fds_synthese").select("*")
         .eq("article_id", article_id).limit(1).execute())
    return r.data[0] if r.data else None


def enregistrer(article_id, valeurs, valider=False):
    if not est_admin():
        raise PermissionError("Action réservée à l'administrateur.")
    valeurs = dict(valeurs, article_id=article_id,
                   updated_at=datetime.datetime.utcnow().isoformat())
    if valider:
        valeurs["statut"] = "valide"
        valeurs["valide_le"] = datetime.datetime.utcnow().isoformat()
    else:
        valeurs["statut"] = "brouillon"
        valeurs["valide_le"] = None
    get_client().table("fds_synthese").upsert(valeurs, on_conflict="article_id").execute()


def afficher_lecture(choix, fiche):
    """Affichage en lecture seule d'une fiche validée (accès consultation)."""
    st.subheader(fiche.get("nom_affichage") or choix["nom"])
    infos = [x for x in [fiche.get("formule"),
                         f"CAS {fiche['cas']}" if fiche.get("cas") else None,
                         fiche.get("concentration")] if x]
    if infos:
        st.caption(" • ".join(infos))
    if fiche.get("mention"):
        st.markdown(f"### {'🔴' if fiche['mention'] == 'DANGER' else '🟠'} {fiche['mention']}")
    if fiche.get("pictos"):
        afficher_pictogrammes(", ".join(fiche["pictos"]), taille=72)

    def liste(titre, elements):
        if elements:
            st.markdown(f"**{titre}**")
            st.markdown("\n".join(f"- {e}" for e in elements))

    liste("Mentions de danger (H)", [f"**{m['code']}** {m['texte']}" for m in fiche.get("mentions_h") or []])
    liste("Conseils de prudence (P)", [f"**{m['code']}** {m['texte']}" for m in fiche.get("mentions_p") or []])
    liste("Équipements de protection (EPI)", fiche.get("epi") or [])
    liste("Premiers secours", [f"**{x['titre']}** : {x['texte']}" for x in fiche.get("premiers_secours") or []])
    for titre, cle in [("Stockage", "stockage"), ("À ne pas mélanger avec", "incompatibilites"),
                       ("Déversement", "deversement"), ("Déchets", "dechets")]:
        if fiche.get(cle):
            st.markdown(f"**{titre}** : {fiche[cle]}")
    if choix.get("fds_path"):
        st.link_button("📄 Ouvrir la FDS officielle du fournisseur", choix["fds_path"])
    st.caption("La FDS du fournisseur reste la référence.")


st.title("Fiches FDS synthétiques")

produits = charger_produits()
if not ADMIN:
    # Les visiteurs ne voient que les fiches relues et validées.
    valides = {f["article_id"] for f in get_client().table("fds_synthese").select("article_id")
               .eq("statut", "valide").execute().data}
    produits = [p for p in produits if p["id"] in valides]
    if not produits:
        st.info("Aucune fiche validée pour le moment.")
        st.stop()
if not produits:
    st.info("Aucun produit chimique actif dans l'inventaire.")
    st.stop()

choix = st.selectbox("Produit", produits, format_func=lambda p: p["nom"])
fiche = charger_fiche(choix["id"]) or {}
k = f"fds_{choix['id']}"

if not ADMIN:
    afficher_lecture(choix, fiche)
    if fiche:
        pdf_lecture = generer_pdf(fiche_depuis_ligne(fiche))
        st.download_button("Télécharger la fiche A4 (PDF)", pdf_lecture,
                           file_name=f"FDS_{re.sub(r'[^A-Za-z0-9]+', '_', fiche.get('nom_affichage') or choix['nom'])}.pdf",
                           mime="application/pdf")
    st.stop()

if fiche:
    if fiche["statut"] == "valide":
        st.success("Fiche validée")
    else:
        st.warning("Brouillon : à relire avec la FDS officielle avant de valider")
else:
    st.info("Pas encore de fiche pour ce produit : remplis le formulaire ci-dessous.")
st.caption("La FDS du fournisseur reste la référence : relis chaque phrase H/P et chaque consigne.")
if choix.get("fds_path"):
    st.markdown(f"[Ouvrir la FDS officielle]({choix['fds_path']})")


@st.cache_data(show_spinner=False)
def extraits_fds(url, nom):
    return extraire(url, nom)


if choix.get("fds_path"):
    if not fiche and st.button("Pré-remplir depuis la FDS officielle"):
        with st.spinner("Lecture de la FDS…"):
            try:
                traiter_article(get_client(), choix)
                st.rerun()
            except Exception as e:
                st.error(f"FDS illisible ou introuvable : {e}")
    with st.expander("Extraits de la FDS (rubriques 4, 6, 7, 8, 10, 13) pour rédiger les consignes"):
        try:
            res = extraits_fds(choix["fds_path"], choix["nom"])
            for a in res["avertissements"]:
                st.warning(a)
            for n, txt in res["extraits"].items():
                st.markdown(f"**Rubrique {n}**")
                st.text(txt or "(rubrique non trouvée)")
        except Exception as e:
            st.error(f"FDS illisible ou introuvable : {e}")

with st.form(k):
    c1, c2 = st.columns(2)
    nom = c1.text_input("Nom affiché", fiche.get("nom_affichage") or choix["nom"])
    formule = c2.text_input("Formule", fiche.get("formule") or "")
    cas = c1.text_input("N° CAS", fiche.get("cas") or choix.get("numero_cas") or "")
    conc = c2.text_input("Concentration / forme", fiche.get("concentration") or "")
    mention = st.selectbox("Mention d'avertissement", ["", "DANGER", "ATTENTION"],
                           index=["", "DANGER", "ATTENTION"].index(fiche.get("mention") or ""))

    pictos_def = fiche.get("pictos") or pictos_depuis_texte(choix.get("pictogrammes"))
    pictos = st.multiselect("Pictogrammes", list(PICTOS), default=pictos_def,
                            format_func=lambda c: PICTOS[c])

    h_def = [x["code"] for x in (fiche.get("mentions_h") or [])]
    p_def = [x["code"] for x in (fiche.get("mentions_p") or [])]
    h_codes = st.multiselect("Mentions H", list(H_TEXTES), default=[c for c in h_def if c in H_TEXTES],
                             format_func=lambda c: f"{c} {H_TEXTES[c][:60]}")
    p_codes = st.multiselect("Mentions P", list(P_TEXTES), default=[c for c in p_def if c in P_TEXTES],
                             format_func=lambda c: f"{c} {P_TEXTES[c][:60]}")

    epi_txt = st.text_area("EPI (un par ligne)", "\n".join(fiche.get("epi") or []), height=100)

    sec_def = {s["titre"]: s["texte"] for s in (fiche.get("premiers_secours") or [])}
    secours = {t: st.text_input(f"Premiers secours — {t}", sec_def.get(t, ""))
               for t in ["Yeux", "Peau", "Inhalation", "Ingestion"]}

    stockage = st.text_area("Stockage", fiche.get("stockage") or "", height=70)
    incompat = st.text_area("À ne pas mélanger avec", fiche.get("incompatibilites") or "", height=70)
    deversement = st.text_area("Déversement", fiche.get("deversement") or "", height=70)
    dechets = st.text_area("Déchets", fiche.get("dechets") or "", height=70)

    c3, c4 = st.columns(2)
    fds_url = c3.text_input("Lien FDS officielle (QR code)",
                            fiche.get("fds_source_url") or choix.get("fds_path") or "")
    fds_date = c4.date_input("Date de la FDS officielle",
                             value=datetime.date.fromisoformat(fiche["fds_date"]) if fiche.get("fds_date") else None)

    b1, b2 = st.columns(2)
    brouillon = b1.form_submit_button("Enregistrer en brouillon")
    valider = b2.form_submit_button("J'ai relu avec la FDS : valider", type="primary")

if brouillon or valider:
    enregistrer(choix["id"], {
        "nom_affichage": nom, "formule": formule, "cas": cas, "concentration": conc,
        "mention": mention or None, "pictos": pictos,
        "mentions_h": [{"code": c, "texte": texte_h(c)} for c in h_codes],
        "mentions_p": [{"code": c, "texte": texte_p(c)} for c in p_codes],
        "epi": [e.strip() for e in epi_txt.splitlines() if e.strip()],
        "premiers_secours": [{"titre": t, "texte": v} for t, v in secours.items() if v],
        "stockage": stockage, "incompatibilites": incompat,
        "deversement": deversement, "dechets": dechets,
        "fds_source_url": fds_url or None,
        "fds_date": fds_date.isoformat() if fds_date else None,
    }, valider=valider)
    st.success("Fiche validée" if valider else "Brouillon enregistré")
    st.rerun()

if fiche:
    pdf = generer_pdf(fiche_depuis_ligne(fiche))
    st.download_button("Télécharger la fiche A4 (PDF)", pdf,
                       file_name=f"FDS_{re.sub(r'[^A-Za-z0-9]+', '_', fiche.get('nom_affichage') or choix['nom'])}.pdf",
                       mime="application/pdf")
