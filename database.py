"""
Module de gestion des données pour l'inventaire du laboratoire.
Stockage : Supabase — Postgres pour les données, Storage pour les photos.
Nécessite supabase_url et supabase_key dans st.secrets (voir SETUP.md).
"""
import functools
import io
import unicodedata
from datetime import datetime, date

import streamlit as st
from supabase import create_client

CATEGORIES = [
    "Optique",
    "Mécanique",
    "Mécanique des fluides",
    "Électricité",
    "Thermodynamique",
    "Acoustique",
    "Électrostatique",
    "Magnétisme",
    "Appareils de mesure",
    "EXAO",
    "Matériel de chimie",
    "Verrerie",
    "Produits chimiques",
    "SVT",
    "Sécurité",
    "Matériel informatique",
    "Autres",
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
UNITES_CHIMIE = ["L", "kg", "mL", "g"]


def formater_quantite(valeur):
    """2.0 -> '2' ; 0.5 -> '0,5' ; 2.250 -> '2,25' (affichage à la française)."""
    try:
        v = float(valeur or 0)
    except (TypeError, ValueError):
        return str(valeur)
    texte = f"{v:.3f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")
PHOTOS_BUCKET = "photos"
DOCUMENTS_BUCKET = "documents"


def _ecriture(fonction):
    """Réserve une fonction d'écriture à l'administrateur (même si l'interface oubliait de masquer un bouton)."""
    @functools.wraps(fonction)
    def enveloppe(*args, **kwargs):
        if st.session_state.get("role") != "admin":
            raise PermissionError("Action réservée à l'administrateur.")
        return fonction(*args, **kwargs)
    return enveloppe


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


def compresser_photo(file_bytes, taille_max=800, qualite=80):
    """Réduit une photo (côté le plus long : 800 px, JPEG qualité 80) : de ~3 Mo à ~100 Ko.
    Évite de dépasser le quota de transfert (egress) de Supabase. En cas de souci, renvoie l'original."""
    try:
        from PIL import Image, ImageOps
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(bytes(file_bytes))))
        image.thumbnail((taille_max, taille_max))
        if image.mode != "RGB":
            fond = Image.new("RGB", image.size, "white")
            fond.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
            image = fond
        sortie = io.BytesIO()
        image.save(sortie, "JPEG", quality=qualite, optimize=True, progressive=True)
        return sortie.getvalue()
    except Exception:
        return bytes(file_bytes)


@_ecriture
def upload_photo(file_bytes, filename, mimetype="image/jpeg"):
    """Compresse la photo, l'envoie dans le bucket Supabase Storage et renvoie son URL publique.
    Le nom contient un horodatage unique : le navigateur peut donc garder la photo en cache 1 an."""
    nom = nom_fichier_sur(filename.rsplit(".", 1)[0], "jpg")
    sb = _get_client()
    bucket = sb.storage.from_(PHOTOS_BUCKET)
    bucket.upload(nom, compresser_photo(file_bytes),
                  {"content-type": "image/jpeg", "upsert": "true", "cache-control": "31536000"})
    return bucket.get_public_url(nom)


# ---------- DOCUMENTS PDF (FDS, notices — Supabase Storage) ----------

@_ecriture
def upload_document(file_bytes, filename, sous_dossier, mimetype="application/pdf"):
    """Envoie un PDF (FDS ou notice) dans le bucket documents et renvoie son URL publique.
    sous_dossier : 'fds' ou 'notices', pour garder les fichiers organisés dans le bucket."""
    base = nom_fichier_sur(filename.rsplit(".", 1)[0], "pdf")
    chemin = f"{sous_dossier}/{int(datetime.now().timestamp())}_{base}"
    sb = _get_client()
    bucket = sb.storage.from_(DOCUMENTS_BUCKET)
    bucket.upload(chemin, bytes(file_bytes), {"content-type": mimetype, "upsert": "true"})
    return bucket.get_public_url(chemin)


# ---------- ARTICLES ----------

