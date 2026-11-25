"""
Bordereau récapitulatif PDF d'un ticket d'enlèvement de déchets (A4 paysage).
Document interne : il prépare et archive l'enlèvement, mais ne remplace pas le bordereau
de suivi des déchets dangereux (BSDD) émis sur Trackdéchets.
Généré dans l'appli (reportlab) et téléchargé directement : aucun passage par Supabase Storage.
"""
import glob
import io
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import database as db

HERE = os.path.dirname(os.path.abspath(__file__))
PICTOS_DIR = os.path.join(HERE, "pictos")
BLEU = colors.HexColor("#1F3864")
ROUGE = colors.HexColor("#C00000")
LIGNE = colors.HexColor("#DCE6F2")
GRIS = colors.HexColor("#595959")
FILET = colors.HexColor("#8EA9DB")
ETABLISSEMENT = "Laboratoire de sciences · Cité scolaire du Hainaut · Valenciennes"
MARGE = 12 * mm


def _fonts():
    r = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
    b = glob.glob("/usr/share/fonts/**/DejaVuSans-Bold.ttf", recursive=True)
    cands = [(r[0], b[0])] if r and b else []
    cands.append(("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"))
    for reg, bold in cands:
        if os.path.exists(reg) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("DEC", reg))
            pdfmetrics.registerFont(TTFont("DEC-B", bold))
            pdfmetrics.registerFontFamily("DEC", normal="DEC", bold="DEC-B", italic="DEC", boldItalic="DEC-B")
            return "DEC", "DEC-B"
    return "Helvetica", "Helvetica-Bold"


FN, FB = _fonts()
S_TXT = ParagraphStyle("t", fontName=FN, fontSize=8.5, leading=10.5)
S_PETIT = ParagraphStyle("p", fontName=FN, fontSize=7.5, leading=9, textColor=GRIS)
S_TETE = ParagraphStyle("h", fontName=FB, fontSize=8.5, leading=10.5, textColor=colors.white)
S_TITRE = ParagraphStyle("T", fontName=FB, fontSize=15, leading=18, textColor=BLEU)
S_SOUS = ParagraphStyle("S", fontName=FB, fontSize=10.5, leading=13, textColor=BLEU, spaceBefore=6, spaceAfter=3)


