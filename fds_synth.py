#!/usr/bin/env python3
"""Générateur de FDS synthétique A4 (une fiche par produit chimique).

Utilisation en ligne de commande :
    python fds_synth.py demo sortie.pdf          # fiche d'exemple (HCl)
    python fds_synth.py json fiche.json sortie.pdf

Utilisation depuis l'appli :
    from fds_synth import fiche_depuis_ligne, generer_pdf
    pdf_bytes = generer_pdf(fiche_depuis_ligne(row_supabase))
"""
import glob
import io
import json
import os
import sys

import qrcode
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from clp_textes import texte_h, texte_p

HERE = os.path.dirname(os.path.abspath(__file__))
PICTOS_DIR = os.path.join(HERE, "pictos")

# Numéro du centre antipoison (modifiable via la variable FDS_ANTIPOISON).
ANTIPOISON = os.environ.get("FDS_ANTIPOISON", "08 00 59 59 59")

# ---------------------------------------------------------------- polices
_regular = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
_bold = glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)
if _regular and _bold:
    pdfmetrics.registerFont(TTFont("F", _regular[0]))
    pdfmetrics.registerFont(TTFont("FB", _bold[0]))
    registerFontFamily("F", normal="F", bold="FB", italic="F", boldItalic="FB")
    FONT, FONTB = "F", "FB"
else:  # Helvetica gère les accents français courants
    FONT, FONTB = "Helvetica", "Helvetica-Bold"

RED = HexColor("#D0021B")
DARK = HexColor("#222222")
GREY = HexColor("#F2F2F2")

# ------------------------------------------------------------ fiche d'exemple
FICHE_DEMO = {
    "nom": "Acide chlorhydrique",
    "formule": "HCl (aq)",
    "cas": "7647-01-0",
    "concentration": "≈ 37 % (solution concentrée)",
    "mention": "DANGER",
    "pictos": ["GHS05", "GHS07"],
    "h": ["H290", "H314", "H335"],
    "p": ["P234", "P260", "P264", "P271", "P280", "P301+P330+P331",
          "P303+P361+P353", "P304+P340", "P305+P351+P338", "P310", "P390",
          "P403+P233", "P405", "P501"],
    "epi": ["Lunettes de protection", "Gants (nitrile/néoprène)",
            "Blouse fermée", "Hotte aspirante"],
    "secours": [
        ("Yeux", "Rincer à l'eau 15 min, paupières écartées, puis avis médical."),
        ("Peau", "Retirer les vêtements souillés, rincer abondamment à l'eau."),
        ("Inhalation", "Air frais, repos. Si gêne persistante : appeler les secours."),
        ("Ingestion", "Rincer la bouche, NE PAS faire vomir, appeler le 15."),
    ],
    "stockage": "Armoire acides ventilée, flacon fermé, à l'écart des bases, oxydants et métaux.",
    "incompat": "Eau de Javel / oxydants (dégagement de dichlore toxique), bases, métaux, sulfures, cyanures.",
    "deversement": "Prévenir le technicien. Absorber avec un absorbant adapté, aérer. Ne pas jeter à l'évier.",
    "dechets": "Bidon « déchets acides » selon la procédure de l'établissement.",
    "fds_url": "https://example.org/fds",
    "fds_date": "JJ/MM/AAAA",
    "statut": "brouillon",
}


