"""Pictogrammes SGH/CLP dessinés en SVG et affichage HTML pour Streamlit."""
import base64

_SYMBOLES = {
    'GHS01': '<circle cx="44" cy="62" r="14"/><rect x="50" y="42" width="5" height="9" transform="rotate(35 52 46)"/>\n<g stroke="#000" stroke-width="3" stroke-linecap="round"><line x1="62" y1="34" x2="62" y2="26"/><line x1="62" y1="34" x2="70" y2="29"/><line x1="62" y1="34" x2="72" y2="36"/><line x1="62" y1="34" x2="55" y2="27"/><line x1="62" y1="34" x2="69" y2="42"/></g>',
    'GHS02': '<path d="M50 20 C53 34 68 40 68 58 C68 71 59 80 50 80 C41 80 32 71 32 58 C32 49 37 45 41 38 C42 45 45 48 47 48 C46 39 46 30 50 20 Z"/>',
    'GHS03': '<path d="M50 20 C52 28 61 32 61 42 C61 49 57 52 50 52 C43 52 39 49 39 42 C39 38 42 35 44 31 C45 36 46 37 48 37 C47 31 47 26 50 20 Z"/><circle cx="50" cy="66" r="11" fill="none" stroke="#000" stroke-width="5"/><rect x="30" y="82" width="40" height="4"/>',
    'GHS04': '<rect x="40" y="34" width="20" height="48" rx="10"/><rect x="45" y="24" width="10" height="12"/><rect x="40" y="22" width="20" height="4" rx="2"/>',
    'GHS05': '<g transform="rotate(35 36 34)"><rect x="30" y="18" width="12" height="26" rx="2"/></g><g transform="rotate(-35 62 32)"><rect x="56" y="16" width="12" height="26" rx="2"/></g>\n<circle cx="30" cy="54" r="2.5"/><circle cx="34" cy="62" r="2.5"/><circle cx="68" cy="50" r="2.5"/><circle cx="64" cy="58" r="2.5"/>\n<rect x="22" y="72" width="26" height="6"/><rect x="56" y="68" width="22" height="10" rx="2"/><rect x="57" y="60" width="4" height="9" rx="2"/><rect x="63" y="58" width="4" height="11" rx="2"/><rect x="69" y="59" width="4" height="10" rx="2"/><rect x="74" y="62" width="3.5" height="7" rx="1.7"/>',
    'GHS06': '<g stroke="#000" stroke-width="5" stroke-linecap="round"><line x1="29" y1="60" x2="71" y2="80"/><line x1="71" y1="60" x2="29" y2="80"/></g>\n<circle cx="28" cy="58" r="4"/><circle cx="72" cy="58" r="4"/><circle cx="28" cy="82" r="4"/><circle cx="72" cy="82" r="4"/>\n<circle cx="50" cy="40" r="15"/><rect x="42" y="50" width="16" height="12" rx="2"/>\n<circle cx="44" cy="40" r="4" fill="#fff"/><circle cx="56" cy="40" r="4" fill="#fff"/><path d="M50 46 L47 52 L53 52 Z" fill="#fff"/>\n<g stroke="#fff" stroke-width="1.6"><line x1="45" y1="56" x2="45" y2="62"/><line x1="50" y1="56" x2="50" y2="62"/><line x1="55" y1="56" x2="55" y2="62"/></g>',
    'GHS07': '<rect x="44" y="24" width="12" height="34" rx="4"/><circle cx="50" cy="70" r="7"/>',
    'GHS08': '<circle cx="50" cy="29" r="9"/><path d="M28 80 C28 54 38 44 50 44 C62 44 72 54 72 80 Z"/><polygon fill="#fff" points="50.0,51.0 52.6,58.4 60.5,58.6 54.3,63.4 56.5,70.9 50.0,66.5 43.5,70.9 45.7,63.4 39.5,58.6 47.4,58.4"/>',
    'GHS09': '<g stroke="#000" stroke-linecap="round" stroke-width="3"><line x1="32" y1="78" x2="32" y2="36"/><line x1="32" y1="56" x2="22" y2="46"/><line x1="32" y1="48" x2="42" y2="38"/><line x1="32" y1="66" x2="42" y2="58"/></g>\n<path d="M50 70 Q60 58 72 64 L80 58 L80 76 L72 70 Q60 80 50 70 Z"/><circle cx="58" cy="66" r="1.6" fill="#fff"/><rect x="20" y="80" width="60" height="3"/>',
}

_CADRE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
          '<polygon points="50,8 92,50 50,92 8,50" fill="#fff" stroke="#d6001c" stroke-width="9" stroke-linejoin="miter"/>'
          '<g fill="#000">{}</g></svg>')

LIBELLES = {
    "GHS01": "Explosif", "GHS02": "Inflammable", "GHS03": "Comburant", "GHS04": "Gaz sous pression",
    "GHS05": "Corrosif", "GHS06": "Toxique", "GHS07": "Nocif / Irritant",
    "GHS08": "Danger pour la santé", "GHS09": "Danger pour l'environnement",
}


def svg_pictogramme(code):
    return _CADRE.format(_SYMBOLES[code])


def html_pictogrammes(pictogrammes, taille=48):
    """pictogrammes : chaîne « GHS02 - Inflammable, GHS05 - Corrosif ». Renvoie une ligne d'images HTML."""
    if not pictogrammes:
        return ""
    codes = []
    for morceau in str(pictogrammes).split(","):
        code = morceau.strip()[:5]
        if code in _SYMBOLES and code not in codes:
            codes.append(code)
    imgs = []
    for code in codes:
        data = base64.b64encode(svg_pictogramme(code).encode("utf-8")).decode("ascii")
        imgs.append(f'<img src="data:image/svg+xml;base64,{data}" width="{taille}" height="{taille}" '
                    f'title="{code} - {LIBELLES[code]}" alt="{code}" style="margin-right:4px;">')
    return "".join(imgs)


def codes_pictogrammes(pictogrammes):
    """Extrait la liste des codes GHS0x (sans doublon) d'une chaîne « GHS02 - Inflammable, GHS05 - Corrosif »."""
    codes = []
    for morceau in str(pictogrammes or "").split(","):
        code = morceau.strip()[:5]
        if code in _SYMBOLES and code not in codes:
            codes.append(code)
    return codes


def afficher_pictogrammes(pictogrammes, taille=48):
    """Affiche les pictogrammes avec st.image (méthode native, valable sur toutes les versions)."""
    import streamlit as st
    codes = codes_pictogrammes(pictogrammes)
    if not codes:
        return
    st.image([svg_pictogramme(c) for c in codes], width=taille)
