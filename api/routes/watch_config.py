"""Routes API — Configuration de veille personnalisée par client.

Chaque client a son propre périmètre de surveillance :
mots-clés, sources, ONG, journalistes, régulateurs, etc.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db
from legix.core.models import ClientProfile

router = APIRouter(prefix="/profiles/{profile_id}/watch-config", tags=["watch-config"])


class WatchConfigUpdate(BaseModel):
    """Mise à jour partielle de la configuration de veille."""
    watch_keywords: list[str] | None = None
    watch_keywords_exclude: list[str] | None = None
    competitors: list[str] | None = None
    watched_think_tanks: list[str] | None = None
    watched_inspections: list[str] | None = None
    watched_ngos: list[str] | None = None
    watched_federations: list[str] | None = None
    watched_media: list[str] | None = None
    watched_journalists: list | None = None  # list[dict] avec nom, media, theme
    watched_politicians: list[str] | None = None
    watched_regulators: list[str] | None = None
    eu_watch_keywords: list[str] | None = None
    eu_watched_committees: list[str] | None = None
    pa_strategy: str | None = None
    pa_priorities: list[str] | None = None


@router.get("")
async def get_watch_config(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Retourne la configuration de veille complète d'un client."""
    from legix.services.client_matching import get_client_watch_config
    config = await get_client_watch_config(db, profile_id)
    if "error" in config:
        raise HTTPException(404, config["error"])
    return config


