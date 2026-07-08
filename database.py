"""
Module de gestion des données pour l'inventaire du laboratoire.
Stockage : Supabase — Postgres pour les données, Storage pour les photos.
Nécessite supabase_url et supabase_key dans st.secrets (voir SETUP.md).
"""
import unicodedata
from datetime import datetime, date

import streamlit as st
from supabase import create_client

CATEGORIES = [
    "Optique",
    "Mécanique",
    "Électricité",
    "Thermodynamique",
    "Acoustique",
    "Électrostatique",
    "Magnétisme",
    "Appareils de mesure",
    "Matériel de chimie",
    "Verrerie",
    "Produits chimiques",
    "Sécurité",
    "Matériel informatique",
]

PICTOGRAMMES_GHS = [
    "GHS01 - Explosif",
    "GHS02 - Inflammable",
    "GHS03 - Comburant",
    "GHS04 - Gaz sous pression",
    "GHS05 - Corrosif",
    "GHS06 - Toxique",
    "GHS07 - Nocif / Irritant",
    "GHS08 - Danger pour la santé (CMR...)",
    "GHS09 - Danger pour l'environnement",
]

CATEGORIE_CHIMIE = "Produits chimiques"
PHOTOS_BUCKET = "photos"


class ConfigurationManquante(Exception):
    pass


@st.cache_resource(show_spinner=False)
def _get_client():
    try:
        url = st.secrets["supabase_url"]
        key = st.secrets["supabase_key"]
    except Exception:
        raise ConfigurationManquante(
            "Les identifiants Supabase (supabase_url / supabase_key) sont introuvables dans "
            "st.secrets. Suis les instructions de SETUP.md pour configurer l'accès à Supabase."
        )
    if not url or not key:
        raise ConfigurationManquante("supabase_url ou supabase_key est vide dans st.secrets.")
    return create_client(url, key)


def init_db():
    """Vérifie que la connexion fonctionne et que les tables existent.
    Les tables elles-mêmes sont créées via le script SQL fourni dans SETUP.md."""
    sb = _get_client()
    try:
        sb.table("articles").select("id").limit(1).execute()
    except Exception as e:
        raise ConfigurationManquante(
            "Impossible d'accéder à la table 'articles' dans Supabase. Vérifie que tu as bien "
            f"exécuté le script SQL de SETUP.md dans l'éditeur SQL de ton projet. Détail : {e}"
        )


def _clear_cache():
    st.cache_data.clear()


# ---------- PHOTOS (Supabase Storage) ----------

def nom_fichier_sur(texte, extension="jpg"):
    """Translittère un texte en un nom de fichier sûr (ASCII uniquement),
    car Supabase Storage rejette les caractères accentués/non-ASCII dans les clés."""
    texte_normalise = unicodedata.normalize("NFKD", texte)
    texte_ascii = texte_normalise.encode("ascii", "ignore").decode("ascii")
    texte_ascii = texte_ascii.replace(" ", "_")
    texte_propre = "".join(c for c in texte_ascii if c.isalnum() or c in "._-")
    return f"{texte_propre}.{extension}" if texte_propre else f"photo.{extension}"


def upload_photo(file_bytes, filename, mimetype="image/jpeg"):
    """Envoie une photo dans le bucket Supabase Storage et renvoie son URL publique."""
    filename = nom_fichier_sur(filename.rsplit(".", 1)[0], filename.rsplit(".", 1)[-1] if "." in filename else "jpg")
    sb = _get_client()
    bucket = sb.storage.from_(PHOTOS_BUCKET)
    bucket.upload(filename, bytes(file_bytes), {"content-type": mimetype, "upsert": "true"})
    return bucket.get_public_url(filename)


# ---------- ARTICLES ----------

def ajouter_article(nom, categorie, quantite, unite, salle, armoire, photo_path=None,
                     numero_cas=None, pictogrammes=None, date_peremption=None, notes=None):
    sb = _get_client()
    row = {
        "nom": nom, "categorie": categorie, "quantite": quantite, "unite": unite,
        "salle": salle, "armoire": armoire, "photo_path": photo_path,
        "numero_cas": numero_cas, "pictogrammes": pictogrammes,
        "date_peremption": date_peremption, "notes": notes,
        "date_ajout": datetime.now().isoformat(), "actif": True,
    }
    res = sb.table("articles").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


def modifier_article(article_id, **kwargs):
    if not kwargs:
        return
    sb = _get_client()
    sb.table("articles").update(kwargs).eq("id", article_id).execute()
    _clear_cache()


