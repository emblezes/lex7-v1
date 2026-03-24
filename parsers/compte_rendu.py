"""Parser pour les comptes rendus XML de l'Assemblée nationale."""

import json
from datetime import datetime

from legix.parsers.common import find, findtext, parse_xml, tag


def parse_compte_rendu(filepath: str) -> dict:
    root = parse_xml(filepath)

    meta = find(root, "metadonnees")
    date_seance_jour = findtext(meta, "dateSeanceJour") if meta is not None else ""
    num_seance = findtext(meta, "numSeance") if meta is not None else ""
    etat = findtext(meta, "etat") if meta is not None else ""

    # Date de séance (format: 20260203150000000)
    date_seance_raw = findtext(meta, "dateSeance") if meta is not None else ""
    date_seance = None
    if date_seance_raw and len(date_seance_raw) >= 14:
        try:
            date_seance = datetime.strptime(date_seance_raw[:14], "%Y%m%d%H%M%S")
        except ValueError:
            pass

    # Sommaire — extraire les intitulés des sujets abordés
    sujets = []
    if meta is not None:
        sommaire = find(meta, "sommaire")
        if sommaire is not None:
            for titre_struct in sommaire.iter(tag("titreStruct")):
                intitule = findtext(titre_struct, "intitule")
                if intitule and intitule.strip() and intitule not in sujets:
                    sujets.append(intitule.strip())

    return {
        "uid": findtext(root, "uid"),
        "seance_ref": findtext(root, "seanceRef"),
        "session_ref": findtext(root, "sessionRef"),
        "date_seance": date_seance,
        "date_seance_jour": date_seance_jour,
        "num_seance": int(num_seance) if num_seance else None,
        "etat": etat,
        "sommaire": json.dumps(sujets, ensure_ascii=False),
    }
