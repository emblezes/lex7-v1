"""Parser pour les fichiers JSON organe du bulk AN."""

import json
from datetime import datetime


TYPE_LABELS = {
    "GP": "Groupe politique",
    "COMPER": "Commission permanente",
    "DELEG": "Délégation",
    "ASSEMBLEE": "Assemblée nationale",
    "MISINFO": "Mission d'information",
    "CNPE": "Commission d'enquête",
    "GE": "Groupe d'études",
    "GA": "Groupe d'amitié",
    "API": "Assemblée parlementaire internationale",
    "PARPOL": "Parti politique",
    "CMP": "Commission mixte paritaire",
    "COMNL": "Commission non législative",
    "CONFPT": "Conférence des présidents",
    "BUREAU": "Bureau",
    "ORGEXTPAam": "Organisme extra-parlementaire",
}


def parse_organe(filepath: str) -> dict:
    """Parse un fichier JSON organe et extrait les champs utiles."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    organe = data["organe"]

    uid = organe.get("uid", "")
    type_code = organe.get("codeType", "")
    libelle = organe.get("libelle", "")
    libelle_court = organe.get("libelleAbrege") or organe.get("libelleAbrev") or ""

    type_libelle = TYPE_LABELS.get(type_code, type_code)

    # Dates
    vimde = organe.get("viMoDe", {})
    date_debut = _parse_date(vimde.get("dateDebut"))
    date_fin = _parse_date(vimde.get("dateFin"))

    # Legislature
    legislature_raw = organe.get("legislature", "")
    legislature = int(legislature_raw) if legislature_raw and legislature_raw.isdigit() else None

    return {
        "uid": uid,
        "type_code": type_code,
        "type_libelle": type_libelle,
        "libelle": libelle,
        "libelle_court": libelle_court,
        "date_debut": date_debut,
        "date_fin": date_fin,
        "legislature": legislature,
    }


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None
