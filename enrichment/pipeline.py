"""Pipeline d'enrichissement IA — classification + résumé en 1 appel Claude.

C'est le SEUL endroit qui fait des appels Claude pour l'enrichissement.
Ne pas activer sur LegisAPI en parallèle (double coût tokens).
"""

import json
import logging

import anthropic

from legix.core.config import settings
from legix.core.models import Amendement, CompteRendu, Reunion, Texte

logger = logging.getLogger(__name__)

THEMES = [
    "santé",
    "énergie",
    "numérique",
    "sécurité / défense",
    "agriculture / alimentation",
    "environnement / climat",
    "économie / finances",
    "éducation / recherche",
    "justice",
    "transports",
    "logement / urbanisme",
    "travail / emploi",
    "culture / médias",
    "outre-mer",
    "institutions / constitution",
    "affaires étrangères",
    "immigration",
]

COMBINED_SYSTEM = f"""Tu es un analyste parlementaire français expert.
Tu dois effectuer DEUX tâches sur le document fourni :

1. CLASSIFIER le document parmi ces thèmes (1 à 3 thèmes) :
{chr(10).join(f'- {t}' for t in THEMES)}

2. RÉSUMER le document en 1-2 phrases, en français clair, sans jargon.

Réponds UNIQUEMENT en JSON, avec ce format exact :
{{"themes": ["thème1", "thème2"], "resume": "Le résumé ici."}}"""

# Prompt enrichi pour la presse et les regulateurs — extraction d'entites en plus
PRESS_SYSTEM = f"""Tu es un analyste d'intelligence reglementaire.
Tu dois effectuer TROIS tâches sur l'article fourni :

1. CLASSIFIER parmi ces thèmes (1 à 3 thèmes) :
{chr(10).join(f'- {t}' for t in THEMES)}

2. RÉSUMER en 1-2 phrases.

3. EXTRAIRE les entités mentionnées :
   - parlementaires : noms de deputes, senateurs, eurodeputes mentionnes
   - entreprises : noms d'entreprises ou secteurs mentionnes
   - textes_loi : references a des lois, decrets, reglements, directives mentionnes

Réponds UNIQUEMENT en JSON :
{{"themes": ["thème1"], "resume": "...", "parlementaires": ["nom1"], "entreprises": ["nom1"], "textes_loi": ["ref1"]}}
Si aucune entite, laisser les listes vides."""

DOC_TYPE_LABELS = {
    "amendement": "amendement parlementaire",
    "texte": "texte législatif",
    "reunion": "réunion de commission parlementaire",
    "compte_rendu": "compte rendu de séance",
    "regulateur": "publication d'un regulateur francais",
    "presse": "article de presse specialisee",
    "eurlex": "texte legislatif europeen",
}


