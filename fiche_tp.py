#!/usr/bin/env python3
"""Fiche de préparation TP normalisée (plateau scientifique, Cité scolaire du Hainaut).

La fiche est décrite par un dictionnaire (le « JSON de la fiche »), produit par le skill Claude
« fiche-tp-labo » ou reconstruit depuis la base (tables tps + tp_materiel).
Le PDF est TOUJOURS régénéré à la demande, en mémoire : il n'est jamais stocké dans Supabase.

Les fiches sont repérées par leur TITRE (unique) : pas de référence, pas de date ni de créneau,
seulement ce qui reste valable d'une année sur l'autre (le contenu du TP).

Ligne de commande :  python fiche_tp.py fiche.json sortie.pdf
Depuis l'appli    :  pdf_bytes = generer_pdf(fiche)

La charte (couleurs, polices, ordre des sections) est FIXE : ne pas la modifier fiche par fiche.
"""
import glob
import io
import json
import math
import os
import re
import sys
import unicodedata
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
PICTOS_DIR = os.path.join(HERE, "pictos")

# ---------------- CHARTE FIXE ----------------
BLEU = colors.HexColor("#1F3864")      # bandeaux, en-têtes de tableaux, titres
ROUGE = colors.HexColor("#C00000")     # sous-titre, alertes sécurité
LIGNE = colors.HexColor("#DCE6F2")     # lignes alternées
GRIS = colors.HexColor("#595959")      # textes secondaires
FILET = colors.HexColor("#8EA9DB")     # bordures fines
ETABLISSEMENT = "Laboratoire de sciences · Cité scolaire du Hainaut · Valenciennes"
MARGE = 14 * mm
LARG = A4[0] - 2 * MARGE

LIBELLES_GHS = {"GHS01": "Explosif", "GHS02": "Inflammable", "GHS03": "Comburant", "GHS04": "Gaz sous pression",
                "GHS05": "Corrosif", "GHS06": "Toxique", "GHS07": "Nocif / irritant", "GHS08": "Danger santé",
                "GHS09": "Environnement"}


def _fonts():
    """DejaVu Sans (Linux / Streamlit Cloud avec fonts-dejavu-core), sinon Arial (Windows), sinon Helvetica."""
    r = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
    b = glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)
    i = glob.glob("/usr/share/fonts/**/DejaVuSans-Oblique.ttf", recursive=True)
    cands = []
    if r and b and i:
        cands.append((r[0], b[0], i[0]))
    cands.append(("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf"))
    for reg, bold, ital in cands:
        if all(os.path.exists(p) for p in (reg, bold, ital)):
            pdfmetrics.registerFont(TTFont("FTP", reg))
            pdfmetrics.registerFont(TTFont("FTP-B", bold))
            pdfmetrics.registerFont(TTFont("FTP-I", ital))
            pdfmetrics.registerFontFamily("FTP", normal="FTP", bold="FTP-B", italic="FTP-I", boldItalic="FTP-B")
            return "FTP", "FTP-B", "FTP-I", True
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", False


FN, FB, FI, UNICODE_OK = _fonts()
CASE = "☐" if UNICODE_OK else "[ ]"
ATTENTION = "⚠" if UNICODE_OK else "!"

S = {
    "txt": ParagraphStyle("txt", fontName=FN, fontSize=9.5, leading=12.5),
    "prep": ParagraphStyle("prep", fontName=FN, fontSize=9.5, leading=15.5),
    "cell": ParagraphStyle("cell", fontName=FN, fontSize=8.8, leading=11),
    "cellc": ParagraphStyle("cellc", fontName=FN, fontSize=8.8, leading=11, alignment=TA_CENTER),
    "head": ParagraphStyle("head", fontName=FB, fontSize=8, leading=10, textColor=colors.white, alignment=TA_CENTER),
    "titre": ParagraphStyle("titre", fontName=FB, fontSize=17, leading=21, textColor=BLEU),
    "sous": ParagraphStyle("sous", fontName=FB, fontSize=11.5, leading=15, textColor=ROUGE),
    "h1": ParagraphStyle("h1", fontName=FB, fontSize=10.5, leading=13, textColor=colors.white),
    "note": ParagraphStyle("note", fontName=FI, fontSize=8, leading=10, textColor=GRIS),
    "alerte": ParagraphStyle("alerte", fontName=FB, fontSize=9.5, leading=12.5, textColor=ROUGE),
    "picto": ParagraphStyle("picto", fontName=FN, fontSize=6.5, leading=8, textColor=GRIS, alignment=TA_CENTER),
}


