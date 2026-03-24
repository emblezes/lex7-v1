"""Parser pour les réunions XML de l'Assemblée nationale."""

import json

from legix.parsers.common import find, findall, findtext, parse_bool, parse_datetime, parse_xml


def parse_reunion(filepath: str) -> dict:
    root = parse_xml(filepath)

    # Lieu
    lieu_el = find(root, "lieu")
    lieu = findtext(lieu_el, "libelleLong") if lieu_el is not None else ""

    # Cycle de vie
    cycle = find(root, "cycleDeVie")
    etat = findtext(cycle, "etat") if cycle is not None else ""

    # Ordre du jour — prendre convocationODJ en priorité, sinon resumeODJ
    odj_items = []
    odj_el = find(root, "ODJ")
    if odj_el is not None:
        for section_name in ["convocationODJ", "resumeODJ"]:
            section = find(odj_el, section_name)
            if section is not None:
                items = findall(odj_el, f"{section_name}/item")
                odj_items = [item.text.strip() for item in items if item.text]
                if odj_items:
                    break

    return {
        "uid": findtext(root, "uid"),
        "date_debut": parse_datetime(findtext(root, "timeStampDebut")),
        "lieu": lieu,
        "organe_ref": findtext(root, "organeReuniRef"),
        "etat": etat,
        "ouverture_presse": parse_bool(findtext(root, "ouverturePresse")),
        "captation_video": parse_bool(findtext(root, "captationVideo")),
        "visioconference": parse_bool(findtext(root, "visioConference")),
        "odj": json.dumps(odj_items, ensure_ascii=False),
        "format_reunion": findtext(root, "formatReunion"),
    }
