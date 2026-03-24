"""Routes statistiques."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_db
from legix.core.models import Acteur, Amendement, CompteRendu, Organe, Reunion, Signal, Texte

router = APIRouter()


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Compteurs globaux par entité et source."""
    counts = {}
    for model, name in [
        (Texte, "textes"), (Amendement, "amendements"),
        (Reunion, "reunions"), (CompteRendu, "comptes_rendus"),
        (Acteur, "acteurs"), (Organe, "organes"), (Signal, "signaux"),
    ]:
        total = (await db.execute(select(func.count()).select_from(model))).scalar() or 0
        counts[name] = total

    # Par source
    by_source = {}
    for model, name in [(Texte, "textes"), (Amendement, "amendements")]:
        stmt = select(model.source, func.count()).group_by(model.source)
        result = await db.execute(stmt)
        by_source[name] = {row[0]: row[1] for row in result.all()}

    # Enrichissement IA
    enriched_textes = (await db.execute(
        select(func.count()).select_from(Texte).where(Texte.resume_ia.isnot(None))
    )).scalar() or 0
    enriched_amdts = (await db.execute(
        select(func.count()).select_from(Amendement).where(Amendement.resume_ia.isnot(None))
    )).scalar() or 0

    return {
        "counts": counts,
        "by_source": by_source,
        "enrichment": {
            "textes_enriched": enriched_textes,
            "textes_total": counts["textes"],
            "amendements_enriched": enriched_amdts,
            "amendements_total": counts["amendements"],
        },
    }
