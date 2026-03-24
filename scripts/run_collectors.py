"""Lance tous les collecteurs une fois et affiche les stats.

Usage : python3 scripts/run_collectors.py
"""

import asyncio
import json
import logging
import sys
import time

sys.path.insert(0, "/Users/emmanuelblezes/legix")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_collectors")

# Desactiver les logs trop verbeux
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


COLLECTORS = [
    ("Assemblee Nationale", "legix.collectors.assemblee", "AssembleeCollector"),
    ("Senat", "legix.collectors.senat", "SenatCollector"),
    ("JORF", "legix.collectors.jorf", "JORFCollector"),
    ("EUR-Lex", "legix.collectors.eurlex", "EurLexCollector"),
    ("Regulateurs", "legix.collectors.regulateurs", "RegulateursCollector"),
    ("Presse", "legix.collectors.presse", "PresseCollector"),
    ("Think Tanks", "legix.collectors.think_tanks", "ThinkTankCollector"),
    ("Cour des Comptes", "legix.collectors.cour_comptes", "CourComptesCollector"),
    ("Inspections", "legix.collectors.inspections", "InspectionsCollector"),
    ("Scrutins", "legix.collectors.scrutins", "ScrutinsCollector"),
    ("HATVP", "legix.collectors.hatvp", "HATVPCollector"),
    ("ONG", "legix.collectors.ong", "ONGCollector"),
    ("Consultations", "legix.collectors.consultations", "ConsultationsCollector"),
    ("Federations", "legix.collectors.federations", "FederationsCollector"),
]

# Les collecteurs lourds (API externes, possible timeout)
HEAVY_COLLECTORS = [
    ("Europarl", "legix.collectors.europarl", "EuroparlCollector"),
    ("Europarl Intel", "legix.collectors.europarl_intelligence", "EuroparlIntelligenceCollector"),
    ("Senat Acteurs", "legix.collectors.senat_acteurs", "SenatActeursCollector"),
]


async def run_one(db, name: str, module_path: str, class_name: str) -> dict:
    """Lance un collecteur et retourne ses stats."""
    import importlib
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        collector = cls()
        t0 = time.time()
        stats = await collector.collect(db)
        elapsed = time.time() - t0
        new = stats.get("new", 0)
        skipped = stats.get("skipped", 0)
        errors = stats.get("errors", 0)
        status = "OK" if errors == 0 else f"WARN ({errors} err)"
        logger.info(
            "  %-20s %s  +%d new  %d skip  %.1fs",
            name, status, new, skipped, elapsed,
        )
        return {"name": name, "new": new, "skipped": skipped, "errors": errors, "time": elapsed}
    except Exception as e:
        logger.error("  %-20s FAIL: %s", name, str(e)[:100])
        return {"name": name, "new": 0, "skipped": 0, "errors": 1, "time": 0, "error": str(e)[:200]}


async def main():
    from legix.core.database import async_session, init_db

    await init_db()
    logger.info("=== LegiX — Lancement des collecteurs ===\n")

    results = []
    async with async_session() as db:
        # Collecteurs principaux (sequentiels pour eviter de surcharger)
        logger.info("--- Collecteurs principaux (%d) ---", len(COLLECTORS))
        for name, mod, cls in COLLECTORS:
            r = await run_one(db, name, mod, cls)
            results.append(r)

        # Collecteurs lourds (optionnels)
        logger.info("\n--- Collecteurs lourds (%d) ---", len(HEAVY_COLLECTORS))
        for name, mod, cls in HEAVY_COLLECTORS:
            r = await run_one(db, name, mod, cls)
            results.append(r)

    # Resume
    total_new = sum(r["new"] for r in results)
    total_errors = sum(r["errors"] for r in results)
    total_time = sum(r["time"] for r in results)
    ok_count = sum(1 for r in results if r["errors"] == 0)

    logger.info("\n=== RESUME ===")
    logger.info("Collecteurs: %d/%d OK", ok_count, len(results))
    logger.info("Total: +%d nouveaux documents", total_new)
    logger.info("Erreurs: %d", total_errors)
    logger.info("Temps total: %.1fs", total_time)

    # Detail par collecteur
    logger.info("\n--- Detail ---")
    for r in sorted(results, key=lambda x: x["new"], reverse=True):
        marker = "OK" if r["errors"] == 0 else "ERR"
        logger.info("  [%s] %-20s +%d  (%.1fs)", marker, r["name"], r["new"], r["time"])

    # Stats DB
    import sqlite3
    try:
        conn = sqlite3.connect("/Users/emmanuelblezes/data/legix.db")
        for table in ["textes", "amendements", "acteurs", "signals", "anticipation_reports", "press_articles", "stakeholder_profiles", "scrutin_votes"]:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count > 0:
                    logger.info("  DB %-25s %d rows", table, count)
            except Exception:
                pass
        conn.close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