@router.put("")
async def update_watch_config(
    profile_id: int,
    data: WatchConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Met à jour la configuration de veille d'un client.

    Seuls les champs fournis sont mis à jour (merge partiel).
    """
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Profil non trouvé")

    # Mapper les champs Pydantic vers les colonnes ORM
    field_map = {
        "watch_keywords": "watch_keywords",
        "watch_keywords_exclude": "watch_keywords_exclude",
        "competitors": "competitors",
        "watched_think_tanks": "watched_think_tanks",
        "watched_inspections": "watched_inspections",
        "watched_ngos": "watched_ngos",
        "watched_federations": "watched_federations",
        "watched_media": "watched_media",
        "watched_journalists": "watched_journalists",
        "watched_politicians": "watched_politicians",
        "watched_regulators": "watched_regulators",
        "eu_watch_keywords": "eu_watch_keywords",
        "eu_watched_committees": "eu_watched_committees",
        "pa_priorities": "pa_priorities",
    }

    updated_fields = []
    for field_name, column_name in field_map.items():
        value = getattr(data, field_name)
        if value is not None:
            setattr(profile, column_name, json.dumps(value, ensure_ascii=False))
            updated_fields.append(field_name)

    # pa_strategy est un texte libre, pas JSON
    if data.pa_strategy is not None:
        profile.pa_strategy = data.pa_strategy
        updated_fields.append("pa_strategy")

    await db.commit()

    return {
        "status": "updated",
        "profile_id": profile_id,
        "updated_fields": updated_fields,
    }


@router.post("/suggest")
async def suggest_watch_config(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Suggère une configuration de veille basée sur le profil du client.

    Utilise les secteurs, produits et enjeux réglementaires pour proposer
    des sources, mots-clés et acteurs pertinents.
    """
    profile = await db.get(ClientProfile, profile_id)
    if not profile:
        raise HTTPException(404, "Profil non trouvé")

    sectors = json.loads(profile.sectors) if profile.sectors else []
    regulatory_focus = json.loads(profile.regulatory_focus) if profile.regulatory_focus else []

    # Suggestions basées sur les secteurs
    suggestions = _build_suggestions(sectors, regulatory_focus, profile.name)

    return {
        "profile_id": profile_id,
        "suggestions": suggestions,
        "note": "Ces suggestions sont générées automatiquement. Validez et ajustez selon vos besoins.",
    }


def _build_suggestions(
    sectors: list[str],
    regulatory_focus: list[str],
    company_name: str,
) -> dict:
    """Génère des suggestions de configuration de veille par secteur."""

    # Mapping secteur → sources recommandées
    SECTOR_SOURCES = {
        "santé": {
            "regulators": ["ANSM", "HAS", "CNAM"],
            "ngos": ["France Assos Santé", "UFC-Que Choisir", "Ligue contre le cancer"],
            "federations": ["LEEM", "FEFIS", "SNITEM"],
            "think_tanks": ["IGAS", "France Stratégie", "Terra Nova"],
            "media": ["APMnews", "Le Quotidien du Médecin", "Contexte Santé"],
            "keywords": ["AMM", "pharmacovigilance", "prix du médicament", "remboursement", "ONDAM"],
            "eu_keywords": ["EMA", "pharmaceutical strategy", "HTA regulation"],
            "eu_committees": ["ENVI"],
        },
        "énergie": {
            "regulators": ["CRE", "ADEME", "ASN"],
            "ngos": ["Greenpeace France", "FNE", "Réseau Action Climat", "WWF France"],
            "federations": ["UFE", "UFIP", "SER"],
            "think_tanks": ["France Stratégie", "IDDRI", "I4CE"],
            "media": ["Contexte Énergie", "Enerpresse", "Actu-Environnement"],
            "keywords": ["mix énergétique", "nucléaire", "renouvelable", "PPE", "ARENH", "tarif réglementé"],
            "eu_keywords": ["Green Deal", "Fit for 55", "REPowerEU", "ETS"],
            "eu_committees": ["ITRE", "ENVI"],
        },
        "numérique": {
            "regulators": ["CNIL", "ARCEP", "Arcom"],
            "ngos": ["La Quadrature du Net", "UFC-Que Choisir"],
            "federations": ["Syntec Numérique", "France Digitale", "AFNUM"],
            "think_tanks": ["Institut Montaigne", "CNNum", "France Stratégie"],
            "media": ["Contexte Numérique", "Next INpact", "L'Usine Digitale"],
            "keywords": ["données personnelles", "IA", "cybersécurité", "cloud souverain", "RGPD"],
            "eu_keywords": ["AI Act", "DSA", "DMA", "Data Act", "GDPR"],
            "eu_committees": ["IMCO", "ITRE", "LIBE"],
        },
        "environnement/climat": {
            "regulators": ["ADEME", "OFB", "Cerema"],
            "ngos": ["WWF France", "Greenpeace", "FNE", "Oxfam France", "Les Amis de la Terre"],
            "federations": ["MEDEF Environnement", "AFEP"],
            "think_tanks": ["IDDRI", "I4CE", "Haut Conseil pour le Climat"],
            "media": ["Actu-Environnement", "Novethic", "Reporterre"],
            "keywords": ["PFAS", "biodiversité", "carbone", "ZAN", "CSRD", "taxonomie"],
            "eu_keywords": ["Green Deal", "CSRD", "taxonomy", "carbon border", "deforestation"],
            "eu_committees": ["ENVI"],
        },
        "agriculture/alimentation": {
            "regulators": ["DGCCRF", "ANSES", "FranceAgriMer"],
            "ngos": ["Foodwatch", "UFC-Que Choisir", "Générations Futures"],
            "federations": ["FNSEA", "ANIA", "Coop de France"],
            "think_tanks": ["France Stratégie", "INRAE"],
            "media": ["Agra Presse", "Terre-net", "La France Agricole"],
            "keywords": ["PAC", "pesticides", "Nutri-Score", "EGALIM", "origine", "phytosanitaire"],
            "eu_keywords": ["CAP", "Farm to Fork", "pesticides regulation"],
            "eu_committees": ["AGRI", "ENVI"],
        },
        "économie/finances": {
            "regulators": ["AMF", "ACPR", "Banque de France"],
            "ngos": ["Oxfam France", "Attac", "Transparency International"],
            "federations": ["FBF", "France Invest", "AFG"],
            "think_tanks": ["Institut Montaigne", "OFCE", "Fondapol", "IFRAP"],
            "media": ["Les Echos", "L'Agefi", "Option Finance"],
            "keywords": ["PLF", "PLFSS", "fiscalité", "épargne", "compétitivité"],
            "eu_keywords": ["MiFID", "Basel", "AIFMD", "sustainable finance"],
            "eu_committees": ["ECON"],
        },
        "transports": {
            "regulators": ["ART", "DGAC", "DGITM"],
            "ngos": ["FNE Transport", "Respire"],
            "federations": ["FNTR", "UTP", "FNTV"],
            "think_tanks": ["France Stratégie", "IDDRI"],
            "media": ["Mobilités Magazine", "VRT"],
            "keywords": ["ZFE", "ferroviaire", "mobilité", "véhicule électrique", "LOM"],
            "eu_keywords": ["Fit for 55 transport", "ETS aviation", "Euro 7"],
            "eu_committees": ["TRAN"],
        },
        "logement/urbanisme": {
            "regulators": ["ANAH", "Cerema"],
            "ngos": ["Fondation Abbé Pierre", "DAL", "CLCV"],
            "federations": ["FFB", "FPI", "FNAIM"],
            "think_tanks": ["France Stratégie", "Terra Nova"],
            "media": ["Le Moniteur", "Batiactu"],
            "keywords": ["DPE", "rénovation énergétique", "ZAN", "loi SRU", "encadrement loyers"],
            "eu_keywords": ["EPBD", "renovation wave"],
            "eu_committees": ["ITRE"],
        },
    }

    result = {
        "keywords": list(set(regulatory_focus)),  # Commencer par le focus réglementaire
        "regulators": [],
        "ngos": [],
        "federations": [],
        "think_tanks": [],
        "media": [],
        "eu_keywords": [],
        "eu_committees": [],
        "competitors": [],
    }

    for sector in sectors:
        sector_lower = sector.lower()
        config = SECTOR_SOURCES.get(sector_lower, {})
        for key in result:
            if key in config:
                result[key].extend(config[key])

    # Dédupliquer
    for key in result:
        result[key] = list(dict.fromkeys(result[key]))

    return result
