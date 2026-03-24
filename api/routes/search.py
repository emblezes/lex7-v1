"""Route recherche full-text."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.api.deps import get_db
from legix.core.models import Acteur, Amendement, CompteRendu, Reunion, Texte

router = APIRouter()


@router.get("/search")
async def search(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Recherche multi-entité."""
    pattern = f"%{q}%"

    # Textes
    textes = (await db.execute(
        select(Texte)
        .where(Texte.titre.ilike(pattern) | Texte.titre_court.ilike(pattern))
        .limit(limit)
    )).scalars().all()

    # Amendements
    amdts = (await db.execute(
        select(Amendement)
        .where(Amendement.dispositif.ilike(pattern) | Amendement.expose_sommaire.ilike(pattern))
        .limit(limit)
    )).scalars().all()

    # Acteurs
    acteurs = (await db.execute(
        select(Acteur)
        .where(Acteur.nom.ilike(pattern) | Acteur.prenom.ilike(pattern))
        .limit(limit)
    )).scalars().all()

    # Réunions (ODJ)
    reunions = (await db.execute(
        select(Reunion).where(Reunion.odj.ilike(pattern)).limit(limit)
    )).scalars().all()

    return {
        "query": q,
        "results": {
            "textes": [
                {"uid": t.uid, "titre": t.titre_court or t.titre, "type": t.type_code}
                for t in textes
            ],
            "amendements": [
                {"uid": a.uid, "numero": a.numero, "texte_ref": a.texte_ref}
                for a in amdts
            ],
            "acteurs": [
                {"uid": a.uid, "prenom": a.prenom, "nom": a.nom}
                for a in acteurs
            ],
            "reunions": [
                {"uid": r.uid, "date_debut": r.date_debut.isoformat() if r.date_debut else None}
                for r in reunions
            ],
        },
        "counts": {
            "textes": len(textes),
            "amendements": len(amdts),
            "acteurs": len(acteurs),
            "reunions": len(reunions),
            "total": len(textes) + len(amdts) + len(acteurs) + len(reunions),
        },
    }