def fiche_depuis_ligne(row):
    """Convertit une ligne de la table fds_synthese (dict) en fiche pour le PDF."""
    secours = row.get("premiers_secours") or []
    mh = row.get("mentions_h") or []
    mp = row.get("mentions_p") or []
    date = row.get("fds_date")
    if date and "-" in str(date):
        a, m, j = str(date)[:10].split("-")
        date = f"{j}/{m}/{a}"
    return {
        "nom": row.get("nom_affichage") or "",
        "formule": row.get("formule") or "",
        "cas": row.get("cas") or "",
        "concentration": row.get("concentration") or "",
        "mention": row.get("mention") or "",
        "pictos": list(row.get("pictos") or []),
        "h": [(x["code"] if isinstance(x, dict) else x) for x in mh],
        "h_textes": {x["code"]: x.get("texte", "") for x in mh if isinstance(x, dict)},
        "p": [(x["code"] if isinstance(x, dict) else x) for x in mp],
        "p_textes": {x["code"]: x.get("texte", "") for x in mp if isinstance(x, dict)},
        "epi": list(row.get("epi") or []),
        "secours": [(s.get("titre", ""), s.get("texte", "")) for s in secours],
        "stockage": row.get("stockage") or "",
        "incompat": row.get("incompatibilites") or "",
        "deversement": row.get("deversement") or "",
        "dechets": row.get("dechets") or "",
        "fds_url": row.get("fds_source_url") or "",
        "fds_date": date or "",
        "statut": row.get("statut") or "brouillon",
    }


# ---------------------------------------------------------------- dessin
def _para(c, text, x, y, w, size=10, bold=False, leading=None):
    style = ParagraphStyle("p", fontName=FONTB if bold else FONT, fontSize=size,
                           leading=leading or size * 1.25)
    p = Paragraph(text, style)
    _, h = p.wrap(w, 1000)
    p.drawOn(c, x, y - h)
    return y - h


def _section(c, x, y, w, titre):
    c.setFillColor(DARK)
    c.rect(x, y - 6 * mm, w, 6 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONTB, 10)
    c.drawString(x + 2 * mm, y - 4.3 * mm, titre)
    return y - 6 * mm - 2 * mm


def _esc(t):
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _groupes_p(codes, textes):
    noms = {"1": "Généraux", "2": "Prévention", "3": "Intervention", "4": "Stockage", "5": "Élimination"}
    groupes = {k: [] for k in noms}
    for code in codes:
        g = code[1] if len(code) > 1 else ""
        if g in groupes:
            txt = textes.get(code) or texte_p(code)
            groupes[g].append((code, txt))
    return [(noms[k], groupes[k]) for k in noms if groupes[k]]