# ---------------- outils ----------------
def code_ghs(code):
    """'SGH05', 'GHS05', 'GHS05 - Corrosif', 'ghs5' -> 'GHS05' ; None si non reconnu."""
    m = re.search(r"(?:SGH|GHS)\s*0?([1-9])", str(code or ""), re.I)
    return f"GHS0{m.group(1)}" if m else None


def codes_ghs(liste):
    res = []
    for c in liste or []:
        k = code_ghs(c)
        if k and k not in res:
            res.append(k)
    return res


def normaliser(texte):
    """Minuscules, sans accents ni espaces superflus : sert à rapprocher une désignation d'un article."""
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(t.lower().split())


def esc(t):
    return (str(t) if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rich(t):
    """Texte simple avec **gras**, _{indice} et ^{exposant}."""
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"_\{(.+?)\}", r"<sub>\1</sub>", t)
    t = re.sub(r"\^\{(.+?)\}", r"<super>\1</super>", t)
    return t


def P(t, st="cell"):
    return Paragraph(rich(t), S[st])


def fmt(x):
    if x is None or x == "":
        return ""
    if isinstance(x, (int, float)):
        if float(x).is_integer():
            return str(int(x))
        return f"{x:.3g}".replace(".", ",")
    return str(x)


def _unite(u):
    u = (u or "").strip()
    return "" if u.lower() in ("", "unité(s)", "unite(s)", "unité", "unités", "u") else " " + u


POSTES_DEFAUT = 8   # norme du plateau scientifique


def nom_fichier(fiche):
    """titre-du-tp_vN.pdf"""
    titre = normaliser(fiche.get("titre", "fiche"))
    titre = re.sub(r"[^a-z0-9]+", "-", titre).strip("-")[:60].strip("-") or "fiche"
    return f"{titre}_v{fiche.get('version', 1)}.pdf"


# ---------------- éléments graphiques ----------------
class Losange(Flowable):
    """Pictogramme de secours (si l'image officielle manque) : losange rouge + code."""
    def __init__(self, code, size=13 * mm):
        super().__init__()
        self.code, self.s = code, size
        self.width = self.height = size

    def draw(self):
        c, s = self.canv, self.s
        p = c.beginPath()
        p.moveTo(s / 2, s); p.lineTo(s, s / 2); p.lineTo(s / 2, 0); p.lineTo(0, s / 2); p.close()
        c.setStrokeColor(ROUGE); c.setFillColor(colors.white); c.setLineWidth(1.6)
        c.drawPath(p, fill=1, stroke=1)
        c.setFillColor(colors.black); c.setFont(FB, 6.5); c.drawCentredString(s / 2, s / 2 - 2, self.code)


def picto(code, size=14 * mm):
    """Pictogramme SGH officiel (pictos/GHS0x.png) avec son libellé dessous."""
    img = None
    for ext in ("png", "PNG", "jpg", "jpeg"):
        f = os.path.join(PICTOS_DIR, f"{code}.{ext}")
        if os.path.isfile(f):
            img = Image(f, width=size, height=size)
            break
    if img is None:
        img = Losange(code, size)
    t = Table([[img], [Paragraph(esc(LIBELLES_GHS.get(code, code)), S["picto"])]], colWidths=[size + 8 * mm])
    t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def bandeau(titre):
    t = Table([[Paragraph(esc(titre).upper(), S["h1"])]], colWidths=[LARG])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLEU), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def tableau(entetes, lignes, largeurs, centrer=()):
    data = [[Paragraph(esc(h), S["head"]) for h in entetes]]
    for l in lignes:
        data.append([c if isinstance(c, Flowable) else P(c, "cellc" if i in centrer else "cell")
                     for i, c in enumerate(l)])
    t = Table(data, colWidths=[w * LARG for w in largeurs], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), BLEU), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.4, FILET), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4),
          ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    for r in range(2, len(data), 2):
        st.append(("BACKGROUND", (0, r), (-1, r), LIGNE))
    t.setStyle(TableStyle(st))
    return t


def section(titre, contenu):
    return [Spacer(1, 4 * mm), KeepTogether([bandeau(titre), Spacer(1, 2 * mm), contenu[0]])] + contenu[1:]


