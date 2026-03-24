"""Intelligence Parlement europeen — analyse des votes par MEP et par groupe.

Construit les statistiques de vote pour chaque eurodepute :
- Taux d'alignement avec la majorite
- Positions par theme (via les sujets OEIL des votes)
- Frequence de vote (participation)
- Alignement avec chaque groupe

Utilise HowTheyVote comme source principale.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import Acteur, Texte

logger = logging.getLogger(__name__)

HTV_API = "https://howtheyvote.eu/api"


class EuroparlIntelligenceCollector(BaseCollector):
    """Collecte l'intelligence de vote PE — stats par MEP et par groupe."""

    def get_source_name(self) -> str:
        return "europarl"

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte les votes recents et calcule les stats par MEP."""
        stats = self._empty_stats()

        # Recuperer les votes deja en base
        result = await db.execute(
            select(Texte).where(
                Texte.source == "europarl",
                Texte.type_code == "VOTE_EU",
            )
        )
        votes_in_db = result.scalars().all()

        if not votes_in_db:
            logger.info("[ep_intel] Pas de votes en base, lancer d'abord EuroparlCollector")
            return stats

        # Construire les stats par MEP
        mep_stats: dict[int, dict] = defaultdict(lambda: {
            "total_votes": 0,
            "for": 0,
            "against": 0,
            "abstention": 0,
            "with_majority": 0,
            "themes": defaultdict(lambda: {"for": 0, "against": 0, "total": 0}),
        })

        # Pour chaque vote, recuperer les positions individuelles
        processed = 0
        for vote_texte in votes_in_db:
            vote_id = vote_texte.uid.replace("EP-VOTE-", "")

            # Recuperer le detail du vote
            detail = await self._fetch_json(f"{HTV_API}/votes/{vote_id}")
            if not detail or not detail.get("member_votes"):
                continue

            result_vote = detail.get("result", "")
            majority_position = "FOR" if result_vote == "ADOPTED" else "AGAINST"

            # Themes du vote (sujets OEIL)
            topics = detail.get("topics", [])
            topic_labels = [t.get("label", "") for t in topics if t.get("label")]

            for mv in detail.get("member_votes", []):
                member = mv.get("member", {})
                htv_id = member.get("id")
                position = mv.get("position", "")

                if not htv_id or position == "DID_NOT_VOTE":
                    continue

                s = mep_stats[htv_id]
                s["total_votes"] += 1

                if position == "FOR":
                    s["for"] += 1
                elif position == "AGAINST":
                    s["against"] += 1
                elif position == "ABSTENTION":
                    s["abstention"] += 1

                if position == majority_position:
                    s["with_majority"] += 1

                # Stats par theme
                for topic in topic_labels:
                    s["themes"][topic]["total"] += 1
                    if position == "FOR":
                        s["themes"][topic]["for"] += 1
                    elif position == "AGAINST":
                        s["themes"][topic]["against"] += 1

            processed += 1

        logger.info("[ep_intel] %d votes analyses, %d MEPs", processed, len(mep_stats))

        # Stocker les stats sur chaque MEP dans le champ collaborateurs (JSON)
        updated = 0
        for htv_id, ms in mep_stats.items():
            uid = f"EP-{htv_id}"
            acteur = await db.get(Acteur, uid)
            if not acteur:
                continue

            # Calculer les taux
            total = ms["total_votes"]
            if total == 0:
                continue

            participation_rate = round(total / processed, 3) if processed > 0 else 0
            majority_rate = round(ms["with_majority"] / total, 3)

            # Top themes
            top_themes = sorted(
                ms["themes"].items(),
                key=lambda x: x[1]["total"],
                reverse=True,
            )[:8]

            intel = {
                "htv_id": htv_id,
                "country_code": "",  # sera preservé si deja present
                "group_code": "",
                "vote_stats": {
                    "total_votes": total,
                    "for": ms["for"],
                    "against": ms["against"],
                    "abstention": ms["abstention"],
                    "participation_rate": participation_rate,
                    "majority_alignment": majority_rate,
                },
                "top_themes": [
                    {
                        "theme": theme,
                        "total": data["total"],
                        "for": data["for"],
                        "against": data["against"],
                        "for_rate": round(data["for"] / data["total"], 3) if data["total"] > 0 else 0,
                    }
                    for theme, data in top_themes
                ],
            }

            # Preserver les donnees existantes
            existing_data = {}
            if acteur.collaborateurs:
                try:
                    existing_data = json.loads(acteur.collaborateurs)
                except (json.JSONDecodeError, TypeError):
                    pass

            if isinstance(existing_data, dict):
                intel["country_code"] = existing_data.get("country_code", "")
                intel["group_code"] = existing_data.get("group_code", "")

            acteur.collaborateurs = json.dumps(intel, ensure_ascii=False)
            acteur.updated_at = datetime.utcnow()
            updated += 1

        await db.commit()
        stats["updated"] = updated
        logger.info("[ep_intel] Stats de vote mises a jour pour %d MEPs", updated)

        return stats
