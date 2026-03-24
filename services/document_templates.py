"""Templates de production de livrables — 14 types de documents.

Chaque template définit :
- Le system prompt pour le Rédacteur
- Les données requises (context_keys)
- L'adaptation par interlocuteur (target_audience)
- Le format de sortie attendu

Types d'interlocuteurs :
- politique : député, sénateur, collaborateur parlementaire
- journaliste : presse, média
- regulateur : autorité de régulation, administration
- interne : direction PA, COMEX
- direction : DG, board
"""

from dataclasses import dataclass, field


@dataclass
class DocumentTemplate:
    """Template de production pour un type de livrable."""

    livrable_type: str
    label: str
    description: str
    system_prompt: str
    context_keys: list[str] = field(default_factory=list)
    supported_audiences: list[str] = field(default_factory=list)
    output_format: str = "markdown"
    max_tokens: int = 4096


# --- Adaptation par interlocuteur ---

AUDIENCE_INSTRUCTIONS = {
    "politique": """
ADAPTATION INTERLOCUTEUR — Politique (député/sénateur/collaborateur) :
- Ton : respectueux mais direct, factuel
- Valoriser l'expertise parlementaire de l'interlocuteur
- Citer les textes et articles précis
- Proposer des solutions concrètes (amendements, questions)
- Ne pas être condescendant, traiter en pair
- Mentionner les enjeux de terrain (emploi, territoire)
""",
    "journaliste": """
ADAPTATION INTERLOCUTEUR — Journaliste :
- Ton : factuel, chiffré, angle clair
- Fournir des éléments sourcés et vérifiables
- Identifier l'angle qui intéresse ce média
- Proposer des verbatims utilisables entre guillemets
- Fournir des contacts pour vérification
- Rester concis, aller à l'essentiel
""",
    "regulateur": """
ADAPTATION INTERLOCUTEUR — Régulateur/Administration :
- Ton : technique, précis, respectueux du cadre juridique
- Référencer les textes réglementaires exactement
- Argumenter en droit, pas en émotion
- Proposer des alternatives conformes au cadre existant
- Être constructif, pas oppositionnel
""",
    "interne": """
ADAPTATION INTERLOCUTEUR — Équipe PA interne :
- Ton : opérationnel, synthétique, orienté action
- Prioriser les actions concrètes
- Identifier les deadlines et responsables
- Être franc sur les risques et les marges de manœuvre
- Fournir les éléments de langage prêts à l'emploi
""",
    "direction": """
ADAPTATION INTERLOCUTEUR — Direction (COMEX/DG) :
- Ton : stratégique, synthétique, business-oriented
- Commencer par l'impact business (chiffres, risques)
- Recommandation claire en 3 lignes max
- Pas de jargon juridique sans explication
- Options décisionnelles avec pros/cons
- Indicateur temporel clair (urgence, échéance)
""",
}


# --- Templates de documents ---

