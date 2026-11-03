#!/usr/bin/env python3
"""Pré-remplissage des fiches FDS synthétiques à partir des FDS officielles (PDF).

Principe : on n'extrait que ce qui est fiable et vérifiable.
  - codes H et P lus dans la rubrique 2 de la FDS, puis libellés officiels via clp_textes.py
  - mention d'avertissement, n° CAS, date de la FDS
  - pictogrammes déduits des codes H (à vérifier à l'œil)
  - premiers secours et EPI pré-remplis à partir des codes P (textes officiels)
Les rubriques 4, 6, 7, 8, 10, 13 sont renvoyées en extraits bruts pour t'aider à
rédiger stockage, incompatibilités, déversement et déchets : rien n'est inventé.
Toute fiche créée est au statut « brouillon ».

Dépendances : pypdf, requests, supabase (pour le mode base de données)

Usage :
    python extraire_fds.py fichier.pdf                 # affiche le résultat
    python extraire_fds.py --article 187               # crée le brouillon pour l'article 187
    python extraire_fds.py --tous --limite 5           # 5 produits sans fiche
Variables : SUPABASE_URL, SUPABASE_KEY
"""
import io
import os
import re
import sys

from clp_textes import H_TEXTES, P_TEXTES, texte_h, texte_p

# --------------------------------------------------------------- lecture PDF


def texte_pdf(source):
    """source : chemin local, URL http(s) ou octets."""
    from pypdf import PdfReader

    if isinstance(source, (bytes, bytearray)):
        flux = io.BytesIO(source)
    elif str(source).startswith("http"):
        import requests
        r = requests.get(source, timeout=60)
        r.raise_for_status()
        flux = io.BytesIO(r.content)
    else:
        flux = open(source, "rb")
    lecteur = PdfReader(flux)
    return "\n".join((p.extract_text() or "") for p in lecteur.pages)


def rubriques(texte):
    """Découpe le texte en rubriques 1..16.
    Deux styles d'intitulés : « RUBRIQUE 2 : … » / « SECTION 2 » et « 2.  TITRE EN MAJUSCULES ».
    On exige la suite 1, 2, 3… pour ignorer les listes numérotées et les « (suite) »."""
    motif = re.compile(
        r"(?m)^[ \t]*(?:(?:RUBRIQUE|SECTION|Rubrique|Section)[ \t]*(\d{1,2})\b"
        r"|(\d{1,2})[ \t]*[.)][ \t]+(?=[A-ZÉÈÀÂÊÎÔÛÇ]{3}))")
    reperes, dernier = [], 0
    for m in motif.finditer(texte):
        n = int(m.group(1) or m.group(2))
        if n == dernier + 1 or (dernier < n <= dernier + 2 and n <= 16 and dernier >= 1):
            reperes.append((n, m.start()))
            dernier = n
    res = {}
    for i, (num, debut) in enumerate(reperes):
        fin = reperes[i + 1][1] if i + 1 < len(reperes) else len(texte)
        res[num] = texte[debut:fin]
    return res


# ---------------------------------------------------------- règles d'extraction
RE_H = re.compile(r"\bH\s?(\d{3}[A-Za-z]{0,2})(?![A-Za-z0-9])")
RE_P = re.compile(r"\bP\s?(\d{3})(?:\s*\+\s*P?\s?(\d{3}))*")
RE_CAS = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")
RE_DATE = re.compile(
    r"(?:date\s+de\s+(?:révision|revision|la\s+version|mise\s+à\s+jour|dernière\s+mise\s+à\s+jour)|"
    r"date\s+d['’]émission|révisé\s+le|version\s+du|date)\s*:?\s*"
    r"(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(\d{4})",
    re.I)


def cas_valide(c):
    """Numéro CAS plausible : ne commence pas par 0 (numéros d'index) et clé de contrôle correcte."""
    if c.startswith("0"):
        return False
    chiffres = c.replace("-", "")
    corps, cle = chiffres[:-1], int(chiffres[-1])
    return sum(int(d) * (i + 1) for i, d in enumerate(reversed(corps))) % 10 == cle


def codes_h(texte):
    vus = []
    for m in RE_H.finditer(texte):
        c = "H" + m.group(1)
        if c not in vus:
            vus.append(c)
    return vus


def codes_p(texte):
    """Retourne les codes P, en gardant les combinaisons (P301+P330+P331)."""
    vus = []
    for m in re.finditer(r"(?<![A-Za-z0-9])P\s?\d{3}(?!\d)(?:\s*\+\s*P?\s?\d{3}(?!\d))*", texte):
        brut = re.sub(r"\s+", "", m.group(0))
        morceaux = [x for x in re.split(r"\+", brut) if x]
        code = "+".join(("P" + x.lstrip("P")) for x in morceaux)
        if code not in vus:
            vus.append(code)
    return vus