@_ecriture
def ajouter_article(nom, categorie, quantite, unite, salle, armoire, photo_path=None,
                     numero_cas=None, pictogrammes=None, date_peremption=None, notes=None,
                     fds_path=None, notice_path=None):
    sb = _get_client()
    row = {
        "nom": nom, "categorie": categorie, "quantite": quantite, "unite": unite,
        "salle": salle, "armoire": armoire, "photo_path": photo_path,
        "numero_cas": numero_cas, "pictogrammes": pictogrammes,
        "date_peremption": date_peremption, "notes": notes,
        "fds_path": fds_path, "notice_path": notice_path,
        "date_ajout": datetime.now().isoformat(), "actif": True,
    }
    res = sb.table("articles").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


@_ecriture
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


@_ecriture
def creer_session(notes=None):
    sb = _get_client()
    row = {"date_debut": datetime.now().isoformat(), "notes": notes}
    res = sb.table("sessions_inventaire").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


@_ecriture
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


@_ecriture
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


# ---------- TP (travaux pratiques) ----------

DISCIPLINES_TP = ["Physique", "Chimie", "SVT", "Autre"]
NIVEAUX_TP = ["Collège", "Seconde", "Première", "Terminale", "Post-bac / BTS", "Autre"]


@st.cache_data(ttl=15, show_spinner=False)
def _tous_les_tps():
    return _get_client().table("tps").select("*").execute().data


@st.cache_data(ttl=15, show_spinner=False)
def _tout_le_materiel_tp():
    return _get_client().table("tp_materiel").select("*").execute().data


def obtenir_tps(discipline=None, niveau=None, recherche=None):
    resultat = []
    for t in _tous_les_tps():
        if not t.get("actif", True):
            continue
        if discipline and discipline != "Toutes" and t.get("discipline") != discipline:
            continue
        if niveau and niveau != "Tous" and t.get("niveau") != niveau:
            continue
        if recherche and recherche.lower() not in str(t.get("titre", "")).lower():
            continue
        resultat.append(t)
    resultat.sort(key=lambda t: (t.get("discipline") or "", t.get("titre") or ""))
    return resultat


@_ecriture
def ajouter_tp(titre, discipline=None, niveau=None, date_prevue=None, notes=None):
    row = {"titre": titre, "discipline": discipline, "niveau": niveau,
           "date_prevue": date_prevue, "notes": notes, "actif": True}
    res = _get_client().table("tps").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


@_ecriture
def modifier_tp(tp_id, **kwargs):
    if kwargs:
        _get_client().table("tps").update(kwargs).eq("id", tp_id).execute()
        _clear_cache()


def supprimer_tp(tp_id):
    modifier_tp(tp_id, actif=False)


def obtenir_materiel_tp(tp_id):
    lignes = [l for l in _tout_le_materiel_tp() if str(l["tp_id"]) == str(tp_id)]
    lignes.sort(key=lambda l: l["id"])
    return lignes


@_ecriture
def ajouter_materiel_tp(tp_id, quantite, unite=None, article_id=None, libelle=None):
    row = {"tp_id": tp_id, "article_id": article_id, "libelle": libelle,
           "quantite": quantite, "unite": unite}
    _get_client().table("tp_materiel").insert(row).execute()
    _clear_cache()


@_ecriture
def supprimer_materiel_tp(ligne_id):
    _get_client().table("tp_materiel").delete().eq("id", ligne_id).execute()
    _clear_cache()


def _meme_unite(u1, u2):
    return (u1 or "").strip().lower() == (u2 or "").strip().lower()


