"""Parser pour les amendements XML de l'Assemblée nationale."""

from legix.parsers.common import find, findall, findtext, parse_datetime, parse_xml


def parse_amendement(filepath: str) -> dict:
    root = parse_xml(filepath)

    # Identification
    uid = findtext(root, "uid")
    legislature = findtext(root, "legislature")

    # Numéro
    numero_raw = findtext(root, "numero")
    numero = findtext(root, "numAmend") or numero_raw

    # Identifiant du texte visé
    texte_ref = findtext(root, "texteLegislatifRef")

    # Auteur
    signataires = find(root, "signataires")
    auteur_ref = ""
    auteur_type = ""
    groupe_ref = ""
    cosignataires_refs = []
    if signataires is not None:
        auteur_el = find(signataires, "auteur")
        if auteur_el is not None:
            auteur_ref = findtext(auteur_el, "acteurRef")
            auteur_type = findtext(auteur_el, "typeAuteur")
            groupe_ref = findtext(auteur_el, "groupePolitiqueRef")

        for cosig in findall(signataires, "cosignataires/cosignataire"):
            ref = findtext(cosig, "acteurRef") if hasattr(cosig, "findtext") else ""
            if not ref:
                ref_el = cosig.findtext(f"{{{root.nsmap.get(None, '')}}}" + "acteurRef") if cosig.nsmap else ""
            if not ref:
                # Essai direct
                from legix.parsers.common import tag
                ref = cosig.findtext(tag("acteurRef")) or ""
            if ref:
                cosignataires_refs.append(ref)

    # Article visé
    article_vise = findtext(root, "pointeurFragmentTexte/division/articleDesignationCourte")
    article_type = findtext(root, "pointeurFragmentTexte/division/type")
    alinea = findtext(root, "pointeurFragmentTexte/alinea/alineaDesignation")

    # Contenu
    corps = find(root, "corps")
    dispositif = findtext(corps, "contenuAuteur/dispositif") if corps else ""
    expose_sommaire = findtext(corps, "contenuAuteur/exposeSommaire") if corps else ""

    # Cycle de vie
    cycle = find(root, "cycleDeVie")
    etat = findtext(cycle, "etatDesTraitements/etat/libelle") if cycle else ""
    sort_el = find(cycle, "sort") if cycle else None
    sort_val = findtext(sort_el, "sortEnSeance") if sort_el is not None else ""

    return {
        "uid": uid,
        "legislature": int(legislature) if legislature else None,
        "numero": numero,
        "numero_ordre_depot": None,
        "texte_ref": texte_ref,
        "examen_ref": findtext(root, "examenRef"),
        "organe_examen": findtext(root, "organeExamen"),
        "auteur_ref": auteur_ref or None,
        "auteur_type": auteur_type,
        "groupe_ref": groupe_ref or None,
        "article_vise": article_vise,
        "article_type": article_type,
        "alinea": alinea,
        "dispositif": dispositif,
        "expose_sommaire": expose_sommaire,
        "date_depot": parse_datetime(findtext(root, "dateDepot")),
        "date_publication": parse_datetime(findtext(root, "datePublication")),
        "date_sort": parse_datetime(findtext(root, "dateSort")),
        "etat": etat,
        "sort": sort_val,
        "cosignataires_refs": cosignataires_refs,
    }