def mention(texte):
    t = texte.lower()
    m = re.search(r"mention[s]?\s+d['’]avertissement\s*:?\s*(danger|attention)", t)
    if m:
        return m.group(1).upper()
    if re.search(r"\bdanger\b", t):
        return "DANGER"
    if re.search(r"\battention\b", t):
        return "ATTENTION"
    return ""


def pictos_depuis_h(codes):
    """Déduction indicative (règles CLP) : à vérifier sur la FDS."""
    s = set()
    for c in codes:
        n = int(c[1:4])
        if 200 <= n <= 205:
            s.add("GHS01")
        elif n in (220, 221, 222, 223, 224, 225, 226, 228, 229, 230, 231, 232, 240, 241, 242, 250, 251, 252, 260, 261):
            s.add("GHS02")
        elif n in (270, 271, 272):
            s.add("GHS03")
        elif n in (280, 281):
            s.add("GHS04")
        elif n in (290, 314, 318):
            s.add("GHS05")
        elif n in (300, 301, 310, 311, 330, 331):
            s.add("GHS06")
        elif n in (302, 312, 315, 317, 319, 332, 335, 336, 420):
            s.add("GHS07")
        elif n in (304, 334, 340, 341, 350, 351, 360, 361, 362, 370, 371, 372, 373):
            s.add("GHS08")
        elif n in (400, 410, 411):
            s.add("GHS09")
    return sorted(s)


def secours_depuis_p(ps):
    """Premiers secours en clair, à partir des P3xx officiels présents dans la FDS."""
    out = []
    corr = [
        ("P305+P351+P338", "Yeux"),
        ("P303+P361+P353", "Peau"),
        ("P302+P352", "Peau"),
        ("P304+P340", "Inhalation"),
        ("P301+P330+P331", "Ingestion"),
        ("P301+P312", "Ingestion"),
    ]
    deja = set()
    for code, titre in corr:
        if code in ps and titre not in deja:
            out.append({"titre": titre, "texte": texte_p(code)})
            deja.add(titre)
    prefixes = {"P301": "Ingestion", "P302": "Peau", "P303": "Peau", "P304": "Inhalation", "P305": "Yeux"}
    for code in ps:
        titre = prefixes.get(code.split("+")[0])
        if titre and titre not in deja and texte_p(code):
            out.append({"titre": titre, "texte": texte_p(code)})
            deja.add(titre)
    return out


def epi_depuis(ps, hs):
    epi = []
    if "P280" in ps:
        epi += ["Gants de protection", "Lunettes de protection", "Blouse fermée"]
    if any(c in ps for c in ("P260", "P261", "P271", "P284")) or any(
            h in hs for h in ("H331", "H332", "H335", "H336", "H334")):
        epi.append("Hotte aspirante / bonne ventilation")
    return epi



# ------------------------------------------------ pré-remplissage depuis le texte de la FDS
_TITRES_SECOURS = [
    ("Inhalation", r"(?:en\s+cas\s+d['’]\s*)?inhalation"),
    ("Peau", r"(?:en\s+cas\s+de\s+)?contact\s+(?:avec\s+)?la\s+peau"),
    ("Yeux", r"(?:en\s+cas\s+de\s+)?contact\s+(?:avec\s+)?les\s+yeux"),
    ("Ingestion", r"(?:en\s+cas\s+d['’]\s*)?ingestion"),
]


def _phrases(txt, nmax=230):
    """Nettoie un passage de FDS et le coupe en fin de phrase (≤ nmax caractères)."""
    t = re.sub(r"Sigma-Aldrich\s*-\s*\d+\s*Page\s*\d+\s*de\s*\d+", " ", txt or "")
    t = re.sub(r"Page\s*:?\s*\d+\s*(?:/|de)\s*\d+", " ", t)
    t = re.sub(r"\.\s*:\s+", ". ", t)
    t = re.sub(r"\s+", " ", t).strip(" :-–")
    if len(t) <= nmax:
        return t
    coupe = t[:nmax]
    i = max(coupe.rfind(". "), coupe.rfind("; "))
    return (coupe[: i + 1] if i > 60 else coupe.rstrip() + "…")


def secours_depuis_rubrique4(r4):
    """Premiers secours repris de la rubrique 4 de la FDS (inhalation, peau, yeux, ingestion)."""
    if not r4:
        return []
    r4 = re.split(r"\n\s*4\.2\b|\n\s*Principaux symptômes", r4)[0]
    r4 = re.sub(r"^\s*4\.?\s*[^\n]*\n", "", r4, count=1)  # titre de rubrique
    reperes = []
    for titre, motif in _TITRES_SECOURS:
        m = re.search(r"(?im)^[ \t]*[-–•]?[ \t]*" + motif + r"\b[ \t]*:?", r4)
        if m:
            reperes.append((m.start(), m.end(), titre))
    reperes.sort()
    out = {}
    for i, (debut, fin_titre, titre) in enumerate(reperes):
        fin = reperes[i + 1][0] if i + 1 < len(reperes) else len(r4)
        texte = _phrases(r4[fin_titre:fin])
        if len(texte) > 15:
            out[titre] = texte
    ordre = ["Yeux", "Peau", "Inhalation", "Ingestion"]
    return [{"titre": t, "texte": out[t]} for t in ordre if t in out]