def disponibilite_ligne(ligne):
    """Compare le besoin d'une ligne de TP au stock de l'inventaire.
    Renvoie (etat, stock, manque) ; etat ∈ 'ok', 'insuffisant', 'verifier', 'hors_inventaire'."""
    article = obtenir_article(ligne["article_id"]) if ligne.get("article_id") else None
    if not article or not article.get("actif", True):
        return "hors_inventaire", None, float(ligne["quantite"] or 0)
    stock = float(article["quantite"] or 0)
    besoin = float(ligne["quantite"] or 0)
    if not _meme_unite(article.get("unite"), ligne.get("unite")):
        return "verifier", stock, 0.0
    if stock >= besoin:
        return "ok", stock, 0.0
    return "insuffisant", stock, besoin - stock


# ---------- COMMANDES ----------

STATUTS_COMMANDE = ["À commander", "Commandée", "Reçue", "Annulée"]


@st.cache_data(ttl=15, show_spinner=False)
def _toutes_les_commandes():
    return _get_client().table("commandes").select("*").execute().data


@st.cache_data(ttl=15, show_spinner=False)
def _toutes_les_lignes_commande():
    return _get_client().table("commande_lignes").select("*").execute().data


def obtenir_commandes(statuts=None):
    """statuts : liste de statuts à garder (None = tous)."""
    res = [c for c in _toutes_les_commandes()
           if c.get("actif", True) and (not statuts or c.get("statut") in statuts)]
    res.sort(key=lambda c: c["id"], reverse=True)
    return res


@_ecriture
def creer_commande(titre, fournisseur=None, notes=None):
    row = {"titre": titre, "fournisseur": fournisseur, "notes": notes,
           "statut": "À commander", "actif": True}
    res = _get_client().table("commandes").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


@_ecriture
def modifier_commande(commande_id, **kwargs):
    if kwargs:
        _get_client().table("commandes").update(kwargs).eq("id", commande_id).execute()
        _clear_cache()


def supprimer_commande(commande_id):
    modifier_commande(commande_id, actif=False)


def obtenir_lignes_commande(commande_id):
    lignes = [l for l in _toutes_les_lignes_commande() if str(l["commande_id"]) == str(commande_id)]
    lignes.sort(key=lambda l: l["id"])
    return lignes


@_ecriture
def ajouter_ligne_commande(commande_id, designation, quantite, unite=None, article_id=None,
                            reference_fournisseur=None, prix_unitaire=None):
    row = {"commande_id": commande_id, "article_id": article_id, "designation": designation,
           "reference_fournisseur": reference_fournisseur, "quantite": quantite,
           "unite": unite, "prix_unitaire": prix_unitaire, "recu": False}
    _get_client().table("commande_lignes").insert(row).execute()
    _clear_cache()


@_ecriture
def supprimer_ligne_commande(ligne_id):
    _get_client().table("commande_lignes").delete().eq("id", ligne_id).execute()
    _clear_cache()


def total_commande(commande_id):
    """Total estimé (lignes avec prix uniquement)."""
    return sum(float(l["quantite"] or 0) * float(l["prix_unitaire"])
               for l in obtenir_lignes_commande(commande_id) if l.get("prix_unitaire") is not None)


@_ecriture
def receptionner_commande(commande_id):
    """Passe la commande à « Reçue » et ajoute au stock les quantités des lignes liées à un article
    (uniquement si l'unité de la ligne est la même que celle de l'article).
    Renvoie la liste des lignes qui n'ont pas pu être ajoutées automatiquement."""
    non_ajoutees = []
    for l in obtenir_lignes_commande(commande_id):
        if l.get("recu"):
            continue
        article = obtenir_article(l["article_id"]) if l.get("article_id") else None
        if article and _meme_unite(article.get("unite"), l.get("unite")):
            nouveau = float(article["quantite"] or 0) + float(l["quantite"] or 0)
            modifier_article(article["id"], quantite=nouveau)
        elif article:
            non_ajoutees.append(f"{l['designation']} (unité commandée « {l.get('unite') or '—'} » "
                                f"≠ unité du stock « {article.get('unite') or '—'} »)")
        _get_client().table("commande_lignes").update({"recu": True}).eq("id", l["id"]).execute()
    modifier_commande(commande_id, statut="Reçue")
    _clear_cache()
    return non_ajoutees
