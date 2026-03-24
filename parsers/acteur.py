"""Parser pour les fichiers JSON acteur (députés) du bulk AN."""

import json
from datetime import datetime


def parse_acteur(filepath: str) -> dict:
    """Parse un fichier JSON acteur et extrait les champs utiles."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    acteur = data["acteur"]

    # UID — peut être un dict {"#text": "PA794502"} ou une string
    uid_raw = acteur["uid"]
    uid = uid_raw["#text"] if isinstance(uid_raw, dict) else uid_raw

    # Etat civil
    ident = acteur["etatCivil"]["ident"]
    civilite = ident.get("civ", "")
    prenom = ident.get("prenom", "")
    nom = ident.get("nom", "")

    # Date de naissance
    date_nais_raw = acteur["etatCivil"].get("infoNaissance", {}).get("dateNais", "")
    date_naissance = None
    if date_nais_raw:
        try:
            date_naissance = datetime.strptime(date_nais_raw, "%Y-%m-%d")
        except ValueError:
            pass

    # Profession
    profession = acteur.get("profession", {}).get("libelleCourant", "")

    # Groupe politique — mandat actif avec typeOrgane == "GP"
    groupe_politique_ref = _find_groupe_politique(acteur)

    # Adresses, réseaux sociaux, contacts
    adresses = _extract_adresses(acteur)

    # Collaborateurs
    collaborateurs = _extract_collaborateurs(acteur)

    return {
        "uid": uid,
        "civilite": civilite,
        "prenom": prenom,
        "nom": nom,
        "date_naissance": date_naissance,
        "profession": profession,
        "groupe_politique_ref": groupe_politique_ref,
        "email": adresses.get("email"),
        "telephone": adresses.get("telephone"),
        "telephone_2": adresses.get("telephone_2"),
        "site_web": adresses.get("site_web"),
        "twitter": adresses.get("twitter"),
        "facebook": adresses.get("facebook"),
        "instagram": adresses.get("instagram"),
        "linkedin": adresses.get("linkedin"),
        "adresse_an": adresses.get("adresse_an"),
        "adresse_circo": adresses.get("adresse_circo"),
        "hatvp_url": adresses.get("hatvp_url"),
        "collaborateurs": collaborateurs,
    }


def _find_groupe_politique(acteur: dict) -> str | None:
    """Trouve le groupe politique actif (typeOrgane=GP, dateFin=null)."""
    mandats_data = acteur.get("mandats", {}).get("mandat", [])
    if isinstance(mandats_data, dict):
        mandats_data = [mandats_data]

    for mandat in mandats_data:
        if mandat.get("typeOrgane") == "GP" and not mandat.get("dateFin"):
            organes = mandat.get("organes", {})
            ref = organes.get("organeRef", "")
            if ref:
                return ref
    return None


def _extract_adresses(acteur: dict) -> dict:
    """Extrait contacts, adresses et réseaux sociaux."""
    result = {}
    adresses_data = acteur.get("adresses", {}).get("adresse", [])
    if isinstance(adresses_data, dict):
        adresses_data = [adresses_data]

    phone_count = 0
    for adr in adresses_data:
        type_libelle = (adr.get("typeLibelle") or "").strip()
        type_val = adr.get("type")

        val_adresse = adr.get("valElec") or ""
        if not val_adresse:
            parts = []
            for key in ("intitule", "numeroRue", "nomRue",
                        "complementAdresse", "codePostal", "ville"):
                v = adr.get(key)
                if v and str(v).strip():
                    parts.append(str(v).strip())
            val_adresse = " ".join(parts)

        if not val_adresse:
            continue

        tl = type_libelle.lower()
        if "mèl" in tl or "mel" in tl or "courriel" in tl:
            result["email"] = val_adresse
        elif "téléphone" in tl or "telephone" in tl or "fax" in tl:
            if phone_count == 0:
                result["telephone"] = val_adresse
            else:
                result["telephone_2"] = val_adresse
            phone_count += 1
        elif "site internet" in tl or "url site" in tl:
            result["site_web"] = val_adresse
        elif "twitter" in tl:
            result["twitter"] = val_adresse
        elif "facebook" in tl:
            result["facebook"] = val_adresse
        elif "instagram" in tl:
            result["instagram"] = val_adresse
        elif "linkedin" in tl:
            result["linkedin"] = val_adresse
        elif "hatvp" in tl or "déclaration" in tl:
            result["hatvp_url"] = val_adresse
        elif "adresse officielle" in tl or str(type_val) == "0":
            if not result.get("adresse_an"):
                result["adresse_an"] = val_adresse
        elif "permanence" in tl or "circonscription" in tl or str(type_val) == "2":
            if not result.get("adresse_circo"):
                result["adresse_circo"] = val_adresse

    return result


def _extract_collaborateurs(acteur: dict) -> str | None:
    """Extrait les collaborateurs et retourne une string JSON."""
    collabs_data = acteur.get("collaborateurs", {})
    if not collabs_data:
        return None

    collabs = collabs_data.get("collaborateur", [])
    if isinstance(collabs, dict):
        collabs = [collabs]

    if not collabs:
        return None

    result = []
    for c in collabs:
        nom = c.get("nom", "")
        civilite = c.get("qualite", "") or c.get("civilite", "")
        if nom:
            result.append({"nom": nom, "civilite": civilite})

    return json.dumps(result, ensure_ascii=False) if result else None