def supprimer_article(article_id):
    modifier_article(article_id, actif=False)


@st.cache_data(ttl=15, show_spinner=False)
def _tous_les_articles():
    sb = _get_client()
    res = sb.table("articles").select("*").execute()
    return res.data


def obtenir_articles(categorie=None, salle=None, recherche=None, inclure_inactifs=False):
    articles = _tous_les_articles()
    result = []
    for a in articles:
        if not inclure_inactifs and not a.get("actif", True):
            continue
        if categorie and categorie != "Toutes" and a.get("categorie") != categorie:
            continue
        if salle and salle != "Toutes" and a.get("salle") != salle:
            continue
        if recherche and recherche.lower() not in str(a.get("nom", "")).lower():
            continue
        result.append(a)
    result.sort(key=lambda a: (a.get("categorie", ""), a.get("nom", "")))
    return result


def obtenir_article(article_id):
    for a in _tous_les_articles():
        if str(a.get("id")) == str(article_id):
            return a
    return None


def obtenir_salles():
    salles = {a["salle"] for a in _tous_les_articles() if a.get("actif", True) and a.get("salle")}
    return sorted(salles)


def statistiques():
    articles = [a for a in _tous_les_articles() if a.get("actif", True)]
    total = len(articles)
    par_cat = {}
    for a in articles:
        c = a.get("categorie", "?")
        if c not in par_cat:
            par_cat[c] = {"categorie": c, "n": 0, "qte": 0}
        par_cat[c]["n"] += 1
        par_cat[c]["qte"] += a.get("quantite") or 0
    par_categorie = sorted(par_cat.values(), key=lambda r: r["n"], reverse=True)

    peremption_proche = []
    aujourdhui = date.today()
    for a in articles:
        dp = a.get("date_peremption")
        if dp:
            try:
                d = datetime.strptime(str(dp)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if (d - aujourdhui).days <= 60:
                peremption_proche.append(a)
    peremption_proche.sort(key=lambda a: a["date_peremption"])

    return {"total": total, "par_categorie": par_categorie, "peremption_proche": peremption_proche}


# ---------- SESSIONS D'INVENTAIRE ----------

@st.cache_data(ttl=10, show_spinner=False)
def _toutes_les_sessions():
    sb = _get_client()
    res = sb.table("sessions_inventaire").select("*").execute()
    return res.data


def creer_session(notes=None):
    sb = _get_client()
    row = {"date_debut": datetime.now().isoformat(), "notes": notes}
    res = sb.table("sessions_inventaire").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


def cloturer_session(session_id):
    sb = _get_client()
    sb.table("sessions_inventaire").update(
        {"date_fin": datetime.now().isoformat()}
    ).eq("id", session_id).execute()
    _clear_cache()


def obtenir_session_ouverte():
    sessions = [s for s in _toutes_les_sessions() if not s.get("date_fin")]
    if not sessions:
        return None
    sessions.sort(key=lambda s: s["date_debut"], reverse=True)
    return sessions[0]


def obtenir_sessions():
    sessions = list(_toutes_les_sessions())
    sessions.sort(key=lambda s: s["date_debut"], reverse=True)
    return sessions


def pointer_article(session_id, article_id, quantite_avant, quantite_apres):
    sb = _get_client()
    row = {
        "session_id": session_id, "article_id": article_id,
        "quantite_avant": quantite_avant, "quantite_apres": quantite_apres,
        "date_pointage": datetime.now().isoformat(),
    }
    sb.table("pointages").insert(row).execute()
    _clear_cache()
    modifier_article(article_id, quantite=quantite_apres,
                      date_dernier_inventaire=datetime.now().isoformat())


@st.cache_data(ttl=10, show_spinner=False)
def _tous_les_pointages():
    sb = _get_client()
    res = sb.table("pointages").select("*").execute()
    return res.data


def articles_pointes_session(session_id):
    return {str(p["article_id"]) for p in _tous_les_pointages() if str(p["session_id"]) == str(session_id)}


def resume_session(session_id):
    pointages = [p for p in _tous_les_pointages() if str(p["session_id"]) == str(session_id)]
    articles_par_id = {str(a["id"]): a for a in _tous_les_articles()}
    resultat = []
    for p in pointages:
        a = articles_par_id.get(str(p["article_id"]), {})
        resultat.append({**p, "nom": a.get("nom", "?"), "categorie": a.get("categorie", "?")})
    resultat.sort(key=lambda r: (r["categorie"], r["nom"]))
    return resultat
