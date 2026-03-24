"""Routes API — Onboarding automatisé + Feedback loop.

Deux fonctionnalités critiques pour le scale :
1. Onboarding : le client donne son nom → tout est configuré automatiquement
2. Feedback : le client dit "pertinent/pas pertinent" → le scoring s'affine
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from legix.core.database import get_db

router = APIRouter(tags=["onboarding-auto"])


# --- Onboarding automatisé ---


class OnboardingRequest(BaseModel):
    profile_id: int


@router.post("/onboarding/auto")
async def run_auto_onboarding(
    data: OnboardingRequest,
    db: AsyncSession = Depends(get_db),
):
    """Lance l'onboarding automatisé complet pour un client.

    Pipeline :
    1. Enrichissement entreprise (SIRENE + site web + BODACC + Claude)
    2. Configuration de veille automatique (sources, ONG, régulateurs)
    3. Scan du backlog législatif (textes existants pertinents)
    4. Détection des signaux d'anticipation

    Le client n'a rien à faire. En 2 minutes, son dashboard est prêt.
    """
    from legix.agents.onboarder import run_full_onboarding

    result = await run_full_onboarding(db, data.profile_id)
    if "error" in result:
        raise HTTPException(404, result["error"])

    return result


# --- Feedback loop ---


class FeedbackRequest(BaseModel):
    doc_type: str  # texte / anticipation / press_article / signal / alert
    doc_id: str  # UID ou ID du document
    relevant: bool  # True = pertinent, False = bruit
    themes: list[str] | None = None
    source_name: str | None = None
    keywords: list[str] | None = None


@router.post("/profiles/{profile_id}/feedback")
async def submit_feedback(
    profile_id: int,
    data: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enregistre un feedback client (pertinent/non pertinent) et ajuste la veille.

    Le système apprend des retours :
    - Documents pertinents → renforce les mots-clés et sources associés
    - Documents non pertinents → ajoute des exclusions, signale les sources bruyantes

    Retourne les ajustements effectués.
    """
    from legix.services.feedback_loop import record_feedback

    result = await record_feedback(
        db=db,
        profile_id=profile_id,
        doc_type=data.doc_type,
        doc_id=data.doc_id,
        relevant=data.relevant,
        themes=data.themes,
        source_name=data.source_name,
        keywords_in_title=data.keywords,
    )

    if "error" in result:
        raise HTTPException(404, result["error"])

    return result


@router.get("/profiles/{profile_id}/feedback/stats")
async def get_feedback_stats(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Statistiques de feedback : précision de la veille, sources fiables, etc."""
    from legix.services.feedback_loop import get_feedback_stats as _get_stats

    result = await _get_stats(db, profile_id)
    if "error" in result:
        raise HTTPException(404, result["error"])

    return result
