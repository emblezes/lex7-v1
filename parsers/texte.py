"""Parser pour les textes législatifs XML de l'Assemblée nationale."""

from legix.parsers.common import find, findall, findtext, parse_datetime, parse_xml


def parse_texte(filepath: str) -> dict:
    root = parse_xml(filepath)

    uid = findtext(root, "uid")
    legislature = findtext(root, "legislature")

    # Classification
    classification = find(root, "classification")
    type_code = findtext(classification, "type/code") if classification else ""
    type_libelle = findtext(classification, "type/libelle") if classification else ""

    # Titre
    titres = find(root, "titres")
    titre = findtext(titres, "titrePrincipal") if titres else ""
    titre_court = findtext(titres, "titrePrincipalCourt") if titres else ""

    # Dénomination (Proposition de loi, Projet de loi, etc.)
    denomination = findtext(root, "denomination")

    # Dates
    cycle = find(root, "cycleDeVie")
    date_depot = parse_datetime(findtext(cycle, "dateDepot")) if cycle else None
    date_publication = parse_datetime(findtext(cycle, "datePublication")) if cycle else None

    # Références
    dossier_ref = findtext(root, "dossierRef")
    organe_ref = findtext(root, "organeRef")

    # Auteurs
    auteurs_refs = []
    auteurs_el = find(root, "auteurs")
    if auteurs_el is not None:
        for auteur in findall(root, "auteurs/auteur"):
            ref = findtext(auteur, "acteurRef")
            if ref:
                auteurs_refs.append(ref)

    return {
        "uid": uid,
        "legislature": int(legislature) if legislature else None,
        "denomination": denomination,
        "titre": titre,
        "titre_court": titre_court,
        "type_code": type_code,
        "type_libelle": type_libelle,
        "date_depot": date_depot,
        "date_publication": date_publication,
        "dossier_ref": dossier_ref,
        "organe_ref": organe_ref,
        "auteurs_refs": auteurs_refs,
    }