def volume_a_preparer(s, postes, marge):
    """Volume par poste × postes × (1 + marge), arrondi à 10 mL (50 mL au-delà de 100 mL).
    'volume_total_mL' l'emporte s'il est fourni."""
    if s.get("volume_total_mL") not in (None, ""):
        return s["volume_total_mL"]
    vp = s.get("volume_poste_mL")
    if not isinstance(vp, (int, float)):
        return ""
    brut = vp * postes * (1 + marge)
    return math.ceil(brut / 50) * 50 if brut > 100 else math.ceil(brut / 10) * 10


# ---------------- génération du PDF ----------------
def construire(d, sortie):
    """d : dictionnaire de la fiche ; sortie : chemin de fichier ou objet fichier (io.BytesIO)."""
    postes = int(d.get("postes") or POSTES_DEFAUT)
    version = d.get("version") or 1
    titre = d.get("titre") or "TP sans titre"
    story = []

    # ---- titre, sous-titre, cartouche ----
    story.append(Paragraph(rich(titre), S["titre"]))
    sous = " · ".join(x for x in [d.get("theme"), d.get("niveau"), d.get("sous_titre")] if x)
    if sous:
        story.append(Paragraph(rich(sous), S["sous"]))
    story.append(Spacer(1, 3 * mm))
    date_maj = d.get("date_maj") or date.today().strftime("%d/%m/%Y")
    info = [("Thème", d.get("theme", "")), ("Niveau", d.get("niveau", "")),
            ("Enseignant(e)", d.get("enseignant", "")), ("Durée", d.get("duree", "")),
            ("Nombre de postes", str(postes)), ("Version", f"v{version} du {date_maj}")]
    rows = [[P(f"**{info[i][0]}**"), P(info[i][1] or ""), P(f"**{info[i + 1][0]}**"), P(info[i + 1][1] or "")]
            for i in range(0, len(info), 2)]
    cart = Table(rows, colWidths=[0.2 * LARG, 0.3 * LARG, 0.2 * LARG, 0.3 * LARG])
    cart.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, FILET), ("BACKGROUND", (0, 0), (0, -1), LIGNE),
                              ("BACKGROUND", (2, 0), (2, -1), LIGNE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(cart)

    # ---- matériel par poste ----
    mp = d.get("materiel_poste") or []
    if mp:
        lignes = []
        for m in mp:
            q, u = m.get("qte", 1), _unite(m.get("unite"))
            tot = q * postes if isinstance(q, (int, float)) else ""
            lignes.append([m.get("designation", ""), m.get("caracteristiques", ""), fmt(q) + u,
                           (fmt(tot) + u) if tot != "" else "", CASE])
        story += section(f"Matériel par poste ({postes} poste{'s' if postes > 1 else ''})",
                         [tableau(["Désignation", "Caractéristiques / référence", "Qté / poste", "Total", "Prêt"],
                                  lignes, [0.34, 0.38, 0.1, 0.1, 0.08], centrer=(2, 3, 4))])

    # ---- matériel au bureau ----
    mb = d.get("materiel_bureau") or []
    if mb:
        lignes = [[m.get("designation", ""), m.get("caracteristiques", ""),
                   fmt(m.get("qte", 1)) + _unite(m.get("unite")), CASE] for m in mb]
        story += section("Matériel au bureau / paillasse professeur",
                         [tableau(["Désignation", "Caractéristiques / référence", "Qté", "Prêt"], lignes,
                                  [0.36, 0.46, 0.1, 0.08], centrer=(2, 3))])

    # ---- solutions et produits ----
    so = d.get("solutions") or []
    marge = float(d.get("marge_solutions", 0.2) or 0)
    if so:
        lignes = []
        for s in so:
            vp = s.get("volume_poste_mL")
            total = volume_a_preparer(s, postes, marge)
            lignes.append([s.get("nom", ""), s.get("concentration", ""),
                           (fmt(vp) + " mL") if vp not in (None, "") else "",
                           (fmt(total) + " mL") if total not in (None, "") else "",
                           " ".join(codes_ghs(s.get("sgh"))), s.get("conditionnement", ""), CASE])
        story += section("Solutions et produits",
                         [tableau(["Solution / produit", "Concentration", "Vol. / poste",
                                   f"Vol. à préparer (+{int(round(marge * 100))} %)", "SGH", "Conditionnement", "Prêt"],
                                  lignes, [0.24, 0.15, 0.09, 0.13, 0.10, 0.21, 0.08], centrer=(1, 2, 3, 4, 6))])

    # ---- préparation des solutions ----
    pr = d.get("preparations") or []
    if pr:
        blocs = []
        for p in pr:
            txt = f"<b>{rich(p.get('solution', ''))}</b>"
            if p.get("calcul"):
                txt += f"<br/><font color='#595959'>Calcul : {rich(p['calcul'])}</font>"
            if p.get("mode_operatoire"):
                txt += f"<br/>{rich(p['mode_operatoire'])}"
            blocs.append([Paragraph(txt, S["prep"])])
        t = Table(blocs, colWidths=[LARG])
        t.setStyle(TableStyle([("LINEBEFORE", (0, 0), (0, -1), 2.2, BLEU), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story += section("Préparation des solutions", [t])

    # ---- sécurité ----
    sec = d.get("securite") or {}
    codes = sorted(set(codes_ghs([c for s in so for c in (s.get("sgh") or [])])) | set(codes_ghs(sec.get("sgh"))))
    if sec or codes:
        contenu = []
        if codes:
            pt = Table([[picto(c) for c in codes]], hAlign="LEFT")
            pt.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
            contenu.append(pt)
        if sec.get("epi"):
            contenu.append(Paragraph(f"<b>Équipements de protection :</b> {rich(', '.join(sec['epi']))}", S["txt"]))
        for a in sec.get("consignes") or []:
            contenu.append(Paragraph(f"{ATTENTION} {rich(a)}", S["alerte"]))
        if sec.get("dechets"):
            contenu.append(Paragraph(f"<b>Déchets / élimination :</b> {rich(sec['dechets'])}", S["txt"]))
        if contenu:
            suite = []
            for c in contenu[1:]:
                suite += [Spacer(1, 1.2 * mm), c]
            story += section("Sécurité", [contenu[0]] + suite)

    # ---- remarques, vérifications, source ----
    rq = d.get("remarques") or []
    if rq:
        story += section("Remarques et points de vigilance",
                         [Paragraph("<br/>".join("• " + rich(r) for r in rq), S["txt"])])
    av = d.get("a_verifier") or []
    if av:
        story += section("À vérifier avant la séance",
                         [Paragraph("<br/>".join(f"{CASE} " + rich(r) for r in av), S["alerte"])])
    if d.get("source"):
        story += [Spacer(1, 3 * mm), Paragraph(f"Source : {rich(d['source'])}", S["note"])]

    # ---- bandeau haut + pied de page ----
    def decor(c, doc):
        c.saveState()
        w, h = A4
        c.setFillColor(BLEU); c.rect(0, h - 17 * mm, w, 17 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont(FB, 12.5); c.drawString(MARGE, h - 9.5 * mm, "FICHE DE PRÉPARATION TP")
        c.setFont(FN, 8.5); c.drawString(MARGE, h - 14 * mm, ETABLISSEMENT)
        c.setFont(FB, 10); c.drawRightString(w - MARGE, h - 11.5 * mm, d.get("discipline") or "")
        c.setFillColor(ROUGE); c.rect(0, h - 18 * mm, w, 1 * mm, fill=1, stroke=0)
        c.setStrokeColor(BLEU); c.setLineWidth(0.6); c.line(MARGE, 12 * mm, w - MARGE, 12 * mm)
        c.setFillColor(GRIS); c.setFont(FN, 7.5)
        court = titre if len(titre) <= 70 else titre[:67].rstrip() + "…"
        c.drawString(MARGE, 8 * mm, f"{court} · v{version} · fiche normalisée du plateau scientifique")
        c.restoreState()

    class NumCanvas(Canvas):
        """Ajoute « Page n / N » en pied de page."""
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            n = len(self._pages)
            for etat in self._pages:
                self.__dict__.update(etat)
                self.setFillColor(GRIS); self.setFont(FN, 7.5)
                self.drawRightString(A4[0] - MARGE, 8 * mm, f"Page {self._pageNumber} / {n}")
                super().showPage()
            super().save()

    doc = BaseDocTemplate(sortie, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE, topMargin=24 * mm,
                          bottomMargin=17 * mm, title=titre,
                          author="Laboratoire - Cité scolaire du Hainaut")
    doc.addPageTemplates([PageTemplate(id="p", onPage=decor, frames=[
        Frame(MARGE, 17 * mm, LARG, A4[1] - 41 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0,
              bottomPadding=0)])])
    doc.build(story, canvasmaker=NumCanvas)


def generer_pdf(d):
    """Renvoie le PDF de la fiche (bytes), fabriqué en mémoire."""
    buf = io.BytesIO()
    construire(d, buf)
    return buf.getvalue()


# ---------------- passage base <-> fiche ----------------
CHAMPS_TP = ["version", "theme", "enseignant", "postes", "duree"]
CHAMPS_FICHE = ["sous_titre", "solutions", "marge_solutions", "preparations", "securite", "remarques",
                "a_verifier", "source"]


def fiche_depuis_tp(tp, lignes, articles_par_id, fiche_json=None):
    """Reconstruit le dictionnaire de la fiche à partir d'une ligne de 'tps', de ses lignes 'tp_materiel'
    et du contenu jsonb 'fiche'. articles_par_id : {id (str): article}."""
    d = {"titre": tp.get("titre"), "discipline": tp.get("discipline"), "niveau": tp.get("niveau")}
    for k in CHAMPS_TP:
        if tp.get(k) not in (None, ""):
            d[k] = tp[k]
    if tp.get("date_maj"):
        a, m, j = str(tp["date_maj"])[:10].split("-")
        d["date_maj"] = f"{j}/{m}/{a}"
    for k in CHAMPS_FICHE:
        if (fiche_json or {}).get(k) not in (None, "", [], {}):
            d[k] = fiche_json[k]
    d["materiel_poste"], d["materiel_bureau"] = [], []
    for l in lignes:
        art = articles_par_id.get(str(l.get("article_id"))) if l.get("article_id") else None
        item = {"designation": (art or {}).get("nom") or l.get("libelle") or "?",
                "caracteristiques": l.get("caracteristiques") or "",
                "qte": float(l.get("quantite") or 0)}
        if item["qte"].is_integer():
            item["qte"] = int(item["qte"])
        if l.get("unite"):
            item["unite"] = l["unite"]
        if art:
            item["article_id"] = art["id"]
        (d["materiel_bureau"] if l.get("emplacement") == "bureau" else d["materiel_poste"]).append(item)
    return d


def preparer_import(d, articles):
    """Transforme le JSON d'une fiche en données pour la base.
    Renvoie (champs_tp, fiche_json, lignes) ; chaque ligne porte 'article' (dict ou None) pour l'aperçu.
    Rapprochement avec l'inventaire : 'article_id' s'il est fourni, sinon nom identique (sans accents ni casse)."""
    if not str(d.get("titre") or "").strip():
        raise ValueError("La fiche n'a pas de titre.")
    par_id = {str(a["id"]): a for a in articles if a.get("actif", True)}
    par_nom = {}
    for a in articles:
        if a.get("actif", True):
            par_nom.setdefault(normaliser(a.get("nom")), a)

    champs = {"titre": str(d["titre"]).strip(), "discipline": d.get("discipline"), "niveau": d.get("niveau")}
    for k in CHAMPS_TP:
        if d.get(k) not in (None, ""):
            champs[k] = d[k]
    champs["postes"] = int(d.get("postes") or POSTES_DEFAUT)
    champs["version"] = int(d.get("version") or 1)
    fiche_json = {k: d[k] for k in CHAMPS_FICHE if d.get(k) not in (None, "", [], {})}

    lignes = []
    for emplacement, cle in (("poste", "materiel_poste"), ("bureau", "materiel_bureau")):
        for m in d.get(cle) or []:
            art = par_id.get(str(m.get("article_id"))) if m.get("article_id") else None
            if art is None:
                art = par_nom.get(normaliser(m.get("designation")))
            q, car = m.get("qte", 1), (m.get("caracteristiques") or "").strip()
            if not isinstance(q, (int, float)):        # ex. « 1 de chaque » : on garde le texte
                car = f"{car} — {q}" if car else str(q)
                q = 1
            unite = m.get("unite") or (art.get("unite") if art else None) or "unité(s)"
            lignes.append({"emplacement": emplacement, "article": art,
                           "article_id": art["id"] if art else None,
                           "libelle": None if art else (m.get("designation") or "?"),
                           "designation": m.get("designation") or "?",
                           "caracteristiques": car or None, "quantite": float(q), "unite": unite})
    return champs, fiche_json, lignes


if __name__ == "__main__":
    src = sys.argv[1]
    fiche = json.load(open(src, encoding="utf-8"))
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".pdf"
    construire(fiche, out)
    print("PDF :", out)
