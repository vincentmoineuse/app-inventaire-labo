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
# Un TP = une ligne de « tps » (séance + contenu jsonb « fiche » : solutions, sécurité…)
# + ses lignes de matériel « tp_materiel » (quantité PAR POSTE si emplacement = 'poste').
# La fiche PDF normalisée est régénérée à la demande (fiche_tp.py) : jamais stockée dans Supabase.

# Les TP sont repérés par leur TITRE (unique parmi les TP actifs) et classés par THÈME.
DISCIPLINES_TP = ["Physique-chimie", "Physique", "Chimie", "SVT", "STL", "Autre"]
THEMES_TP = ["Électricité", "Chimie", "Mécanique", "Optique", "Thermique", "Pression",
             "Acoustique (son)", "Biologie / SVT", "Autre"]
NIVEAUX_TP = ["CAP", "2de bac pro", "1re bac pro", "Tle bac pro", "2de", "1re", "Tle", "BTS", "CPGE", "Autre"]
POSTES_DEFAUT = 8
EMPLACEMENTS_TP = {"poste": "Par poste", "bureau": "Bureau professeur"}

# Colonnes lues pour la liste : tout sauf le jsonb « fiche », lu seulement à la demande.
_COLONNES_TPS = ("id,titre,discipline,theme,niveau,notes,date_ajout,actif,version,"
                 "enseignant,postes,duree,date_maj")


@st.cache_data(ttl=600, show_spinner=False)
def _tous_les_tps():
    return _get_client().table("tps").select(_COLONNES_TPS).execute().data


@st.cache_data(ttl=600, show_spinner=False)
def _tout_le_materiel_tp():
    return _get_client().table("tp_materiel").select("*").execute().data


@st.cache_data(ttl=600, show_spinner=False)
def obtenir_fiche_tp(tp_id):
    """Contenu jsonb « fiche » d'un seul TP (environ 3 Ko), lu uniquement quand on en a besoin."""
    res = _get_client().table("tps").select("fiche").eq("id", tp_id).execute().data
    return (res[0].get("fiche") if res else None) or {}


def _sans_accents(texte):
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(t.lower().split())


SANS_ENSEIGNANT = "(non renseigné)"


def obtenir_enseignants_tp():
    """Enseignant(e)s présents dans les TP actifs, tirés des données déjà en cache (aucune requête en plus).
    Les variantes d'écriture (accents, majuscules, espaces) sont regroupées sous la première forme rencontrée."""
    noms, sans_nom = {}, False
    for t in _tous_les_tps():
        if not t.get("actif", True):
            continue
        nom = " ".join(str(t.get("enseignant") or "").split())
        if nom:
            noms.setdefault(_sans_accents(nom), nom)
        else:
            sans_nom = True
    liste = sorted(noms.values(), key=_sans_accents)
    return liste + ([SANS_ENSEIGNANT] if sans_nom else [])


def obtenir_tps(theme=None, niveau=None, recherche=None, enseignant=None):
    """Filtres souples (« Tle » retrouve « Tle bac pro ») ; la recherche porte sur le titre et
    l'enseignant(e) est comparé sans tenir compte des accents ni des majuscules."""
    resultat = []
    for t in _tous_les_tps():
        if not t.get("actif", True):
            continue
        if theme and theme != "Tous" and (t.get("theme") or "") != theme:
            continue
        if enseignant and enseignant != "Tous":
            if enseignant == SANS_ENSEIGNANT:
                if str(t.get("enseignant") or "").strip():
                    continue
            elif _sans_accents(t.get("enseignant")) != _sans_accents(enseignant):
                continue
        if niveau and niveau != "Tous" and niveau.lower() not in str(t.get("niveau") or "").lower():
            continue
        if recherche and _sans_accents(recherche) not in _sans_accents(t.get("titre")):
            continue
        resultat.append(t)
    resultat.sort(key=lambda t: (t.get("theme") or "~", _sans_accents(t.get("titre"))))
    return resultat


def trouver_tp_par_titre(titre):
    """TP actif portant ce titre (accents, majuscules et espaces ignorés), sinon None."""
    if not str(titre or "").strip():
        return None
    cle = _sans_accents(titre)
    for t in _tous_les_tps():
        if t.get("actif", True) and _sans_accents(t.get("titre")) == cle:
            return t
    return None


@_ecriture
def ajouter_tp(titre, discipline=None, niveau=None, notes=None, **autres):
    """autres : theme, version, enseignant, postes, duree, fiche."""
    row = {"titre": titre, "discipline": discipline, "niveau": niveau, "notes": notes, "actif": True,
           "date_maj": date.today().isoformat(), **autres}
    res = _get_client().table("tps").insert(row).execute()
    _clear_cache()
    return res.data[0]["id"] if res.data else None


