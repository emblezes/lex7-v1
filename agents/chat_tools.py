"""Fonctions de requete DB exposees comme outils Claude tool-use.

Adapte de LegisAPI pour SQLAlchemy async.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.core.models import (
    Acteur,
    Amendement,
    ClientProfile,
    CompteRendu,
    ImpactAlert,
    Organe,
    Reunion,
    Signal,
    Texte,
)


async def search_documents(db: AsyncSession, query: str, limit: int = 10) -> dict:
    """Recherche full-text sur tous les types de documents."""
    pattern = f"%{query}%"

    # Textes
    result = await db.execute(
        select(Texte)
        .where(
            Texte.titre.ilike(pattern)
            | Texte.titre_court.ilike(pattern)
            | Texte.themes.ilike(pattern)
        )
        .order_by(Texte.date_depot.desc())
        .limit(limit)
    )
    textes = result.scalars().all()

    # Amendements
    result = await db.execute(
        select(Amendement)
        .options(joinedload(Amendement.auteur), joinedload(Amendement.groupe))
        .where(
            Amendement.dispositif.ilike(pattern)
            | Amendement.expose_sommaire.ilike(pattern)
            | Amendement.themes.ilike(pattern)
        )
        .order_by(Amendement.date_depot.desc())
        .limit(limit)
    )
    amendements = result.unique().scalars().all()

    # Reunions
    result = await db.execute(
        select(Reunion)
        .options(joinedload(Reunion.organe))
        .where(Reunion.odj.ilike(pattern) | Reunion.themes.ilike(pattern))
        .order_by(Reunion.date_debut.desc())
        .limit(limit)
    )
    reunions = result.unique().scalars().all()

    return {
        "textes": [
            {
                "uid": t.uid,
                "titre": t.titre_court or t.titre,
                "type": t.type_libelle,
                "date_depot": str(t.date_depot) if t.date_depot else None,
                "themes": t.themes,
                "resume_ia": t.resume_ia,
            }
            for t in textes
        ],
        "amendements": [
            {
                "uid": a.uid,
                "numero": a.numero,
                "auteur": f"{a.auteur.prenom} {a.auteur.nom}" if a.auteur else None,
                "groupe": a.groupe.libelle_court if a.groupe else None,
                "article_vise": a.article_vise,
                "sort": a.sort,
                "themes": a.themes,
                "resume_ia": a.resume_ia,
            }
            for a in amendements
        ],
        "reunions": [
            {
                "uid": r.uid,
                "date": str(r.date_debut) if r.date_debut else None,
                "organe": r.organe.libelle_court if r.organe else None,
                "themes": r.themes,
            }
            for r in reunions
        ],
        "total": len(textes) + len(amendements) + len(reunions),
    }


async def get_textes(
    db: AsyncSession,
    theme: str | None = None,
    type_code: str | None = None,
    limit: int = 10,
) -> dict:
    """Filtre et retourne des textes legislatifs."""
    stmt = select(Texte)
    if theme:
        stmt = stmt.where(Texte.themes.ilike(f"%{theme}%"))
    if type_code:
        stmt = stmt.where(Texte.type_code == type_code)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(stmt.order_by(Texte.date_depot.desc()).limit(limit))
    items = result.scalars().all()

    return {
        "total": total,
        "textes": [
            {
                "uid": t.uid,
                "titre": t.titre_court or t.titre,
                "type": t.type_libelle,
                "type_code": t.type_code,
                "date_depot": str(t.date_depot) if t.date_depot else None,
                "themes": t.themes,
                "resume_ia": t.resume_ia,
            }
            for t in items
        ],
    }


async def get_amendements(
    db: AsyncSession,
    groupe: str | None = None,
    theme: str | None = None,
    sort: str | None = None,
    limit: int = 10,
) -> dict:
    """Filtre et retourne des amendements."""
    stmt = select(Amendement).options(
        joinedload(Amendement.auteur), joinedload(Amendement.groupe)
    )
    if groupe:
        stmt = stmt.join(Organe, Amendement.groupe_ref == Organe.uid).where(
            Organe.libelle_court.ilike(f"%{groupe}%")
            | Organe.libelle.ilike(f"%{groupe}%")
        )
    if theme:
        stmt = stmt.where(Amendement.themes.ilike(f"%{theme}%"))
    if sort:
        stmt = stmt.where(Amendement.sort.ilike(f"%{sort}%"))

    result = await db.execute(stmt.order_by(Amendement.date_depot.desc()).limit(limit))
    items = result.unique().scalars().all()

    return {
        "total": len(items),
        "amendements": [
            {
                "uid": a.uid,
                "numero": a.numero,
                "auteur": f"{a.auteur.prenom} {a.auteur.nom}" if a.auteur else None,
                "groupe": a.groupe.libelle_court if a.groupe else None,
                "article_vise": a.article_vise,
                "date_depot": str(a.date_depot) if a.date_depot else None,
                "sort": a.sort,
                "etat": a.etat,
                "themes": a.themes,
                "resume_ia": a.resume_ia,
            }
            for a in items
        ],
    }


async def get_reunions(
    db: AsyncSession, theme: str | None = None, limit: int = 10
) -> dict:
    """Filtre et retourne des reunions."""
    stmt = select(Reunion).options(joinedload(Reunion.organe))
    if theme:
        stmt = stmt.where(
            Reunion.themes.ilike(f"%{theme}%") | Reunion.odj.ilike(f"%{theme}%")
        )
    result = await db.execute(stmt.order_by(Reunion.date_debut.desc()).limit(limit))
    items = result.unique().scalars().all()

    return {
        "total": len(items),
        "reunions": [
            {
                "uid": r.uid,
                "date": str(r.date_debut) if r.date_debut else None,
                "lieu": r.lieu,
                "organe": r.organe.libelle_court if r.organe else None,
                "etat": r.etat,
                "themes": r.themes,
            }
            for r in items
        ],
    }


async def get_stats(db: AsyncSession) -> dict:
    """Statistiques globales de la base."""
    counts = {}
    for model, key in [
        (Texte, "textes"),
        (Amendement, "amendements"),
        (Reunion, "reunions"),
        (CompteRendu, "comptes_rendus"),
        (Acteur, "acteurs"),
        (Organe, "organes"),
    ]:
        result = await db.execute(select(func.count()).select_from(model))
        counts[key] = result.scalar() or 0
    return counts


async def get_signals(
    db: AsyncSession,
    theme: str | None = None,
    severity: str | None = None,
    days: int = 7,
) -> dict:
    """Retourne les signaux faibles recents."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = select(Signal).where(
        Signal.created_at >= cutoff,
        Signal.is_dismissed.is_(False),
    )
    if severity:
        stmt = stmt.where(Signal.severity == severity)

    result = await db.execute(stmt.order_by(Signal.created_at.desc()).limit(20))
    signals = result.scalars().all()

    if theme:
        theme_lower = theme.lower()
        signals = [
            s
            for s in signals
            if theme_lower in (s.themes or "").lower()
            or theme_lower in (s.title or "").lower()
        ]

    return {
        "total": len(signals),
        "signals": [
            {
                "type": s.signal_type,
                "severity": s.severity,
                "title": s.title,
                "description": s.description,
                "themes": json.loads(s.themes) if s.themes else [],
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in signals[:10]
        ],
    }


async def get_strategic_context(
    db: AsyncSession, sector: str, days: int = 30
) -> dict:
    """Vue 360 d'un secteur : textes, acteurs cles, calendrier, signaux."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    pattern = f'%"{sector}"%'
    sector_like = f"%{sector}%"

    # Textes actifs
    result = await db.execute(
        select(Texte)
        .where(Texte.themes.ilike(pattern), Texte.date_depot >= cutoff)
        .order_by(Texte.date_depot.desc())
        .limit(10)
    )
    textes = result.scalars().all()

    # Amendements
    result = await db.execute(
        select(Amendement)
        .options(joinedload(Amendement.auteur), joinedload(Amendement.groupe))
        .where(Amendement.themes.ilike(pattern), Amendement.date_depot >= cutoff)
        .order_by(Amendement.date_depot.desc())
    )
    amdts = result.unique().scalars().all()

    # Acteurs cles par activite
    depute_activity: dict[str, dict] = {}
    for a in amdts:
        if a.auteur_ref:
            if a.auteur_ref not in depute_activity:
                nom = (
                    f"{a.auteur.prenom or ''} {a.auteur.nom or ''}".strip()
                    if a.auteur
                    else a.auteur_ref
                )
                groupe = (
                    (a.groupe.libelle_court or a.groupe.libelle) if a.groupe else ""
                )
                depute_activity[a.auteur_ref] = {
                    "nom": nom,
                    "groupe": groupe,
                    "total": 0,
                    "adoptes": 0,
                }
            depute_activity[a.auteur_ref]["total"] += 1
            if a.sort and "adopt" in a.sort.lower():
                depute_activity[a.auteur_ref]["adoptes"] += 1

    top_deputes = sorted(depute_activity.values(), key=lambda x: -x["total"])[:10]

    # Signaux
    result = await db.execute(
        select(Signal)
        .where(
            Signal.created_at >= cutoff,
            Signal.is_dismissed.is_(False),
            Signal.themes.ilike(sector_like),
        )
        .order_by(Signal.created_at.desc())
        .limit(5)
    )
    signaux = result.scalars().all()

    nb_adoptes = sum(1 for a in amdts if a.sort and "adopt" in a.sort.lower())
    nb_sorted = sum(1 for a in amdts if a.sort)
    taux_adoption = round(nb_adoptes / nb_sorted, 3) if nb_sorted > 0 else 0

    return {
        "secteur": sector,
        "periode_jours": days,
        "stats": {
            "nb_textes": len(textes),
            "nb_amendements": len(amdts),
            "taux_adoption": taux_adoption,
            "nb_signaux": len(signaux),
        },
        "textes_actifs": [
            {
                "titre": t.titre_court or t.titre or t.uid,
                "type": t.type_code,
                "resume": t.resume_ia,
            }
            for t in textes[:5]
        ],
        "acteurs_cles": top_deputes,
        "signaux": [
            {"type": s.signal_type, "severity": s.severity, "title": s.title}
            for s in signaux
        ],
    }


async def analyze_depute(
    db: AsyncSession, uid_or_name: str
) -> dict:
    """Intelligence complete d'un depute : profil, taux adoption par theme,
    cosignataires frequents, activite recente."""
    from legix.agents.intelligence import (
        depute_by_name,
        depute_full_profile,
        depute_adoption_by_theme,
        depute_cosignataires_frequents,
        depute_recent_activity,
    )

    # Resoudre par UID ou par nom
    if uid_or_name.startswith("PA"):
        uid = uid_or_name
    else:
        acteur = await depute_by_name(db, uid_or_name)
        if not acteur:
            return {"error": f"Depute '{uid_or_name}' non trouve"}
        uid = acteur.uid

    profile = await depute_full_profile(db, uid)
    if "error" in profile:
        return profile

    themes = await depute_adoption_by_theme(db, uid)
    cosignataires = await depute_cosignataires_frequents(db, uid)
    recent = await depute_recent_activity(db, uid)

    return {
        **profile,
        "adoption_par_theme": dict(list(themes.items())[:8]),
        "cosignataires_frequents": cosignataires,
        "activite_recente_30j": recent,
    }


async def analyze_groupe(
    db: AsyncSession, uid_or_name: str, theme: str | None = None
) -> dict:
    """Intelligence d'un groupe politique : taux adoption (global + par theme),
    deputes les plus actifs, themes principaux."""
    from legix.agents.intelligence import (
        groupe_by_name,
        groupe_adoption_rate,
        groupe_top_deputes,
    )

    # Resoudre par UID ou par nom
    if uid_or_name.startswith("PO"):
        uid = uid_or_name
    else:
        organe = await groupe_by_name(db, uid_or_name)
        if not organe:
            return {"error": f"Groupe '{uid_or_name}' non trouve"}
        uid = organe.uid

    rate = await groupe_adoption_rate(db, uid, theme=theme)
    if "error" in rate:
        return rate

    top = await groupe_top_deputes(db, uid)

    return {
        **rate,
        "deputes_actifs": top,
    }


async def analyze_texte_dynamics(db: AsyncSession, texte_uid: str) -> dict:
    """Dynamique legislative autour d'un texte : qui amende, quels groupes,
    taux adoption, amendements gouvernementaux, themes."""
    from legix.agents.intelligence import texte_amendment_dynamics

    return await texte_amendment_dynamics(db, texte_uid)


async def get_amendement_network(db: AsyncSession, amendement_uid: str) -> dict:
    """Reseau complet d'un amendement : auteur (avec intelligence), cosignataires,
    convergence transpartisane, score adoption, texte parent."""
    from legix.agents.intelligence import amendement_cosignataire_network

    return await amendement_cosignataire_network(db, amendement_uid)


async def get_client_profile(
    db: AsyncSession, profile_id: int | None = None
) -> dict:
    """Retourne le profil client actif."""
    if profile_id:
        stmt = select(ClientProfile).where(ClientProfile.id == profile_id)
    else:
        stmt = select(ClientProfile).where(ClientProfile.is_active.is_(True))

    result = await db.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        return {"error": "Aucun profil client actif trouve"}

    def _parse(val):
        if not val:
            return []
        try:
            return json.loads(val) if isinstance(val, str) else val
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "id": profile.id,
        "name": profile.name,
        "sectors": _parse(profile.sectors),
        "business_lines": _parse(profile.business_lines),
        "products": _parse(profile.products),
        "regulatory_focus": _parse(profile.regulatory_focus),
        "context_note": profile.context_note,
        "description": profile.description,
        "monitoring_explanation": profile.monitoring_explanation,
        # Données publiques entreprise
        "siren": profile.siren,
        "code_naf": profile.code_naf,
        "categorie_entreprise": profile.categorie_entreprise,
        "chiffre_affaires": profile.chiffre_affaires,
        "effectifs": profile.effectifs,
        "siege_social": profile.siege_social,
        "dirigeants": _parse(profile.dirigeants),
        "key_risks": _parse(profile.key_risks),
        "key_opportunities": _parse(profile.key_opportunities),
        # Préférences de veille
        "followed_textes": _parse(profile.followed_textes),
        "min_signal_severity": profile.min_signal_severity,
    }


# --- Definitions d'outils Claude ---

TOOL_DEFINITIONS = [
    {
        "name": "search_documents",
        "description": (
            "Recherche full-text sur tous les documents parlementaires "
            "(textes de loi, amendements, reunions)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Terme de recherche"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_textes",
        "description": "Recupere des textes legislatifs avec filtres par theme et type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string"},
                "type_code": {"type": "string", "description": "PION ou PRJL"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_amendements",
        "description": "Recupere des amendements avec filtres par groupe, theme, sort.",
        "input_schema": {
            "type": "object",
            "properties": {
                "groupe": {"type": "string"},
                "theme": {"type": "string"},
                "sort": {"type": "string", "description": "Adopte/Rejete/Retire"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_reunions",
        "description": "Recupere des reunions de commissions parlementaires.",
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_stats",
        "description": "Statistiques globales de la base de donnees parlementaire.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_signals",
        "description": (
            "Signaux faibles recents : convergences transpartisanes, pics d'amendements, "
            "themes emergents, accelerations gouvernementales."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string"},
                "severity": {"type": "string"},
                "days": {"type": "integer", "default": 7},
            },
            "required": [],
        },
    },
    {
        "name": "get_strategic_context",
        "description": "Vue strategique 360 d'un secteur : textes, acteurs cles, signaux.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "Secteur a analyser"},
                "days": {"type": "integer", "default": 30},
            },
            "required": ["sector"],
        },
    },
    {
        "name": "analyze_depute",
        "description": (
            "Intelligence complete d'un depute ou acteur : taux adoption global et par theme, "
            "cosignataires frequents, activite recente (30j), groupe politique. "
            "Utilise pour comprendre le comportement d'un acteur legislatif."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "uid_or_name": {
                    "type": "string",
                    "description": "UID (ex: PA721900) ou nom du depute",
                },
            },
            "required": ["uid_or_name"],
        },
    },
    {
        "name": "analyze_groupe",
        "description": (
            "Intelligence d'un groupe politique : taux adoption global ou filtre par theme, "
            "deputes les plus actifs, themes principaux. "
            "Utilise pour comprendre la position d'un groupe sur un sujet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "uid_or_name": {
                    "type": "string",
                    "description": "UID (ex: PO730964) ou nom du groupe (ex: 'Renaissance', 'RN', 'LFI')",
                },
                "theme": {
                    "type": "string",
                    "description": "Theme optionnel pour filtrer (ex: 'sante', 'environnement/climat')",
                },
            },
            "required": ["uid_or_name"],
        },
    },
    {
        "name": "analyze_texte_dynamics",
        "description": (
            "Dynamique legislative autour d'un texte : nb amendements, groupes impliques "
            "avec taux adoption, deputes actifs, amendements gouvernementaux, themes. "
            "Utilise pour comprendre les forces en jeu autour d'un texte de loi."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "texte_uid": {
                    "type": "string",
                    "description": "UID du texte (ex: PIONANR5L17B2037)",
                },
            },
            "required": ["texte_uid"],
        },
    },
    {
        "name": "get_amendement_network",
        "description": (
            "Reseau complet d'un amendement : auteur avec profil intelligence, "
            "cosignataires, convergence transpartisane, score adoption, texte parent. "
            "Utilise pour evaluer la force et les chances d'un amendement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amendement_uid": {
                    "type": "string",
                    "description": "UID de l'amendement (ex: AMANR5L17PO744107B2037A16)",
                },
            },
            "required": ["amendement_uid"],
        },
    },
    {
        "name": "get_client_profile",
        "description": "Profil client actif avec secteurs et preferences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "profile_id": {"type": "integer"},
            },
            "required": [],
        },
    },
]

# Mapping nom -> fonction
TOOL_FUNCTIONS = {
    "search_documents": search_documents,
    "get_textes": get_textes,
    "get_amendements": get_amendements,
    "get_reunions": get_reunions,
    "get_stats": get_stats,
    "get_signals": get_signals,
    "get_strategic_context": get_strategic_context,
    "analyze_depute": analyze_depute,
    "analyze_groupe": analyze_groupe,
    "analyze_texte_dynamics": analyze_texte_dynamics,
    "get_amendement_network": get_amendement_network,
    "get_client_profile": get_client_profile,
}