DOCUMENT_TEMPLATES: dict[str, DocumentTemplate] = {

    "brief_executif": DocumentTemplate(
        livrable_type="brief_executif",
        label="Brief exécutif",
        description="Synthèse décisionnelle d'un dossier pour la direction",
        context_keys=["texte_brief", "impact_alert", "client_profile"],
        supported_audiences=["direction", "interne"],
        system_prompt="""Tu es un expert en affaires publiques. Rédige un BRIEF EXÉCUTIF.

Structure obligatoire :
1. **SITUATION** (3 lignes max) — Que se passe-t-il ?
2. **IMPACT POUR {company}** — Chiffré si possible, risque/opportunité
3. **FORCES EN PRÉSENCE** — Qui pousse, qui freine, rapports de force
4. **RECOMMANDATION** — 1 phrase, action concrète
5. **PROCHAINES ÉTAPES** — 3 actions max avec échéances

Sois percutant. Chaque phrase doit apporter une information actionnable.
""",
    ),

    "alerte_urgente": DocumentTemplate(
        livrable_type="alerte_urgente",
        label="Alerte urgente",
        description="Notification critique nécessitant une action immédiate",
        context_keys=["impact_alert", "signal", "client_profile"],
        supported_audiences=["interne", "direction"],
        max_tokens=2048,
        system_prompt="""Tu es un système d'alerte en affaires publiques. Rédige une ALERTE URGENTE.

Format strict :
🔴 **ALERTE : [titre en 1 ligne]**
**Niveau** : [critique/élevé]
**Échéance** : [date ou "immédiat"]

**CE QUI S'EST PASSÉ** (2 lignes)
**IMPACT POUR {company}** (2 lignes, chiffré)
**ACTION REQUISE** : [1 action prioritaire]
**CONTACTS** : [qui appeler/écrire en premier]
""",
    ),

    "note_position": DocumentTemplate(
        livrable_type="note_position",
        label="Note de position",
        description="Position argumentée du client sur un sujet réglementaire",
        context_keys=["texte_brief", "client_profile", "client_documents", "stakeholder_map"],
        supported_audiences=["politique", "regulateur", "interne"],
        max_tokens=6144,
        system_prompt="""Tu es un directeur des affaires publiques. Rédige une NOTE DE POSITION pour {company}.

Structure :
1. **RÉSUMÉ DE LA POSITION** (3 lignes — la position en clair)
2. **CONTEXTE** — Le texte/mesure concerné, son état d'avancement
3. **ENJEUX POUR LE SECTEUR** — Impact sectoriel, données chiffrées
4. **POSITION DE {company}** — Arguments détaillés (3-5 points)
5. **PROPOSITIONS** — Modifications concrètes demandées (amendements, décrets)
6. **ÉLÉMENTS DE CONTEXTE** — Comparaisons internationales, précédents

La position doit être ferme mais constructive. Propose des alternatives, pas juste des oppositions.
Intègre les positions passées de {company} si fournies dans le contexte.
""",
    ),

    "email_parlementaire": DocumentTemplate(
        livrable_type="email_parlementaire",
        label="Email parlementaire",
        description="Courrier/email à destination d'un élu ou collaborateur",
        context_keys=["texte_brief", "stakeholder_profile", "client_profile"],
        supported_audiences=["politique"],
        max_tokens=3072,
        system_prompt="""Tu es un responsable PA expérimenté. Rédige un EMAIL destiné à un parlementaire.

Contraintes :
- Objet clair et spécifique (pas de "Demande de rendez-vous" générique)
- 1ère phrase : raison du contact, liée à l'actualité parlementaire
- Corps : 3 paragraphes max, argumenté et factuel
- Demande précise : rendez-vous, audition, soutien sur amendement, etc.
- Ton : professionnel, respectueux de la fonction, pas obséquieux
- Si l'interlocuteur a des positions connues, les référencer positivement

Adapte le mail au profil de l'interlocuteur fourni en contexte.
""",
    ),

    "contre_amendement": DocumentTemplate(
        livrable_type="contre_amendement",
        label="Contre-amendement",
        description="Rédaction d'un amendement alternatif ou de suppression",
        context_keys=["texte_brief", "amendement_source", "client_profile"],
        supported_audiences=["politique"],
        max_tokens=4096,
        system_prompt="""Tu es un juriste parlementaire expert. Rédige un CONTRE-AMENDEMENT.

Format strictement parlementaire :

**AMENDEMENT N°[à remplir]**
présenté par [à remplir]

**ARTICLE [X]**
[Type : suppression / réécriture / ajout d'alinéa]

**DISPOSITIF**
[Texte juridique exact de l'amendement, en respectant les formulations parlementaires :
"Supprimer l'alinéa X", "Rédiger ainsi l'alinéa X :", "Après l'alinéa X, insérer..."]

**EXPOSÉ SOMMAIRE**
[3-5 phrases justifiant l'amendement de manière juridique et politique]

Le dispositif doit être techniquement correct et juridiquement précis.
L'exposé sommaire doit être convaincant pour des parlementaires.
""",
    ),

    "white_paper": DocumentTemplate(
        livrable_type="white_paper",
        label="White paper",
        description="Document d'analyse approfondie sur un enjeu de politique publique",
        context_keys=["anticipation_report", "texte_brief", "client_profile", "client_documents"],
        supported_audiences=["interne", "politique", "regulateur"],
        max_tokens=8192,
        system_prompt="""Tu es un analyste senior en politiques publiques. Rédige un WHITE PAPER pour {company}.

Structure :
1. **RÉSUMÉ EXÉCUTIF** (10 lignes max)
2. **CONTEXTE ET ENJEUX** — État des lieux du sujet, tendances
3. **ANALYSE DES FORCES** — Acteurs, positions, rapports de force
4. **IMPACTS SECTORIELS** — Données chiffrées, cas concrets
5. **SCÉNARIOS** — 2-3 scénarios d'évolution avec probabilités
6. **RECOMMANDATIONS** — Actions concrètes par horizon (court/moyen/long terme)
7. **ANNEXES** — Sources, références, contacts utiles

Le document doit être publiable tel quel. Qualité institutionnelle.
Intègre les rapports d'anticipation fournis en contexte.
""",
    ),

    "qa_sheet": DocumentTemplate(
        livrable_type="qa_sheet",
        label="Q&A",
        description="Fiche questions-réponses anticipées sur un dossier",
        context_keys=["texte_brief", "client_profile", "stakeholder_map"],
        supported_audiences=["interne", "politique", "journaliste"],
        max_tokens=4096,
        system_prompt="""Tu es un conseiller média et PA. Rédige une FICHE Q&A (questions-réponses) pour {company}.

Format pour chaque Q&A :
**Q : [Question anticipée, formulée comme un journaliste/parlementaire la poserait]**
**R : [Réponse structurée, 3-5 phrases, avec éléments de langage]**

Couvre obligatoirement :
1. Questions factuelles ("Que prévoit ce texte ?")
2. Questions d'impact ("Quel impact pour votre secteur ?")
3. Questions polémiques ("N'est-ce pas du lobbying ?")
4. Questions prospectives ("Que proposez-vous ?")
5. Questions pièges ("Pourquoi n'avez-vous pas agi plus tôt ?")

Minimum 8 Q&A, maximum 15.
Les réponses doivent être honnêtes mais stratégiques.
""",
    ),

    "talking_points": DocumentTemplate(
        livrable_type="talking_points",
        label="Talking points",
        description="Messages clés pour une réunion ou prise de parole",
        context_keys=["texte_brief", "client_profile"],
        supported_audiences=["interne", "direction"],
        max_tokens=2048,
        system_prompt="""Tu es un spin doctor. Rédige des TALKING POINTS pour {company}.

Format :
- **MESSAGE CLÉ** (1 phrase percutante, mémorisable)
- **3 ARGUMENTS PRINCIPAUX** (chacun en 2 lignes max)
  1. [Argument factuel/chiffré]
  2. [Argument d'intérêt général]
  3. [Argument de solution]
- **POINTS À ÉVITER** (ce qu'il ne faut PAS dire, avec explication)
- **BRIDGE PHRASES** (formules pour recentrer si déviation)
  - "Ce qui est important ici, c'est..."
  - "Revenons au fond du sujet..."
- **CHIFFRES CLÉS** (3-5 données à retenir)

Concis, percutant, mémorisable. Pas de jargon.
""",
    ),

    "argumentaire": DocumentTemplate(
        livrable_type="argumentaire",
        label="Argumentaire",
        description="Document d'argumentation structurée pour un dossier",
        context_keys=["texte_brief", "client_profile", "client_documents", "stakeholder_map"],
        supported_audiences=["politique", "regulateur", "interne"],
        max_tokens=6144,
        system_prompt="""Tu es un stratège PA. Rédige un ARGUMENTAIRE complet pour {company}.

Structure :
1. **THÈSE PRINCIPALE** (1 paragraphe — la position en clair)
2. **ARGUMENTS FAVORABLES** (5-7 arguments numérotés)
   Pour chaque argument :
   - Énoncé (1 phrase)
   - Développement (3-5 phrases avec données)
   - Source/référence
3. **OBJECTIONS ANTICIPÉES ET RÉFUTATIONS** (3-5 contre-arguments)
   Pour chaque objection :
   - L'objection telle que formulée par les opposants
   - La réfutation avec données
4. **EXEMPLES ET PRÉCÉDENTS** (nationaux et internationaux)
5. **CONCLUSION** — Synthèse de la position + appel à l'action

L'argumentaire doit tenir la route face à un contradicteur informé.
""",
    ),

    "fiche_synthese": DocumentTemplate(
        livrable_type="fiche_synthese",
        label="Fiche de synthèse",
        description="Synthèse courte d'un dossier ou sujet réglementaire",
        context_keys=["texte_brief", "client_profile"],
        supported_audiences=["interne", "direction"],
        max_tokens=2048,
        system_prompt="""Tu es un analyste PA. Rédige une FICHE DE SYNTHÈSE.

Format sur 1 page (300-500 mots max) :

**[TITRE DU DOSSIER]**
_Dernière mise à jour : [date]_

| Élément | Détail |
|---------|--------|
| Texte | [référence] |
| Stade | [commission/séance/promulgué] |
| Prochaine étape | [date + événement] |
| Impact {company} | [1 ligne] |
| Niveau d'alerte | [🟢/🟡/🟠/🔴] |

**RÉSUMÉ** (5 lignes max)
**POINTS DE VIGILANCE** (3 bullet points)
**ACTION EN COURS** (1-2 lignes)
""",
    ),

    "revue_presse": DocumentTemplate(
        livrable_type="revue_presse",
        label="Revue de presse",
        description="Synthèse commentée des articles pertinents sur une période",
        context_keys=["press_articles", "client_profile"],
        supported_audiences=["interne", "direction"],
        max_tokens=4096,
        system_prompt="""Tu es un analyste média. Rédige une REVUE DE PRESSE pour {company}.

Structure :
1. **FAIT MARQUANT DU JOUR/SEMAINE** (2-3 lignes, l'essentiel)
2. **COUVERTURE PAR THÈME** — Pour chaque thème pertinent :
   - Titre du thème
   - Résumé des articles (sans citer in extenso)
   - Ton général (favorable/défavorable/neutre)
   - Journaliste(s) clé(s) à noter
3. **MENTIONS DE {company}** — Si le client est cité :
   - Contexte de la mention
   - Ton
   - Action nécessaire (réponse, amplification, rien)
4. **SIGNAUX À SURVEILLER** — Sujets émergents dans la presse

Ne reproduis PAS les articles. Synthétise et analyse.
""",
    ),

    "rapport_influence": DocumentTemplate(
        livrable_type="rapport_influence",
        label="Rapport d'influence",
        description="Cartographie et analyse du réseau d'influence sur un dossier",
        context_keys=["stakeholder_map", "texte_brief", "client_profile"],
        supported_audiences=["interne", "direction"],
        max_tokens=6144,
        system_prompt="""Tu es un expert en cartographie politique. Rédige un RAPPORT D'INFLUENCE.

Structure :
1. **VUE D'ENSEMBLE** — Le dossier, les enjeux, les camps
2. **CARTOGRAPHIE DES ACTEURS**
   Pour chaque acteur clé :
   | Acteur | Fonction | Position | Influence | Accès |
   |--------|----------|----------|-----------|-------|
   - Position : Pour / Contre / Indécis
   - Influence : 1-5 (5 = très influent)
   - Accès : Direct / Indirect / Aucun
3. **DYNAMIQUE DES COALITIONS** — Qui est allié de qui, tensions
4. **FENÊTRES D'OPPORTUNITÉ** — Quand et comment influencer
5. **STRATÉGIE DE CONTACT** — Ordre de priorité, messages adaptés
6. **RISQUES** — Ce qui pourrait mal tourner

Sois précis sur les noms, fonctions et positions.
""",
    ),

    "note_comex": DocumentTemplate(
        livrable_type="note_comex",
        label="Note COMEX",
        description="Note stratégique pour le comité exécutif",
        context_keys=["texte_brief", "client_profile", "impact_alert"],
        supported_audiences=["direction"],
        max_tokens=3072,
        system_prompt="""Tu es le directeur PA. Rédige une NOTE COMEX pour {company}.

Format strict (1 page max) :

**OBJET** : [1 ligne]
**DÉCISION DEMANDÉE** : [1 ligne claire — ce que le COMEX doit décider]
**NIVEAU D'URGENCE** : [immédiat/cette semaine/ce mois]

**SITUATION** (5 lignes max)
- Que se passe-t-il
- Pourquoi c'est important pour {company}

**IMPACT FINANCIER ESTIMÉ** : [fourchette en €]

**OPTIONS** :
| Option | Description | Risque | Coût |
|--------|-------------|--------|------|
| A | ... | ... | ... |
| B | ... | ... | ... |

**RECOMMANDATION** : Option [X] parce que [1 phrase]
**PROCHAINE ÉTAPE** : [action + responsable + date]
""",
    ),

    "reponse_presse": DocumentTemplate(
        livrable_type="reponse_presse",
        label="Réponse presse",
        description="Réponse/communiqué suite à une couverture médiatique",
        context_keys=["press_article", "client_profile", "stakeholder_profile"],
        supported_audiences=["journaliste"],
        max_tokens=2048,
        system_prompt="""Tu es un directeur de communication. Rédige une RÉPONSE PRESSE pour {company}.

Choisis le format adapté :
A) **DROIT DE RÉPONSE** — Si article inexact/injuste
B) **COMMUNIQUÉ RÉACTIF** — Si sujet d'actualité à commenter
C) **ÉLÉMENTS DE RÉPONSE** — Si journaliste a contacté {company}

Pour A ou B :
- Titre accrocheur mais sobre
- 1er paragraphe : position de {company} en 2 phrases
- 2ème paragraphe : faits et chiffres correctifs
- 3ème paragraphe : perspective / ce que fait {company}
- Contact presse en signature

Pour C :
- Citation attribuable (entre guillemets, avec nom du porte-parole)
- Données factuelles complémentaires
- Background (off the record) si pertinent

Adapte le ton au média et au journaliste (si profil fourni).
""",
    ),
}