def _esc(texte):
    return (str(texte or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _fr(d):
    d = db._en_date(d)
    return d.strftime("%d/%m/%Y") if d else "—"


def _pictos(chaine, taille=6.5 * mm):
    images = []
    for morceau in str(chaine or "").split(","):
        code = morceau.strip()[:5]
        chemin = os.path.join(PICTOS_DIR, f"{code}.png")
        if code.startswith("GHS") and os.path.isfile(chemin) and code not in [c for c, _ in images]:
            images.append((code, Image(chemin, width=taille, height=taille)))
    if not images:
        return ""
    t = Table([[img for _, img in images]], colWidths=[taille + 0.6 * mm] * len(images))
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _style_tableau(nb_lignes):
    st = [("BACKGROUND", (0, 0), (-1, 0), BLEU),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.4, FILET),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    for i in range(2, nb_lignes, 2):
        st.append(("BACKGROUND", (0, i), (-1, i), LIGNE))
    return TableStyle(st)


def _pied(canvas, doc):
    canvas.saveState()
    canvas.setFont(FN, 7)
    canvas.setFillColor(GRIS)
    l, h = landscape(A4)
    canvas.drawString(MARGE, 7 * mm, f"{ETABLISSEMENT} — document interne, ne remplace pas le BSDD (Trackdéchets)")
    canvas.drawRightString(l - MARGE, 7 * mm, f"Édité le {date.today():%d/%m/%Y} — page {doc.page}")
    canvas.restoreState()


def generer_pdf_enlevement(enlevement, lignes):
    """Renvoie les octets du PDF récapitulatif d'un ticket d'enlèvement."""
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=landscape(A4), leftMargin=MARGE, rightMargin=MARGE,
                            topMargin=MARGE, bottomMargin=14 * mm,
                            title=f"Enlèvement de déchets — {enlevement.get('intitule', '')}")
    largeur = landscape(A4)[0] - 2 * MARGE
    elts = [Paragraph("Bordereau récapitulatif d'enlèvement des déchets du laboratoire", S_TITRE),
            Paragraph(ETABLISSEMENT, S_PETIT), Spacer(0, 4 * mm)]

    # --- Informations du ticket ---
    infos = [
        ["Ticket", _esc(enlevement.get("intitule")), "Statut", _esc(enlevement.get("statut"))],
        ["Ouvert le", _fr(enlevement.get("date_ouverture")), "Enlèvement prévu le", _fr(enlevement.get("date_prevue"))],
        ["Prestataire", _esc(enlevement.get("prestataire") or "—"), "Enlevé le", _fr(enlevement.get("date_enlevement"))],
        ["N° de BSDD (Trackdéchets)", _esc(enlevement.get("numero_bsd") or "—"), "Notes", _esc(enlevement.get("notes") or "—")],
    ]
    t = Table([[Paragraph(f"<b>{a}</b>", S_TXT), Paragraph(b, S_TXT), Paragraph(f"<b>{c}</b>", S_TXT), Paragraph(d, S_TXT)]
               for a, b, c, d in infos], colWidths=[45 * mm, largeur / 2 - 45 * mm, 40 * mm, largeur / 2 - 40 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, FILET), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("BACKGROUND", (0, 0), (0, -1), LIGNE), ("BACKGROUND", (2, 0), (2, -1), LIGNE)]))
    elts += [t, Spacer(0, 3 * mm)]

    # --- Récapitulatif par catégorie ---
    elts.append(Paragraph("Récapitulatif par catégorie", S_SOUS))
    par_cat = {}
    for l in lignes:
        par_cat.setdefault((l["categorie"], l.get("code_dechet") or ""), []).append(l)
    rec = [[Paragraph(x, S_TETE) for x in ("Catégorie", "Code déchet", "Entrées", "Contenants", "Quantité totale")]]
    for (cat, code), ls in sorted(par_cat.items()):
        rec.append([Paragraph(_esc(cat), S_TXT), Paragraph(_esc(code or "à préciser"), S_TXT), str(len(ls)),
                    str(sum(int(l.get("nb_contenants") or 0) for l in ls)),
                    Paragraph(db.texte_totaux(db.totaux_dechets(ls)), S_TXT)])
    rec.append([Paragraph("<b>Total</b>", S_TXT), "", str(len(lignes)),
                str(sum(int(l.get("nb_contenants") or 0) for l in lignes)),
                Paragraph(f"<b>{db.texte_totaux(db.totaux_dechets(lignes))}</b>", S_TXT)])
    t = Table(rec, colWidths=[85 * mm, 35 * mm, 25 * mm, 30 * mm, largeur - 175 * mm], repeatRows=1)
    t.setStyle(_style_tableau(len(rec)))
    elts += [t, Spacer(0, 3 * mm)]

    # --- Détail ---
    elts.append(Paragraph("Détail des entrées", S_SOUS))
    entetes = ("N°", "Ajouté le", "Catégorie", "Désignation / composition", "Code", "Contenant", "Quantité",
               "État", "Dangers", "Origine / remarques")
    det = [[Paragraph(x, S_TETE) for x in entetes]]
    for i, l in enumerate(lignes, 1):
        q = l.get("quantite")
        qte = f"{db.formater_quantite(q)} {l.get('unite') or ''}" if q not in (None, "") else "—"
        cont = f"{int(l.get('nb_contenants') or 1)} × {l.get('contenant') or '?'}"
        remarques = " — ".join(x for x in (l.get("origine"), l.get("notes")) if x)
        det.append([str(i), _fr(l.get("date_ajout")), Paragraph(_esc(l["categorie"]), S_TXT),
                    Paragraph(_esc(l["designation"]), S_TXT), Paragraph(_esc(l.get("code_dechet") or ""), S_TXT),
                    Paragraph(_esc(cont), S_TXT), Paragraph(_esc(qte), S_TXT), Paragraph(_esc(l.get("etat_physique") or ""), S_TXT),
                    _pictos(l.get("pictogrammes")), Paragraph(_esc(remarques), S_PETIT)])
    if len(det) == 1:
        det.append(["", "", Paragraph("Aucune entrée", S_TXT), "", "", "", "", "", "", ""])
    larg = [9, 21, 36, 56, 20, 28, 20, 17, 34]
    larg = [x * mm for x in larg] + [largeur - sum(larg) * mm]
    t = Table(det, colWidths=larg, repeatRows=1)
    t.setStyle(_style_tableau(len(det)))
    elts += [t, Spacer(0, 6 * mm)]

    # --- Signatures ---
    sig = Table([[Paragraph("<b>Remis par</b> (nom, fonction, date, signature)", S_TXT),
                  Paragraph("<b>Pris en charge par le prestataire</b> (nom, date, signature)", S_TXT)],
                 ["", ""]], colWidths=[largeur / 2] * 2, rowHeights=[None, 18 * mm])
    sig.setStyle(TableStyle([("BOX", (0, 0), (0, -1), 0.6, BLEU), ("BOX", (1, 0), (1, -1), 0.6, BLEU),
                             ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elts.append(sig)
    elts.append(Spacer(0, 2 * mm))
    elts.append(Paragraph("Codes déchets : liste européenne des déchets (art. R541-8 du code de l'environnement) ; "
                          "l'astérisque signale un déchet dangereux. Le code retenu sur le BSDD par le prestataire fait foi.",
                          ParagraphStyle("n", parent=S_PETIT, textColor=ROUGE)))
    doc.build(elts, onFirstPage=_pied, onLaterPages=_pied)
    return tampon.getvalue()
