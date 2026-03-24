"""Pipeline proactif — collect → enrich → score → detect → trigger (par texte).

Orchestre toute la chaîne de traitement automatisé de LegiX.
Appelé périodiquement par le scheduler (toutes les 5 min).

Phase 2 : le trigger est désormais par texte, pas par amendement individuel.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from legix.collectors.assemblee import AssembleeCollector
from legix.collectors.senat import SenatCollector
from legix.collectors.jorf import JORFCollector
from legix.collectors.eurlex import EurLexCollector
from legix.collectors.europarl import EuroparlCollector
from legix.collectors.europarl_intelligence import EuroparlIntelligenceCollector
from legix.collectors.regulateurs import RegulateursCollector
from legix.collectors.presse import PresseCollector
from legix.collectors.senat_acteurs import SenatActeursCollector
# Collecteurs anticipation (Phase 1)
from legix.collectors.think_tanks import ThinkTankCollector
from legix.collectors.cour_comptes import CourComptesCollector
from legix.collectors.inspections import InspectionsCollector
from legix.collectors.scrutins import ScrutinsCollector
# Collecteurs Phase 2
from legix.collectors.hatvp import HATVPCollector
from legix.collectors.ong import ONGCollector
from legix.collectors.consultations import ConsultationsCollector
from legix.collectors.federations import FederationsCollector
from legix.core.database import async_session
from legix.core.models import (
    Amendement,
    PipelineRun,
    Texte,
)
from legix.enrichment.pipeline import enrich
from legix.enrichment.scoring import batch_compute_scores
from legix.enrichment.signals import detect_all

logger = logging.getLogger(__name__)

# Mapping type → modèle ORM
MODEL_MAP = {
    "texte": Texte,
    "amendement": Amendement,
}


async def collect_and_process():
    """Pipeline complet : collecte, enrichissement, scoring, signaux, trigger par texte."""
    async with async_session() as db:
        run = PipelineRun(run_type="full", status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        stats = {
            "collected": 0,
            "enriched": 0,
            "scored": 0,
            "signals": 0,
            "followups_created": 0,
            "briefs_created": 0,
        }

        try:
            # 1. Collecter depuis toutes les sources
            new_uids: dict[str, list] = defaultdict(list)

            # 1a. Assemblee nationale
            try:
                an_stats = await AssembleeCollector().collect(db)
                stats["collected"] += an_stats.get("new", 0)
                for k, v in an_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte AN echouee: %s", e)

            # 1b. Senat (textes + amendements)
            try:
                senat_stats = await SenatCollector().collect(db)
                stats["collected"] += senat_stats.get("new", 0)
                for k, v in senat_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte Senat echouee: %s", e)

            # 1b2. Senateurs (fiches structurees, 1x/jour suffit)
            try:
                await SenatActeursCollector().collect(db)
            except Exception as e:
                logger.warning("Collecte senateurs echouee: %s", e)

            # 1c. JORF (si configure)
            try:
                jorf_stats = await JORFCollector().collect(db)
                stats["collected"] += jorf_stats.get("new", 0)
                for k, v in jorf_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte JORF echouee: %s", e)

            # 1d. EUR-Lex (legislation EU)
            try:
                eu_stats = await EurLexCollector().collect(db)
                stats["collected"] += eu_stats.get("new", 0)
                for k, v in eu_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte EUR-Lex echouee: %s", e)

            # 1e. Parlement europeen (MEPs + votes)
            try:
                ep_collector = EuroparlCollector()
                await ep_collector.collect(db)  # MEPs + groupes
                ep_votes = await ep_collector.collect_recent_votes(db, pages=2)
                stats["collected"] += ep_votes.get("new", 0)
                for k, v in ep_votes.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte Europarl echouee: %s", e)

            # 1e2. Intelligence PE (stats de vote par MEP)
            try:
                await EuroparlIntelligenceCollector().collect(db)
            except Exception as e:
                logger.warning("Intelligence Europarl echouee: %s", e)

            # 1f. Regulateurs (CNIL, AMF, ARCEP, HAS, etc.)
            try:
                reg_stats = await RegulateursCollector().collect(db)
                stats["collected"] += reg_stats.get("new", 0)
                for k, v in reg_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte regulateurs echouee: %s", e)

            # 1g. Presse specialisee
            try:
                presse_stats = await PresseCollector().collect(db)
                stats["collected"] += presse_stats.get("new", 0)
                for k, v in presse_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte presse echouee: %s", e)

            # --- Collecteurs anticipation (Phase 1) ---

            # 1h. Think tanks
            try:
                tt_stats = await ThinkTankCollector().collect(db)
                stats["collected"] += tt_stats.get("new", 0)
                for k, v in tt_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte think tanks echouee: %s", e)

            # 1i. Cour des Comptes
            try:
                cc_stats = await CourComptesCollector().collect(db)
                stats["collected"] += cc_stats.get("new", 0)
                for k, v in cc_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte Cour des Comptes echouee: %s", e)

            # 1j. Corps d'inspection (IGF, IGAS, IGA)
            try:
                insp_stats = await InspectionsCollector().collect(db)
                stats["collected"] += insp_stats.get("new", 0)
                for k, v in insp_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte inspections echouee: %s", e)

            # 1k. Scrutins (votes nominatifs)
            try:
                scr_stats = await ScrutinsCollector().collect(db)
                stats["collected"] += scr_stats.get("new", 0)
                for k, v in scr_stats.get("new_uids", {}).items():
                    new_uids[k].extend(v)
            except Exception as e:
                logger.warning("Collecte scrutins echouee: %s", e)

            # --- Collecteurs Phase 2 ---

            # 1l. HATVP (representants d'interets)
            try:
                hatvp_stats = await HATVPCollector().collect(db)
                stats["collected"] += hatvp_stats.get("new", 0)
            except Exception as e:
                logger.warning("Collecte HATVP echouee: %s", e)

            # 1m. ONG et societe civile
            try:
                ong_stats = await ONGCollector().collect(db)
                stats["collected"] += ong_stats.get("new", 0)
            except Exception as e:
                logger.warning("Collecte ONG echouee: %s", e)

            # 1n. Consultations publiques
            try:
                consult_stats = await ConsultationsCollector().collect(db)
                stats["collected"] += consult_stats.get("new", 0)
            except Exception as e:
                logger.warning("Collecte consultations echouee: %s", e)

            # 1o. Federations professionnelles
            try:
                fed_stats = await FederationsCollector().collect(db)
                stats["collected"] += fed_stats.get("new", 0)
            except Exception as e:
                logger.warning("Collecte federations echouee: %s", e)

            logger.info(
                "Pipeline: %d nouveaux documents collectés",
                stats["collected"],
            )

            # 2. Enrichir les nouveaux documents (themes + resume IA)
            for doc_type in ["texte", "amendement"]:
                model = MODEL_MAP.get(doc_type)
                if not model:
                    continue
                for uid in new_uids.get(doc_type, []):
                    doc = await db.get(model, uid)
                    if doc and not doc.themes:
                        try:
                            result = await asyncio.to_thread(enrich, doc)
                            doc.themes = result.get("themes")
                            doc.resume_ia = result.get("resume_ia")
                            # Pour presse/regulateur, stocker les entites dans auteur_texte
                            if result.get("entities") and hasattr(doc, "source") and doc.source in ("presse", "regulateur"):
                                doc.auteur_texte = result["entities"]
                            stats["enriched"] += 1
                        except Exception as e:
                            logger.warning("Enrichissement échoué pour %s: %s", uid, e)
                await db.commit()

            # 2b. Intelligence presse — lier articles aux textes suivis
            try:
                from legix.services.press_intelligence import process_press_articles
                press_matches = await process_press_articles(db)
                if press_matches > 0:
                    logger.info("Presse: %d articles lies a des textes suivis", press_matches)
            except Exception as e:
                logger.warning("Intelligence presse echouee: %s", e)

            # 3. Scorer les amendements sans score
            scored = await batch_compute_scores(db)
            stats["scored"] = scored

            # 4. Détecter les signaux faibles
            signals_count = await detect_all(db)
            stats["signals"] = signals_count

            # 5. Trigger par texte (pas par amendement individuel)
            from legix.agents.trigger import (
                on_new_texte,
                on_new_amendments_for_texte,
            )

            # 5a. Nouveaux textes enrichis
            for uid in new_uids.get("texte", []):
                doc = await db.get(Texte, uid)
                if doc and doc.themes:
                    try:
                        result = await on_new_texte(db, doc)
                        stats["followups_created"] += result.get("followups_created", 0)
                        stats["briefs_created"] += result.get("briefs_created", 0)
                    except Exception as e:
                        logger.warning("Trigger texte échoué pour %s: %s", uid, e)

            # 5b. Grouper les nouveaux amendements par texte_ref
            texte_new_amdts: dict[str, list[Amendement]] = defaultdict(list)
            for uid in new_uids.get("amendement", []):
                doc = await db.get(Amendement, uid)
                if doc and doc.themes and doc.texte_ref:
                    texte_new_amdts[doc.texte_ref].append(doc)

            # 5c. Trigger par groupe de texte (1 brief par texte, pas N alertes)
            for texte_uid, amdts in texte_new_amdts.items():
                try:
                    result = await on_new_amendments_for_texte(db, texte_uid, amdts)
                    stats["followups_created"] += result.get("followups_created", 0)
                    stats["briefs_created"] += result.get("briefs_updated", 0)
                except Exception as e:
                    logger.warning(
                        "Trigger amendements échoué pour texte %s: %s",
                        texte_uid, e,
                    )

            # Marquer le run comme terminé
            run.status = "completed"
            run.stats = json.dumps(stats)
            run.completed_at = datetime.utcnow()
            await db.commit()

            logger.info(
                "Pipeline terminé: %d collectés, %d enrichis, %d scorés, "
                "%d signaux, %d followups, %d briefs",
                stats["collected"], stats["enriched"], stats["scored"],
                stats["signals"], stats["followups_created"],
                stats["briefs_created"],
            )

        except Exception as e:
            logger.exception("Erreur pipeline: %s", e)
            run.status = "failed"
            run.error_message = str(e)[:500]
            run.completed_at = datetime.utcnow()
            await db.commit()
