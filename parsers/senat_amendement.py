"""Parser pour les amendements du Sénat (format JSON senat.fr)."""

from datetime import datetime


def parse_senat_amendement(amdt_json: dict, session: str = "2024-2025") -> dict:
    """Parse un amendement Sénat depuis le JSON senat.fr.

    Le JSON des amendements Sénat a la structure :
    {
        "numero": "42",
        "rectif": 0,
        "auteur": "M. DUPONT",
        "groupe": "Les Républicains",
        "objet": "...",
        "dispositif": "...",
        "sort": "Adopté" / "Rejeté" / "Retiré" / "Non soutenu",
        "date_depot": "2025-01-15",
        "article": "Article 3",
        ...
    }

    Args:
        amdt_json: dict d'un amendement du JSON complet
        session: session parlementaire (ex: "2024-2025")

    Returns:
        dict compatible avec le format store_amendement() du collecteur
    """
    numero = str(amdt_json.get("numero", ""))
    rectif = amdt_json.get("rectif", 0)
    num_texte = str(amdt_json.get("numTexte", amdt_json.get("num_texte", "")))

    # Numéro complet avec rectificatif
    numero_display = numero
    if rectif and int(rectif) > 0:
        numero_display = f"{numero} rect. {rectif}"

    # UID unique
    uid = f"SENATAMDT-{session}-{num_texte}-{numero}"
    if rectif and int(rectif) > 0:
        uid += f"-r{rectif}"

    # Date de dépôt
    date_depot = _parse_date(amdt_json.get("date_depot") or amdt_json.get("dateDepot"))

    # Sort / état
    sort_value = amdt_json.get("sort", "")
    etat = amdt_json.get("etat", "")
    if not etat:
        if sort_value:
            etat = sort_value
        else:
            etat = "En traitement"

    # Article visé
    article = amdt_json.get("article") or amdt_json.get("subdivisionArticle", "")
    if isinstance(article, dict):
        article = article.get("titre", article.get("numero", ""))

    return {
        "uid": uid,
        "legislature": None,
        "numero": numero_display,
        "numero_ordre_depot": _safe_int(amdt_json.get("ordreDepot")),
        "texte_ref": None,  # Sera résolu par le collector si le texte est en base
        "examen_ref": None,
        "organe_examen": "Sénat",
        "auteur_ref": None,  # Pas de FK vers acteurs AN
        "auteur_type": amdt_json.get("typeAuteur", "Sénateur"),
        "groupe_ref": None,
        "article_vise": str(article),
        "article_type": amdt_json.get("typeArticle", "ARTICLE"),
        "alinea": str(amdt_json.get("alinea", "")),
        "dispositif": amdt_json.get("dispositif", ""),
        "expose_sommaire": amdt_json.get("objet", amdt_json.get("exposeSommaire", "")),
        "date_depot": date_depot,
        "date_publication": date_depot,
        "date_sort": _parse_date(amdt_json.get("date_sort") or amdt_json.get("dateSort")),
        "etat": etat,
        "sort": sort_value,
        # Métadonnées Sénat supplémentaires
        "auteur_nom": amdt_json.get("auteur", ""),
        "groupe_nom": amdt_json.get("groupe", amdt_json.get("groupePolitique", "")),
        "url_source": amdt_json.get("urlAmdt", ""),
    }


def parse_senat_amendements_batch(json_data: dict, session: str = "2024-2025") -> list[dict]:
    """Parse le jeu complet d'amendements d'un texte Sénat.

    Le JSON complet a la structure :
    {
        "amendements": [...],
        "texte": {"numero": "123", ...}
    }
    ou directement une liste d'amendements.
    """
    if isinstance(json_data, list):
        amendements = json_data
    elif isinstance(json_data, dict):
        amendements = json_data.get("amendements", json_data.get("Amendements", []))
        # Si c'est une structure avec metadata du texte
        if not amendements and "rows" in json_data:
            amendements = json_data["rows"]
    else:
        return []

    results = []
    for amdt in amendements:
        # Certains JSON wrappent chaque amendement dans un sous-dict
        if isinstance(amdt, dict) and "amendement" in amdt:
            amdt = amdt["amendement"]
        try:
            results.append(parse_senat_amendement(amdt, session))
        except (KeyError, TypeError):
            continue

    return results


def _parse_date(value) -> datetime | None:
    """Parse une date ISO ou française."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _safe_int(value) -> int | None:
    """Conversion sûre en int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
