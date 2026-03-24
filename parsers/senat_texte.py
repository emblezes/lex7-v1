"""Parser pour les textes législatifs du Sénat (pages HTML senat.fr)."""

import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_senat_texte(url: str, html_content: str) -> dict:
    """Parse la page HTML d'un texte législatif sur senat.fr.

    Args:
        url: URL de la page sur senat.fr
        html_content: contenu HTML de la page

    Returns:
        dict compatible avec le format store_texte() du collecteur
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Extraire le numéro du texte depuis l'URL
    # Patterns : /leg/ppl24-123.html, /leg/pjl24-456.html, /leg/tas24-789.html
    numero = ""
    numero_match = re.search(r"/leg/\w+(\d{2}-\d+)", url)
    if numero_match:
        numero = numero_match.group(1)
    else:
        # Fallback: chercher un numéro dans l'URL
        num_match = re.search(r"(\d{2,4}-\d+)", url)
        if num_match:
            numero = num_match.group(1)

    # Déterminer le type de texte depuis l'URL
    type_code = "SENAT"
    type_libelle = "Texte du Sénat"
    denomination = "Texte"
    if "/ppl" in url.lower():
        type_code = "PPL"
        type_libelle = "Proposition de loi"
        denomination = "Proposition de loi"
    elif "/pjl" in url.lower():
        type_code = "PJL"
        type_libelle = "Projet de loi"
        denomination = "Projet de loi"
    elif "/tas" in url.lower():
        type_code = "TAS"
        type_libelle = "Texte adopté"
        denomination = "Texte adopté"

    # Extraire la session depuis l'URL ou le numéro (ex: "24-123" → session 2024-2025)
    session = _extract_session(url, numero)

    # Titre — <h1> dans le contenu principal
    titre = ""
    h1 = soup.find("h1")
    if h1:
        titre = h1.get_text(strip=True)

    # Fallback: <title>
    if not titre:
        title_tag = soup.find("title")
        if title_tag:
            titre = title_tag.get_text(strip=True)

    # Auteur / Date — chercher dans les métadonnées de la page
    date_depot = None
    auteur_texte = ""

    # Les pages Sénat ont souvent les infos dans des <p> ou <ul> après le h1
    content = soup.find("div", id="content") or soup.find("div", class_="content") or soup
    for p in content.find_all(["p", "li"]):
        text = p.get_text(strip=True).lower()
        # Date de dépôt
        date_match = re.search(r"(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})", text)
        if date_match and not date_depot:
            date_depot = _parse_french_date(date_match.group(0))
        # Auteur
        if "déposé" in text and "par" in text:
            auteur_match = re.search(r"par\s+(?:m\.|mme|mm\.)\s+(.+?)(?:,|\.|$)", text, re.IGNORECASE)
            if auteur_match:
                auteur_texte = auteur_match.group(1).strip().title()

    # Générer l'UID
    uid = f"SENATTXT-{session}-{numero}" if numero else f"SENATTXT-{session}-{_url_hash(url)}"

    return {
        "uid": uid,
        "legislature": None,  # Le Sénat fonctionne par session, pas par législature
        "denomination": denomination,
        "titre": titre,
        "titre_court": titre[:120] if titre else "",
        "type_code": type_code,
        "type_libelle": type_libelle,
        "date_depot": date_depot,
        "date_publication": date_depot,
        "dossier_ref": None,
        "organe_ref": None,
        "auteurs_refs": [],  # Les acteurs Sénat ne sont pas dans la même table
        "auteur_texte": auteur_texte,  # Stocké en texte libre
        "url_source": url,
    }


def _extract_session(url: str, numero: str) -> str:
    """Extrait la session parlementaire depuis l'URL ou le numéro."""
    # Pattern numéro : "24-123" → année = 2024
    if numero:
        match = re.match(r"(\d{2})-", numero)
        if match:
            year_short = int(match.group(1))
            year = 2000 + year_short
            return f"{year}-{year + 1}"
    # Chercher dans l'URL
    match = re.search(r"(\d{4})-(\d{4})", url)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return "2024-2025"


def _parse_french_date(date_str: str) -> datetime | None:
    """Parse une date française (ex: '15 janvier 2025')."""
    months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    }
    match = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", date_str.strip().lower())
    if not match:
        return None
    day, month_str, year = match.groups()
    month = months.get(month_str)
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day))
    except ValueError:
        return None


def _url_hash(url: str) -> str:
    """Génère un identifiant court à partir d'une URL."""
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:10]
