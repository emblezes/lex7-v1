"""Script de rattrapage historique — ingere les donnees manquantes.

Usage:
    python -m legix.backfill                    # Tout (AN 30j + Senat session + scrutins)
    python -m legix.backfill --an               # AN seulement (30 derniers jours)
    python -m legix.backfill --senat            # Senat seulement (session courante)
    python -m legix.backfill --scrutins         # Scrutins seulement (zip complet)
    python -m legix.backfill --an --days 60     # AN avec 60 jours de rattrapage
"""

import argparse
import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger("legix.backfill")


async def backfill_an(days: int = 30):
    """Rattrapage Assemblee nationale."""
    from legix.collectors.assemblee import AssembleeCollector
    from legix.core.database import async_session

    logger.info("=== Backfill Assemblee nationale (%d jours) ===", days)
    collector = AssembleeCollector()
    async with async_session() as db:
        stats = await collector.backfill(db, days=days)
    logger.info("AN termine: %d nouveaux, %d erreurs", stats["new"], stats["errors"])
    return stats


async def backfill_senat(max_numero: int = 500):
    """Rattrapage Senat."""
    from legix.collectors.senat import SenatCollector
    from legix.core.database import async_session

    logger.info("=== Backfill Senat (session courante, textes 1-%d) ===", max_numero)
    collector = SenatCollector()
    async with async_session() as db:
        stats = await collector.backfill(db, max_numero=max_numero)
    logger.info("Senat termine: %d nouveaux, %d erreurs", stats["new"], stats["errors"])
    return stats


async def backfill_scrutins():
    """Rattrapage scrutins (votes nominatifs)."""
    from legix.collectors.scrutins import ScrutinsCollector
    from legix.core.database import async_session

    logger.info("=== Backfill Scrutins (ZIP complet AN) ===")
    collector = ScrutinsCollector()
    async with async_session() as db:
        stats = await collector.collect(db)
    logger.info(
        "Scrutins termine: %d nouveaux votes, %d scrutins, %d erreurs",
        stats["new"], stats["by_type"].get("scrutin", 0), stats["errors"],
    )
    return stats


async def main(args):
    run_all = not (args.an or args.senat or args.scrutins)

    if args.an or run_all:
        await backfill_an(days=args.days)

    if args.senat or run_all:
        await backfill_senat()

    if args.scrutins or run_all:
        await backfill_scrutins()

    logger.info("=== Backfill complet ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rattrapage historique LegiX")
    parser.add_argument("--an", action="store_true", help="Backfill Assemblee nationale")
    parser.add_argument("--senat", action="store_true", help="Backfill Senat")
    parser.add_argument("--scrutins", action="store_true", help="Backfill scrutins")
    parser.add_argument("--days", type=int, default=30, help="Jours de rattrapage AN (defaut: 30)")
    args = parser.parse_args()

    asyncio.run(main(args))