@_ecriture
def modifier_tp(tp_id, **kwargs):
    if kwargs:
        if "actif" not in kwargs:
            kwargs["date_maj"] = date.today().isoformat()
        _get_client().table("tps").update(kwargs).eq("id", tp_id).execute()
        _clear_cache()


def supprimer_tp(tp_id):
    modifier_tp(tp_id, actif=False)


def obtenir_materiel_tp(tp_id):
    lignes = [l for l in _tout_le_materiel_tp() if str(l["tp_id"]) == str(tp_id)]
    lignes.sort(key=lambda l: (l.get("emplacement") == "bureau", l["id"]))
    return lignes


@_ecriture
def ajouter_materiel_tp(tp_id, quantite, unite=None, article_id=None, libelle=None,
                        caracteristiques=None, emplacement="poste"):
    row = {"tp_id": tp_id, "article_id": article_id, "libelle": libelle,
           "quantite": quantite, "unite": unite,
           "caracteristiques": caracteristiques, "emplacement": emplacement}
    _get_client().table("tp_materiel").insert(row).execute()
    _clear_cache()


@_ecriture
def supprimer_materiel_tp(ligne_id):
    _get_client().table("tp_materiel").delete().eq("id", ligne_id).execute()
    _clear_cache()


@_ecriture
def importer_fiche_tp(champs, fiche_json, lignes, remplacer_id=None):
    """Enregistre une fiche importée (JSON du skill Claude, déjà passé dans fiche_tp.preparer_import).
    remplacer_id : met à jour ce TP (son matériel est remplacé par celui de la fiche) au lieu d'en créer un.
    Renvoie l'id du TP."""
    sb = _get_client()
    row = {**champs, "fiche": fiche_json, "date_maj": date.today().isoformat(), "actif": True}
    if remplacer_id:
        sb.table("tps").update(row).eq("id", remplacer_id).execute()
        sb.table("tp_materiel").delete().eq("tp_id", remplacer_id).execute()
        tp_id = remplacer_id
    else:
        res = sb.table("tps").insert(row).execute()
        tp_id = res.data[0]["id"]
    if lignes:
        sb.table("tp_materiel").insert([
            {"tp_id": tp_id, "article_id": l["article_id"], "libelle": l["libelle"],
             "quantite": l["quantite"], "unite": l["unite"],
             "caracteristiques": l["caracteristiques"], "emplacement": l["emplacement"]}
            for l in lignes]).execute()
    _clear_cache()
    return tp_id


def _meme_unite(u1, u2):
    return (u1 or "").strip().lower() == (u2 or "").strip().lower()


def besoin_ligne(ligne, postes=1):
    """Quantité totale nécessaire : quantité × postes pour le matériel par poste."""
    q = float(ligne.get("quantite") or 0)
    return q if ligne.get("emplacement") == "bureau" else q * max(int(postes or 1), 1)


def disponibilite_ligne(ligne, postes=1):
    """Compare le besoin total d'une ligne de TP au stock de l'inventaire.
    Renvoie (etat, stock, manque) ; etat ∈ 'ok', 'insuffisant', 'verifier', 'hors_inventaire'."""
    article = obtenir_article(ligne["article_id"]) if ligne.get("article_id") else None
    besoin = besoin_ligne(ligne, postes)
    if not article or not article.get("actif", True):
        return "hors_inventaire", None, besoin
    stock = float(article["quantite"] or 0)
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


# ---------- FILTRES (hottes à filtration, armoires filtrantes, caissons) ----------
# Trafic Supabase minimal : une seule petite requête (≈ 7 lignes) mise en cache 6 h,
# partagée par la page Filtres et l'alerte de l'accueil, vidée uniquement après une
# modification des filtres. L'historique n'est lu que lorsqu'on demande à l'afficher.

TYPES_APPAREIL_FILTRE = ["Hotte à filtration", "Armoire filtrante", "Caisson de filtration", "Autre"]
FIABILITES_REFERENCE = ["Confirmée", "Probable", "À vérifier"]
RESULTATS_TEST = ["Conforme", "Saturé"]
STATUTS_FILTRE = ["Saturé", "En retard", "Bientôt", "À renseigner", "OK"]   # du plus urgent au moins urgent
STATUTS_ALERTE = ("Saturé", "En retard", "Bientôt")
DELAI_BIENTOT_JOURS = 30
_TTL_FILTRES = 6 * 3600


