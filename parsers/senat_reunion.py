"""Parser pour les réunions/commissions du Sénat (pages HTML senat.fr)."""

import json
import re
from datetime import datetime

from bs4 import BeautifulSoup


def parse_senat_reunion(url: str, html_content: str) -> dict:
    """Parse la page HTML d'une réunion de commission sur senat.fr.

    Args:
        url: URL de la page sur senat.fr
        html_content: contenu HTML de la page

    Returns:
        dict compatible avec le format store_reunion() du collecteur
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Titre / Commission depuis le h1 ou breadcrumb
    commission = ""
    h1 = soup.find("h1")
    if h1:
        commission = h1.get_text(strip=True)

    # Chercher le nom de la commission dans le fil d'Ariane
    breadcrumb = soup.find("nav", class_="breadcrumb") or soup.find("ul", class_="breadcrumb")
    if breadcrumb:
        items = breadcrumb.find_all("li")
        for item in items:
            text = item.get_text(strip=True).lower()
            if "commission" in text or "délégation" in text:
                commission = item.get_text(strip=True)
                break

    # Date de la réunion
    date_debut = None
    page_text = soup.get_text()

    # Chercher une date dans le contenu
    date_match = re.search(
        r"(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{4})",
        page_text.lower(),
    )
    if date_match:
        date_debut = _parse_french_date(date_match.group(0))

    # Chercher aussi le format numérique
    if not date_debut:
        date_match = re.search(r"(\d{2})/(\d{2})/(\d{4})", page_text)
        if date_match:
            try:
                date_debut = datetime(
                    int(date_match.group(3)),
                    int(date_match.group(2)),
                    int(date_match.group(1)),
                )
            except ValueError:
                pass

    # Heure
    time_match = re.search(r"(\d{1,2})\s*[h:]\s*(\d{0,2})", page_text)
    if time_match and date_debut:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if 0 <= hour <= 23:
            date_debut = date_debut.replace(hour=hour, minute=minute)

    # Lieu
    lieu = "Sénat, Palais du Luxembourg"
    lieu_match = re.search(r"(?:salle|lieu)\s*:\s*(.+?)(?:\n|<|$)", page_text, re.IGNORECASE)
    if lieu_match:
        lieu = lieu_match.group(1).strip()

    # Ordre du jour
    odj_items = []
    # Chercher les items d'ordre du jour dans les listes
    odj_section = soup.find(string=re.compile(r"ordre du jour", re.IGNORECASE))
    if odj_section:
        parent = odj_section.find_parent()
        if parent:
            # Chercher la liste suivante
            next_list = parent.find_next(["ul", "ol"])
            if next_list:
                for li in next_list.find_all("li"):
                    text = li.get_text(strip=True)
                    if text:
                        odj_items.append(text)

    # Fallback: tous les li structurés de la page
    if not odj_items:
        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            if len(text) > 20 and any(
                kw in text.lower()
                for kw in ["examen", "audition", "table ronde", "rapport", "proposition", "projet"]
            ):
                odj_items.append(text)

    odj = json.dumps(odj_items, ensure_ascii=False) if odj_items else None

    # Commission ID pour l'UID
    commission_id = _commission_slug(commission)
    date_part = date_debut.strftime("%Y%m%d") if date_debut else _url_hash(url)
    uid = f"SENATRU-{commission_id}-{date_part}"

    return {
        "uid": uid,
        "date_debut": date_debut,
        "lieu": lieu,
        "organe_ref": None,  # Pas de FK vers organes AN
        "etat": "Confirmé",
        "ouverture_presse": False,
        "captation_video": False,
        "visioconference": False,
        "odj": odj,
        "format_reunion": "commission",
        "commission_nom": commission,
        "url_source": url,
    }


def _commission_slug(name: str) -> str:
    """Génère un slug court pour le nom de la commission."""
    import unicodedata
    slug = unicodedata.normalize("NFKD", name.lower())
    slug = slug.encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug[:30] if slug else "senat"


def _parse_french_date(date_str: str) -> datetime | None:
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
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:10]