def classify_and_summarize(text: str, doc_type: str) -> dict:
    """Classifie et résume en un seul appel API."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    truncated = text[:4000]
    label = DOC_TYPE_LABELS.get(doc_type, "document parlementaire")

    # Prompt enrichi pour presse/regulateurs (extraction d'entites)
    use_press_prompt = doc_type in ("presse", "regulateur")
    system = PRESS_SYSTEM if use_press_prompt else COMBINED_SYSTEM
    max_tokens = 500 if use_press_prompt else 300

    response = client.messages.create(
        model=settings.enrichment_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": f"Analyse ce {label} :\n\n{truncated}"}],
    )

    try:
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)
        themes = [t for t in result.get("themes", []) if t in THEMES]
        resume = result.get("resume", "").strip()
        out = {"themes": themes, "resume": resume}
        # Entites extraites (presse/regulateurs)
        if use_press_prompt:
            out["parlementaires"] = result.get("parlementaires", [])
            out["entreprises"] = result.get("entreprises", [])
            out["textes_loi"] = result.get("textes_loi", [])
        return out
    except (json.JSONDecodeError, IndexError, KeyError):
        return {"themes": [], "resume": ""}


def extract_text(obj) -> tuple[str, str]:
    """Extrait le texte pertinent d'un objet DB pour l'enrichissement."""
    if isinstance(obj, Amendement):
        parts = []
        if obj.numero:
            parts.append(f"Amendement n°{obj.numero}")
        if obj.expose_sommaire:
            parts.append(obj.expose_sommaire)
        if obj.dispositif:
            parts.append(f"Dispositif : {obj.dispositif}")
        if obj.article_vise:
            parts.append(f"Article visé : {obj.article_vise}")
        if not obj.expose_sommaire and not obj.dispositif:
            return "", "amendement"
        return "\n".join(parts), "amendement"

    elif isinstance(obj, Texte):
        parts = []
        if obj.titre:
            parts.append(obj.titre)
        if obj.denomination:
            parts.append(f"Type : {obj.denomination}")
        if obj.titre_court:
            parts.append(f"Titre court : {obj.titre_court}")
        return "\n".join(parts), "texte"

    elif isinstance(obj, Reunion):
        parts = []
        if obj.odj:
            try:
                odj_items = json.loads(obj.odj)
                parts.append("Ordre du jour :\n" + "\n".join(f"- {item}" for item in odj_items))
            except (json.JSONDecodeError, TypeError):
                parts.append(obj.odj)
        return "\n".join(parts), "reunion"

    elif isinstance(obj, CompteRendu):
        parts = []
        if obj.sommaire:
            try:
                sujets = json.loads(obj.sommaire)
                parts.append("Sujets abordés :\n" + "\n".join(f"- {s}" for s in sujets))
            except (json.JSONDecodeError, TypeError):
                parts.append(obj.sommaire)
        if obj.date_seance_jour:
            parts.append(f"Séance du {obj.date_seance_jour}")
        return "\n".join(parts), "compte_rendu"

    return "", "amendement"


def extract_text_multi_source(obj) -> tuple[str, str]:
    """Extrait le texte d'un Texte provenant de n'importe quelle source."""
    if not isinstance(obj, Texte):
        return extract_text(obj)

    source = getattr(obj, "source", "") or ""

    if source in ("regulateur", "presse", "eurlex"):
        parts = []
        if obj.titre:
            parts.append(obj.titre)
        if obj.type_libelle:
            parts.append(f"Source : {obj.type_libelle}")
        # auteur_texte contient la description/contenu pour ces sources
        if obj.auteur_texte:
            parts.append(obj.auteur_texte)
        doc_type = source
        return "\n".join(parts), doc_type

    # Sources AN/Senat/JORF — logique standard
    return extract_text(obj)


def enrich(obj) -> dict:
    """Enrichit un objet DB avec thèmes et résumé IA (1 seul appel API).

    Pour les sources presse/regulateur, extrait aussi les entites
    (parlementaires, entreprises, textes de loi mentionnes).

    Returns:
        {"themes": "json_string", "resume_ia": "string",
         "entities": "json_string" (optionnel, pour presse/regulateur)}
    """
    # Utiliser le nouvel extracteur multi-source pour les Texte
    if isinstance(obj, Texte):
        text, doc_type = extract_text_multi_source(obj)
    else:
        text, doc_type = extract_text(obj)

    if not text.strip():
        return {"themes": None, "resume_ia": None}

    result = classify_and_summarize(text, doc_type)

    out = {
        "themes": json.dumps(result["themes"], ensure_ascii=False) if result["themes"] else None,
        "resume_ia": result["resume"] or None,
    }

    # Stocker les entites extraites dans le champ auteur_texte (JSON)
    # pour presse/regulateur — on reutilise ce champ comme metadata
    if doc_type in ("presse", "regulateur"):
        entities = {
            "parlementaires": result.get("parlementaires", []),
            "entreprises": result.get("entreprises", []),
            "textes_loi": result.get("textes_loi", []),
        }
        if any(entities.values()):
            out["entities"] = json.dumps(entities, ensure_ascii=False)

    return out