class TablesFiltresManquantes(Exception):
    pass


def _exiger_admin_lecture():
    if st.session_state.get("role") != "admin":
        raise PermissionError("Suivi des filtres réservé à l'administrateur.")


def _en_date(valeur):
    if not valeur:
        return None
    if isinstance(valeur, date):
        return valeur
    try:
        return datetime.strptime(str(valeur)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def ajouter_mois(d, mois):
    """d + n mois ; le 31/01 + 1 mois donne le 28 (ou 29) février."""
    import calendar
    total = d.month - 1 + int(mois)
    annee, mois_num = d.year + total // 12, total % 12 + 1
    return date(annee, mois_num, min(d.day, calendar.monthrange(annee, mois_num)[1]))


def _vider_cache_filtres():
    _filtres_bruts.clear()
    _evenements_filtres_bruts.clear()


@st.cache_data(ttl=_TTL_FILTRES, show_spinner=False)
def _filtres_bruts():
    try:
        return _get_client().table("filtres").select("*").eq("actif", True).execute().data
    except Exception as e:
        raise TablesFiltresManquantes(str(e))


@st.cache_data(ttl=_TTL_FILTRES, show_spinner=False)
def _evenements_filtres_bruts():
    try:
        return (_get_client().table("filtres_evenements").select("*")
                .order("date_evt", desc=True).order("id", desc=True).execute().data)
    except Exception as e:
        raise TablesFiltresManquantes(str(e))


def calculer_statut_filtre(f, aujourdhui=None):
    """Renvoie (prochaine_echeance, statut, jours_restants). Calcul fait en Python, sans requête."""
    aujourdhui = aujourdhui or date.today()
    pose = _en_date(f.get("date_pose"))
    test = _en_date(f.get("dernier_test_date"))
    if not pose:
        return None, "À renseigner", None
    echeance = ajouter_mois(pose, f.get("periodicite_mois") or 12)
    jours = (echeance - aujourdhui).days
    if f.get("dernier_test_resultat") == "Saturé" and test and test >= pose:
        return echeance, "Saturé", jours
    if jours < 0:
        return echeance, "En retard", jours
    if jours <= DELAI_BIENTOT_JOURS:
        return echeance, "Bientôt", jours
    return echeance, "OK", jours


def obtenir_filtres():
    """Liste des appareils actifs, enrichie de 'echeance', 'statut' et 'jours_restants'."""
    _exiger_admin_lecture()
    res = []
    for f in _filtres_bruts():
        f = dict(f)
        f["echeance"], f["statut"], f["jours_restants"] = calculer_statut_filtre(f)
        res.append(f)
    res.sort(key=lambda f: (f.get("ordre") or 999, f["id"]))
    return res


def filtres_a_surveiller():
    """Pour l'alerte de l'accueil : filtres « Saturé », « En retard » ou « Bientôt ».
    Renvoie [] si les tables n'existent pas encore (l'accueil ne doit jamais planter)."""
    try:
        return [f for f in obtenir_filtres() if f["statut"] in STATUTS_ALERTE]
    except Exception:
        return []


def filtres_pour_accueil():
    """Rappel de l'accueil : tous les filtres avec leur statut, ou None si les tables
    n'existent pas encore. Même requête en cache que la page Filtres (aucun trafic en plus)."""
    try:
        return obtenir_filtres()
    except Exception:
        return None


def obtenir_evenements_filtres(filtre_id=None):
    _exiger_admin_lecture()
    evts = _evenements_filtres_bruts()
    if filtre_id is not None:
        evts = [e for e in evts if str(e["filtre_id"]) == str(filtre_id)]
    return evts


def _journaliser(filtre_id, type_evt, date_evt, resultat=None, notes=None):
    _get_client().table("filtres_evenements").insert({
        "filtre_id": filtre_id, "type_evt": type_evt, "date_evt": str(date_evt),
        "resultat": resultat, "notes": notes or None,
    }).execute()


@_ecriture
def enregistrer_remplacement(filtre_id, date_evt, notes=None):
    """Nouveau filtre posé : met à jour la date de pose, efface le dernier test (il concernait
    l'ancien filtre) et l'inscrit dans l'historique."""
    _get_client().table("filtres").update({
        "date_pose": str(date_evt), "dernier_test_date": None, "dernier_test_resultat": None,
    }).eq("id", filtre_id).execute()
    _journaliser(filtre_id, "Remplacement", date_evt, notes=notes)
    _vider_cache_filtres()


@_ecriture
def enregistrer_test_saturation(filtre_id, date_evt, resultat, notes=None):
    _get_client().table("filtres").update({
        "dernier_test_date": str(date_evt), "dernier_test_resultat": resultat,
    }).eq("id", filtre_id).execute()
    _journaliser(filtre_id, "Test de saturation", date_evt, resultat=resultat, notes=notes)
    _vider_cache_filtres()


@_ecriture
def modifier_filtre(filtre_id, **champs):
    if champs:
        champs = {k: (str(v) if isinstance(v, date) else v) for k, v in champs.items()}
        _get_client().table("filtres").update(champs).eq("id", filtre_id).execute()
        _vider_cache_filtres()


@_ecriture
def ajouter_filtre(appareil, **champs):
    row = {"appareil": appareil, "actif": True,
           **{k: (str(v) if isinstance(v, date) else v) for k, v in champs.items()}}
    _get_client().table("filtres").insert(row).execute()
    _vider_cache_filtres()


def retirer_filtre(filtre_id):
    """Retrait du suivi (appareil réformé) : la ligne et son historique sont conservés."""
    modifier_filtre(filtre_id, actif=False)


# ---------- ÉVACUATION DES DÉCHETS (tickets d'enlèvement) ----------
# Un ticket par enlèvement du prestataire ; on y ajoute des entrées au fil de l'eau
# (bidons de collecte, verrerie cassée, emballages souillés, produits périmés…).
# Trafic Supabase minimal : deux petites requêtes (tickets + entrées, texte seul, aucune
# image) mises en cache 6 h, partagées par la page et l'encart de l'accueil, et vidées
# uniquement après une modification.

# Catégorie -> (code déchet indicatif, état physique par défaut, pictogrammes suggérés)
# Codes de la liste européenne des déchets (annexe II de l'article R541-8 du code de
# l'environnement) ; l'astérisque marque un déchet dangereux. Ils restent modifiables :
# c'est le code inscrit par le prestataire sur le bordereau (BSDD) qui fait foi.
CATEGORIES_DECHET = {
    "Solutions de métaux lourds": ("16 05 06*", "Liquide", "GHS06 - Toxique, GHS09 - Danger pour l'environnement"),
    "Solvants halogénés": ("14 06 02*", "Liquide", "GHS07 - Nocif / Irritant, GHS08 - Danger pour la santé (CMR...)"),
    "Solvants non halogénés": ("14 06 03*", "Liquide", "GHS02 - Inflammable"),
    "Acides": ("16 05 06*", "Liquide", "GHS05 - Corrosif"),
    "Bases": ("16 05 06*", "Liquide", "GHS05 - Corrosif"),
    "Autres solutions de laboratoire": ("16 05 06*", "Liquide", ""),
    "Produits périmés ou inutilisables": ("16 05 06*", "Solide", ""),
    "Emballages / bidons souillés": ("15 01 10*", "Solide", ""),
    "Verrerie cassée souillée": ("", "Solide", ""),
    "Filtres usagés (hottes, armoires)": ("15 02 02*", "Solide", ""),
    "Autre": ("", "Solide", ""),
}
CONTENANTS_DECHET = ["Bidon 5 L", "Bidon 10 L", "Bidon 20 L", "Bidon 30 L", "Flacon d'origine", "Carton",
                     "Seau", "Fût", "Sac", "Autre"]
UNITES_DECHET = ["L", "kg", "mL", "g", "unité(s)"]
ETATS_DECHET = ["Liquide", "Solide", "Pâteux", "Gazeux"]
STATUTS_ENLEVEMENT = ["Ouvert", "Enlevé"]
_TTL_DECHETS = 6 * 3600


class TablesDechetsManquantes(Exception):
    pass


def _exiger_admin_dechets():
    if st.session_state.get("role") != "admin":
        raise PermissionError("Évacuation des déchets réservée à l'administrateur.")


def _vider_cache_dechets():
    _enlevements_bruts.clear()
    _lignes_dechets_brutes.clear()


@st.cache_data(ttl=_TTL_DECHETS, show_spinner=False)
def _enlevements_bruts():
    try:
        return (_get_client().table("dechets_enlevements").select("*").eq("actif", True)
                .order("date_ouverture", desc=True).order("id", desc=True).execute().data)
    except Exception as e:
        raise TablesDechetsManquantes(str(e))


@st.cache_data(ttl=_TTL_DECHETS, show_spinner=False)
def _lignes_dechets_brutes():
    try:
        return (_get_client().table("dechets_lignes").select("*")
                .order("date_ajout").order("id").execute().data)
    except Exception as e:
        raise TablesDechetsManquantes(str(e))


def obtenir_enlevements():
    """Tickets d'enlèvement (les plus récents d'abord), enrichis de 'nb_entrees', 'nb_contenants'
    et 'jours_avant' (jours avant la date d'enlèvement prévue, négatif si dépassée)."""
    _exiger_admin_dechets()
    lignes = _lignes_dechets_brutes()
    res = []
    for e in _enlevements_bruts():
        e = dict(e)
        siennes = [l for l in lignes if str(l["enlevement_id"]) == str(e["id"])]
        e["nb_entrees"] = len(siennes)
        e["nb_contenants"] = sum(int(l.get("nb_contenants") or 0) for l in siennes)
        prevue = _en_date(e.get("date_prevue"))
        e["jours_avant"] = (prevue - date.today()).days if prevue else None
        res.append(e)
    # tickets ouverts en premier, puis du plus récent au plus ancien
    res.sort(key=lambda e: (e["statut"] != "Ouvert",))
    return res


def obtenir_lignes_dechets(enlevement_id=None):
    _exiger_admin_dechets()
    lignes = _lignes_dechets_brutes()
    if enlevement_id is not None:
        lignes = [l for l in lignes if str(l["enlevement_id"]) == str(enlevement_id)]
    return lignes


def totaux_dechets(lignes):
    """{'L': 12.5, 'kg': 3.0, …} — mL et g sont convertis en L et kg."""
    totaux = {}
    for l in lignes:
        q, u = l.get("quantite"), (l.get("unite") or "").strip()
        if q in (None, ""):
            continue
        q = float(q)
        if u == "mL":
            q, u = q / 1000, "L"
        elif u == "g":
            q, u = q / 1000, "kg"
        totaux[u] = totaux.get(u, 0) + q
    return totaux


def texte_totaux(totaux):
    ordre = ["L", "kg", "unité(s)"]
    cles = sorted(totaux, key=lambda u: ordre.index(u) if u in ordre else 99)
    return " + ".join(f"{formater_quantite(totaux[u])} {u}" for u in cles) or "—"


def enlevements_pour_accueil():
    """Encart de l'accueil : tickets ouverts, ou None si les tables n'existent pas encore
    (l'accueil ne doit jamais planter). Même cache que la page : aucun trafic en plus."""
    try:
        return [e for e in obtenir_enlevements() if e["statut"] == "Ouvert"]
    except Exception:
        return None


def _iso(champs):
    return {k: (str(v) if isinstance(v, date) else v) for k, v in champs.items()}


@_ecriture
def creer_enlevement(intitule, **champs):
    row = {"intitule": intitule, "statut": "Ouvert", "actif": True,
           "date_ouverture": str(date.today()), **_iso(champs)}
    res = _get_client().table("dechets_enlevements").insert(row).execute()
    _vider_cache_dechets()
    return res.data[0]["id"] if res.data else None


@_ecriture
def modifier_enlevement(enlevement_id, **champs):
    if champs:
        _get_client().table("dechets_enlevements").update(_iso(champs)).eq("id", enlevement_id).execute()
        _vider_cache_dechets()


def cloturer_enlevement(enlevement_id, date_enlevement, prestataire=None, numero_bsd=None):
    """Déchets enlevés par le prestataire : le ticket passe en lecture seule."""
    modifier_enlevement(enlevement_id, statut="Enlevé", date_enlevement=date_enlevement,
                        prestataire=prestataire or None, numero_bsd=numero_bsd or None)


def rouvrir_enlevement(enlevement_id):
    modifier_enlevement(enlevement_id, statut="Ouvert", date_enlevement=None)


def supprimer_enlevement(enlevement_id):
    """Suppression douce (le ticket et ses entrées restent dans la base)."""
    modifier_enlevement(enlevement_id, actif=False)


@_ecriture
def ajouter_ligne_dechet(enlevement_id, categorie, designation, **champs):
    row = {"enlevement_id": enlevement_id, "categorie": categorie, "designation": designation,
           "date_ajout": str(date.today()), **_iso(champs)}
    _get_client().table("dechets_lignes").insert(row).execute()
    _vider_cache_dechets()


@_ecriture
def modifier_ligne_dechet(ligne_id, **champs):
    if champs:
        _get_client().table("dechets_lignes").update(_iso(champs)).eq("id", ligne_id).execute()
        _vider_cache_dechets()


@_ecriture
def supprimer_ligne_dechet(ligne_id):
    _get_client().table("dechets_lignes").delete().eq("id", ligne_id).execute()
    _vider_cache_dechets()
