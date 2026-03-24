"""Enrichissement IA par batch — classifie themes + resume pour les textes non enrichis.

Usage : python3 scripts/enrich_batch.py [--limit 50] [--dry-run]

Necessite ANTHROPIC_API_KEY dans .env
"""

import asyncio
import json
import logging
import os
import sys
import time

sys.path.insert(0, "/Users/emmanuelblezes/legix")
os.chdir("/Users/emmanuelblezes/legix")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("enrich")

THEMES = [
    "sante", "environnement/climat", "fiscalite", "numerique/tech",
    "transport", "energie", "agriculture", "education", "defense",
    "travail/emploi", "logement", "justice", "finance", "industrie",
    "commerce", "securite", "culture", "immigration", "international",
]


async def enrich_one(client, title: str, content: str) -> dict:
    """Enrichit un texte avec Claude (1 appel)."""
    prompt = f"""Classifie ce texte legislatif.

THEMES POSSIBLES : {', '.join(THEMES)}

Retourne en JSON strict :
{{"themes": ["theme1", "theme2"], "resume": "Resume en 2 phrases."}}

TITRE : {title}
CONTENU : {(content or title)[:2000]}"""

    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    import re
    text = response.content[0].text
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group())
    return {"themes": [], "resume": ""}


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from legix.core.config import settings
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY non configuree. Ajoutez-la dans .env")
        sys.exit(1)

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    from legix.core.database import async_session, init_db
    from legix.core.models import Texte
    from sqlalchemy import select

    await init_db()

    async with async_session() as db:
        # Textes sans themes
        result = await db.execute(
            select(Texte)
            .where((Texte.themes == None) | (Texte.themes == ""))
            .limit(args.limit)
        )
        textes = result.scalars().all()
        logger.info("Textes a enrichir: %d (limit=%d)", len(textes), args.limit)

        if args.dry_run:
            for t in textes[:5]:
                logger.info("  [DRY] %s", (t.titre or "?")[:80])
            return

        enriched = 0
        errors = 0
        for i, t in enumerate(textes):
            try:
                result = await enrich_one(
                    client,
                    title=t.titre or t.titre_court or "",
                    content=t.resume_ia or t.titre or "",
                )
                t.themes = json.dumps(result.get("themes", []), ensure_ascii=False)
                if result.get("resume") and not t.resume_ia:
                    t.resume_ia = result["resume"]
                enriched += 1

                if (i + 1) % 10 == 0:
                    await db.commit()
                    logger.info("  %d/%d enrichis...", i + 1, len(textes))

                # Rate limit
                await asyncio.sleep(0.2)

            except Exception as e:
                errors += 1
                logger.warning("  Erreur %s: %s", (t.titre or "?")[:40], str(e)[:80])

        await db.commit()
        logger.info("Enrichissement termine: %d/%d enrichis, %d erreurs", enriched, len(textes), errors)


if __name__ == "__main__":
    asyncio.run(main())
