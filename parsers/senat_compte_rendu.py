"""Parser pour les comptes rendus intégraux du Sénat (pages HTML senat.fr)."""

import json
import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_senat_cr(url: str, html_content: str) -> dict:
    """Parse la page HTML d'un compte rendu intégral sur senat.fr.

    Args:
        url: URL de la page sur senat.fr
        html_content: contenu HTML de la page

    Returns:
        dict compatible avec le format store_compte_rendu() du collecteur
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Extraire la date de séance depuis l'URL ou le contenu
    # Patterns : /cra/s20250115/s20250115.html, /seances/s20250115.html
    date_seance = None
    date_str_match = re.search(r"s(\d{8})", url)
    if date_str_match:
        try:
            date_seance = datetime.strptime(date_str_match.group(1), "%Y%m%d")
        except ValueError:
            pass

    # Numéro de séance
    num_seance = None
    num_match = re.search(r"(\d+)(?:e|ème)?\s*séance", url + " " + (soup.title.string if soup.title else ""), re.IGNORECASE)
    if num_match:
        num_seance = int(num_match.group(1))

    # Titre / date depuis le <h1>
    h1 = soup.find("h1")
    date_seance_jour = ""
    if h1:
        h1_text = h1.get_text(strip=True)
        date_seance_jour = h1_text
        # Tenter d'extraire la date si pas trouvée dans l'URL
        if not date_seance:
            date_seance = _parse_french_date_from_text(h1_text)

    # Session
    session = _extract_session(url, date_seance)

    # Sommaire : extraire les titres des interventions / sujets
    sommaire_items = []
    # Chercher les h2/h3 qui structurent le compte rendu
    for heading in soup.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True)
        if text and len(text) > 3:
            sommaire_items.append(text)

    # Si pas de h2/h3, chercher la table des matières
    if not sommaire_items:
        toc = soup.find("div", class_="sommaire") or soup.find("ul", class_="sommaire")
        if toc:
            for li in toc.find_all("li"):
                text = li.get_text(strip=True)
                if text:
                    sommaire_items.append(text)

    # Générer le sommaire en JSON string
    sommaire = json.dumps(sommaire_items, ensure_ascii=False) if sommaire_items else None

    # État
    etat = "complet"
    page_text = soup.get_text().lower()
    if "provisoire" in page_text[:500]:
        etat = "provisoire"

    # UID — utiliser le hash de l'URL comme discriminant si pas de num_seance
    date_part = date_seance.strftime("%Y%m%d") if date_seance else _url_hash(url)
    num_part = str(num_seance) if num_seance else _url_hash(url)[:6]
    uid = f"SENATCR-{session}-{date_part}-{num_part}"

    return {
        "uid": uid,
        "seance_ref": None,
        "session_ref": session,
        "date_seance": date_seance,
        "date_seance_jour": date_seance_jour,
        "num_seance": num_seance,
        "etat": etat,
        "sommaire": sommaire,
        "url_source": url,
    }


def _extract_session(url: str, date_seance: datetime | None) -> str:
    """Extrait la session parlementaire."""
    if date_seance:
        year = date_seance.year
        # Session parlementaire : oct-sept
        if date_seance.month >= 10:
            return f"{year}-{year + 1}"
        return f"{year - 1}-{year}"
    match = re.search(r"(\d{4})-(\d{4})", url)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return "2024-2025"


def _parse_french_date_from_text(text: str) -> datetime | None:
    """Extrait une date française d'un texte libre."""
    months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4,
        "mai": 5, "juin": 6, "juillet": 7, "août": 8,
        "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    }
    match = re.search(
        r"(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})",
        text.lower(),
    )
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
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:10]