def get_template(livrable_type: str) -> DocumentTemplate | None:
    """Retourne le template pour un type de livrable."""
    return DOCUMENT_TEMPLATES.get(livrable_type)


def get_all_types() -> list[dict]:
    """Retourne la liste des types de livrables disponibles."""
    return [
        {
            "type": t.livrable_type,
            "label": t.label,
            "description": t.description,
            "audiences": t.supported_audiences,
        }
        for t in DOCUMENT_TEMPLATES.values()
    ]


def build_prompt(
    livrable_type: str,
    company_name: str,
    target_audience: str = "interne",
    context_data: dict | None = None,
) -> str:
    """Construit le prompt complet pour le Rédacteur.

    Args:
        livrable_type: Type de livrable (clé dans DOCUMENT_TEMPLATES)
        company_name: Nom de l'entreprise cliente
        target_audience: Type d'interlocuteur
        context_data: Données de contexte (brief, alert, stakeholders, etc.)

    Returns:
        Prompt complet prêt pour le Rédacteur.
    """
    template = get_template(livrable_type)
    if not template:
        return f"Rédige un document de type '{livrable_type}' pour {company_name}."

    # System prompt avec substitution du nom d'entreprise
    prompt = template.system_prompt.replace("{company}", company_name)

    # Adaptation interlocuteur
    audience_instruction = AUDIENCE_INSTRUCTIONS.get(target_audience, "")
    if audience_instruction:
        prompt += f"\n{audience_instruction}"

    # Ajouter le contexte fourni
    if context_data:
        prompt += "\n\n--- DONNÉES DE CONTEXTE ---\n"
        for key, value in context_data.items():
            if value:
                if isinstance(value, (dict, list)):
                    import json
                    prompt += f"\n{key}:\n{json.dumps(value, ensure_ascii=False, indent=2)}\n"
                else:
                    prompt += f"\n{key}:\n{value}\n"

    return prompt