def incompatibilites_depuis_rubrique10(r10):
    """« Matières incompatibles / à éviter » de la rubrique 10, telles qu'écrites dans la FDS."""
    if not r10:
        return ""
    m = re.search(r"(?is)mati[èe]res?\s+(?:incompatibles?|à\s+éviter)\s*:?\s*(.+?)"
                  r"(?=\n\s*(?:10\.\d|réactions?\s+dangereuses?|produits?\s+de\s+décomposition|polym[ée]risation)|$)", r10)
    if not m:
        return ""
    t = _phrases(m.group(1), 300)
    return "" if re.match(r"(?i)donn[ée]e\s+non\s+disponible", t) else t


def extrait_court(texte, nmax=1600):
    t = re.sub(r"[ \t]+", " ", texte or "")
    t = re.sub(r"\n{2,}", "\n", t).strip()
    return t[:nmax] + ("…" if len(t) > nmax else "")


# ---------------------------------------------------------------- principal
def extraire(source, nom_produit=""):
    """Analyse une FDS (chemin, URL ou octets) et renvoie un dict prêt pour fds_synthese."""
    texte = texte_pdf(source)
    rub = rubriques(texte)
    r2 = rub.get(2, texte)
    r3 = rub.get(3, "")
    r1 = rub.get(1, "")

    hs = codes_h(r2)
    ps = codes_p(r2)
    cas, eau = [], False
    for c in RE_CAS.findall(r3 or r1 or texte[:4000]):
        if not cas_valide(c):
            continue
        if c == "7732-18-5":
            eau = True
            continue
        if c not in cas:
            cas.append(c)
    notes_cas = []
    if eau and not cas:
        notes_cas.append("Seul le CAS de l'eau (7732-18-5) figure dans la FDS : renseigner le CAS du soluté à la main")
    m = RE_DATE.search(texte)
    date = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None
    conc = re.search(r"(\d{1,3}(?:[.,]\d+)?)\s*%", nom_produit or "")

    inconnus = [c for c in hs if c not in H_TEXTES] + [c for c in ps if not texte_p(c)]
    return {
        "mention": mention(r2),
        "mentions_h": [{"code": c, "texte": texte_h(c)} for c in hs],
        "mentions_p": [{"code": c, "texte": texte_p(c)} for c in ps],
        "pictos": pictos_depuis_h(hs),
        "cas": cas[0] if cas else "",
        "cas_tous": cas,
        "concentration": f"≈ {conc.group(1)} %" if conc else "",
        "fds_date": date,
        "premiers_secours": secours_depuis_rubrique4(rub.get(4)) or secours_depuis_p(ps),
        "incompatibilites": incompatibilites_depuis_rubrique10(rub.get(10)),
        "epi": epi_depuis(ps, hs),
        "extraits": {n: extrait_court(rub.get(n, "")) for n in (4, 6, 7, 8, 10, 13)},
        "avertissements": notes_cas
        + (["Codes sans libellé dans clp_textes.py : " + ", ".join(inconnus)] if inconnus else [])
        + ([] if rub.get(2) else ["Rubrique 2 introuvable : codes lus dans tout le document, à vérifier"])
        + (["Aucun code H trouvé : produit non classé dangereux, ou FDS mal lue (à vérifier sur le PDF)"] if not hs else []),
    }


def vers_ligne(art, res):
    """Convertit le résultat en ligne fds_synthese (brouillon)."""
    return {
        "article_id": art["id"],
        "nom_affichage": re.sub(r"\s*\d+\s*%.*$", "", art["nom"]).strip() or art["nom"],
        "cas": res["cas"] or art.get("numero_cas"),
        "concentration": res["concentration"],
        "mention": res["mention"] or None,
        "pictos": res["pictos"],
        "mentions_h": res["mentions_h"],
        "mentions_p": res["mentions_p"],
        "epi": res["epi"],
        "premiers_secours": res["premiers_secours"],
        "incompatibilites": res.get("incompatibilites") or None,
        "fds_source_url": art.get("fds_path"),
        "fds_date": res["fds_date"],
        "statut": "brouillon",
    }