def generer_pdf(f, chemin=None):
    """Génère le PDF A4. Retourne les octets, et écrit dans `chemin` si fourni."""
    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Fiche synthétique — {f['nom']}")
    m = 12 * mm
    w = W - 2 * m

    # Bandeau titre
    bandeau = 32 * mm
    c.setFillColor(RED)
    c.rect(0, H - bandeau, W, bandeau, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FONTB, 24)
    c.drawString(m, H - 14 * mm, f["nom"])
    c.setFont(FONT, 11)
    c.drawString(m, H - 21 * mm, f"{f['formule']}   |   CAS {f['cas']}")
    c.drawString(m, H - 27 * mm, f"Concentration : {f['concentration']}")
    if f.get("mention"):
        c.setFont(FONTB, 22)
        c.drawRightString(W - m, H - 14 * mm, f["mention"])

    # Pictogrammes officiels (UN GHS)
    y = H - bandeau - 4 * mm
    taille = 30 * mm
    x = m
    for code in f["pictos"]:
        img = os.path.join(PICTOS_DIR, f"{code}.png")
        if os.path.exists(img):
            c.drawImage(ImageReader(img), x, y - taille, taille, taille, mask="auto")
            x += taille + 4 * mm
    y -= taille + 4 * mm

    # EPI
    y = _section(c, m, y, w, "ÉQUIPEMENTS DE PROTECTION OBLIGATOIRES")
    y = _para(c, "  •  ".join(_esc(e) for e in f["epi"]), m + 2 * mm, y, w - 4 * mm,
              size=11, bold=True)
    y -= 3 * mm

    # Mentions H
    y = _section(c, m, y, w, "DANGERS (mentions H)")
    for code in f["h"]:
        txt = f.get("h_textes", {}).get(code) or texte_h(code)
        y = _para(c, f"<b>{code}</b>  {_esc(txt)}", m + 2 * mm, y, w - 4 * mm, size=9.5)
        y -= 0.8 * mm
    y -= 2.5 * mm

    # Premiers secours
    y = _section(c, m, y, w, "PREMIERS SECOURS")
    for k, v in f["secours"]:
        y = _para(c, f"<b>{_esc(k)} :</b> {_esc(v)}", m + 2 * mm, y, w - 4 * mm, size=9.5)
        y -= 0.8 * mm
    y -= 2.5 * mm

    # Conseils de prudence (P)
    if f["p"]:
        y = _section(c, m, y, w, "CONSEILS DE PRUDENCE (mentions P)")
        for nom, items in _groupes_p(f["p"], f.get("p_textes", {})):
            txt = " ".join(f"<b>{code}</b> {_esc(t)}" for code, t in items)
            y = _para(c, f"<b>{nom.upper()}</b> — {txt}", m + 2 * mm, y, w - 4 * mm,
                      size=8.8, leading=10.6)
            y -= 1.2 * mm
        y -= 2 * mm

    # Stockage / incompatibilités
    y = _section(c, m, y, w, "STOCKAGE ET INCOMPATIBILITÉS")
    y = _para(c, f"<b>Stockage :</b> {_esc(f['stockage'])}", m + 2 * mm, y, w - 4 * mm, size=9.5)
    y -= 0.8 * mm
    y = _para(c, f"<b>À ne pas mélanger avec :</b> {_esc(f['incompat'])}", m + 2 * mm, y,
              w - 4 * mm, size=9.5)
    y -= 3.5 * mm

    # Déversement / déchets
    y = _section(c, m, y, w, "DÉVERSEMENT ET DÉCHETS")
    y = _para(c, f"<b>Déversement :</b> {_esc(f['deversement'])}", m + 2 * mm, y,
              w - 4 * mm, size=9.5)
    y -= 0.8 * mm
    y = _para(c, f"<b>Déchets :</b> {_esc(f['dechets'])}", m + 2 * mm, y, w - 4 * mm, size=9.5)

    pied_haut = 38 * mm
    if y < pied_haut:
        print(f"ATTENTION : contenu trop long pour {f['nom']} (déborde sur le pied de page)",
              file=sys.stderr)

    # Pied de page : urgences + QR
    fy = 10 * mm
    c.setFillColor(GREY)
    c.rect(m, fy, w, 26 * mm, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont(FONTB, 9.5)
    c.drawString(m + 3 * mm, fy + 19 * mm,
                 f"15 SAMU  •  18 POMPIERS  •  Centre antipoison de LILLE : {ANTIPOISON}")
    c.setFont(FONT, 8.5)
    c.drawString(m + 3 * mm, fy + 12 * mm,
                 f"FDS officielle : scanner le QR code  (version du {f['fds_date'] or '—'})")
    if f.get("statut") != "valide":
        c.setFillColor(RED)
        c.setFont(FONTB, 8.5)
        c.drawString(m + 3 * mm, fy + 5 * mm, "BROUILLON — non validé, ne pas afficher")
    else:
        c.setFillColor(DARK)
        c.setFont(FONT, 8)
        c.drawString(m + 3 * mm, fy + 5 * mm, "Fiche synthétique validée — la FDS officielle fait foi")

    if f.get("fds_url"):
        qr = qrcode.make(f["fds_url"])
        qb = io.BytesIO()
        qr.save(qb, format="PNG")
        qb.seek(0)
        c.drawImage(ImageReader(qb), W - m - 24 * mm, fy + 1 * mm, 24 * mm, 24 * mm)

    c.showPage()
    c.save()
    data = buf.getvalue()
    if chemin:
        with open(chemin, "wb") as fh:
            fh.write(data)
    return data


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "demo":
        generer_pdf(FICHE_DEMO, sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "json":
        with open(sys.argv[2], encoding="utf-8") as fh:
            generer_pdf(json.load(fh), sys.argv[3])
    else:
        print(__doc__)