def _aplatir(d, prefixe=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _aplatir(v, f"{prefixe}{k}.")
        else:
            yield f"{prefixe}{k}", v


def _fichiers_possibles():
    ici = os.path.dirname(os.path.abspath(__file__))
    dossiers = [os.getcwd(), ici, os.path.expanduser("~")]
    for d in dossiers:
        yield os.path.join(d, ".streamlit", "secrets.toml")
    yield os.path.join(ici, "streamlit", "secrets.toml")  # dossier sans point
    for d in dossiers:
        yield os.path.join(d, ".env")


def _lire_fichier(chemin):
    """Retourne un dict {nom: valeur} à plat, ou {}."""
    try:
        if chemin.endswith(".toml"):
            import tomllib
            with open(chemin, "rb") as fh:
                return dict(_aplatir(tomllib.load(fh)))
        res = {}
        with open(chemin, encoding="utf-8") as fh:
            for ligne in fh:
                if "=" in ligne and not ligne.lstrip().startswith("#"):
                    k, v = ligne.split("=", 1)
                    res[k.strip()] = v.strip().strip('"').strip("'")
        return res
    except Exception:
        return {}


def _identifiants():
    """URL et clé Supabase : variables d'environnement, sinon fichiers de secrets de l'appli."""
    url, cle = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if url and cle:
        return url, cle
    trouves = []
    for chemin in _fichiers_possibles():
        if not os.path.exists(chemin):
            continue
        trouves.append(chemin)
        champs = {k: str(v) for k, v in _lire_fichier(chemin).items() if isinstance(v, str)}
        u = next((v for v in champs.values() if v.startswith("https://") and "supabase.co" in v), None)
        # clé : on préfère les noms « service/secret », sinon tout nom contenant « key »
        noms = [k for k in champs if "key" in k.lower() or "secret" in k.lower() or "service" in k.lower()]
        noms.sort(key=lambda k: 0 if ("service" in k.lower() or "secret" in k.lower()) else 1)
        noms = [k for k in noms if len(champs[k]) > 30]
        if u and noms:
            print(f"Identifiants lus dans {chemin} (clé : « {noms[0]} »)")
            return u, champs[noms[0]]
    sys.exit(
        "Identifiants Supabase introuvables.\n"
        + ("Fichiers vus mais inutilisables : " + ", ".join(trouves) + "\n" if trouves else "Aucun fichier de secrets trouvé.\n")
        + "Solution : définis-les dans ce terminal (PowerShell) :\n"
        '  $env:SUPABASE_URL = "https://xxxx.supabase.co"\n'
        '  $env:SUPABASE_KEY = "la même clé que celle de ton appli"'
    )


def _client():
    from supabase import create_client
    url, cle = _identifiants()
    return create_client(url, cle)


def traiter_article(cli, art):
    res = extraire(art["fds_path"], art["nom"])
    cli.table("fds_synthese").upsert(vers_ligne(art, res), on_conflict="article_id").execute()
    return res


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "--article":
        cli = _client()
        art = cli.table("articles").select("id,nom,numero_cas,fds_path").eq("id", int(args[1])).single().execute().data
        res = traiter_article(cli, art)
        print(art["nom"], "->", res["mention"], [x["code"] for x in res["mentions_h"]], res["avertissements"])
    elif args[0] == "--tous":
        limite = int(args[args.index("--limite") + 1]) if "--limite" in args else 5
        cli = _client()
        deja = {r["article_id"] for r in cli.table("fds_synthese").select("article_id").execute().data}
        arts = (cli.table("articles").select("id,nom,numero_cas,fds_path")
                .eq("categorie", "Produits chimiques").eq("actif", True).not_.is_("fds_path", "null")
                .order("nom").execute().data)
        print(f"Produits chimiques actifs avec une FDS : {len(arts)} | fiches déjà créées : {len(deja)}")
        if not arts:
            print("AUCUN produit lu dans la base. Cause probable : la clé du fichier secrets.toml est la clé "
                  "publique (anon / publishable) et non la clé « service_role » (ou « secret »). "
                  "Remplace-la dans .streamlit\\secrets.toml par la clé service_role.")
            sys.exit(1)
        a_faire = [a for a in arts if a["id"] not in deja]
        print(f"Produits sans fiche : {len(a_faire)} | traitement de {min(limite, len(a_faire))}")
        faits = 0
        for art in arts:
            if art["id"] in deja:
                continue
            try:
                res = traiter_article(cli, art)
                print(f"OK  {art['nom']:<45} {res['mention']:<9} H={len(res['mentions_h'])} P={len(res['mentions_p'])} {res['avertissements']}")
            except Exception as e:  # une FDS illisible ne doit pas bloquer le lot
                print(f"ERR {art['nom']}: {e}")
            faits += 1
            if faits >= limite:
                break
        print(f"Terminé : {faits} brouillon(s) traité(s).")
    else:
        import json
        r = extraire(args[0])
        print(json.dumps(r, ensure_ascii=False, indent=2))
