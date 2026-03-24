"""Collecteur Scrutins — votes nominatifs de l'Assemblée nationale.

Source : Open data AN — fichiers XML des scrutins publics.
Chaque scrutin contient le vote nominatif de chaque député.

URL : https://data.assemblee-nationale.fr/travaux-parlementaires/votes
"""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import ScrutinVote

logger = logging.getLogger(__name__)

# API JSON des scrutins (plus simple que le XML complet)
SCRUTINS_API = "https://www2.assemblee-nationale.fr/scrutins/liste/(legislature)/17/(type)/tous/(idDossier)/tous"
# Open data direct
SCRUTINS_JSON_URL = "https://www.assemblee-nationale.fr/dyn/opendata/SCRUTINS.json"


class ScrutinsCollector(BaseCollector):
    """Collecteur des scrutins publics de l'Assemblée nationale."""

    def get_source_name(self) -> str:
        return "scrutins"

    async def collect(self, db: AsyncSession) -> dict:
        stats = self._empty_stats()

        # Tenter l'API JSON des scrutins
        try:
            data = await self._fetch_json(SCRUTINS_JSON_URL)
            if data and isinstance(data, dict):
                scrutins = data.get("scrutins", {}).get("scrutin", [])
                if isinstance(scrutins, dict):
                    scrutins = [scrutins]

                for scrutin in scrutins[-50:]:  # 50 derniers scrutins
                    await self._process_scrutin(db, stats, scrutin)

                await db.commit()
        except Exception as e:
            logger.warning("[scrutins] Collecte échouée: %s", e)
            stats["errors"] += 1

        if stats["new"] > 0:
            logger.info("[scrutins] %d nouveaux votes collectés", stats["new"])
        return stats

    async def _process_scrutin(self, db: AsyncSession, stats: dict, scrutin: dict):
        """Traite un scrutin et extrait les votes nominatifs."""
        numero = scrutin.get("numero")
        if not numero:
            return

        numero_int = int(numero) if isinstance(numero, str) else numero

        # Vérifier si déjà traité
        existing = await db.execute(
            select(ScrutinVote).where(ScrutinVote.scrutin_numero == numero_int).limit(1)
        )
        if existing.scalar_one_or_none():
            return

        titre = scrutin.get("titre", scrutin.get("objet", {}).get("libelle", ""))
        date_str = scrutin.get("dateScrutin", "")
        scrutin_date = None
        if date_str:
            try:
                scrutin_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                pass

        scrutin_type = scrutin.get("typeVote", {}).get("libelleTypeVote", "ordinaire")

        # Résultats globaux
        synthese = scrutin.get("syntheseVote", {})
        nombre_votants = _to_int(synthese.get("nombreVotants"))
        pour_total = _to_int(synthese.get("nbresSuffExprimesGroupe", {}).get("pour") if isinstance(synthese.get("nbresSuffExprimesGroupe"), dict) else synthese.get("decompte", {}).get("pour"))
        contre_total = _to_int(synthese.get("decompte", {}).get("contre"))
        abstentions_total = _to_int(synthese.get("decompte", {}).get("abstentions"))

        # Résultat
        sort_code = scrutin.get("sort", {}).get("code", "")
        resultat = "adopte" if sort_code == "adopté" or sort_code == "adopte" else "rejete"

        # Extraire les votes par groupe
        ventilation = scrutin.get("ventilationVotes", {}).get("organe", {}).get("groupes", {}).get("groupe", [])
        if isinstance(ventilation, dict):
            ventilation = [ventilation]

        for groupe_data in ventilation:
            groupe_ref = groupe_data.get("organeRef", "")
            decompte = groupe_data.get("vote", {}).get("decompteNominatif", {})

            for position_key, position_label in [
                ("pours", "pour"),
                ("contres", "contre"),
                ("abstentions", "abstention"),
                ("nonVotants", "non_votant"),
            ]:
                votants = decompte.get(position_key, {}).get("votant", [])
                if isinstance(votants, dict):
                    votants = [votants]

                for votant in votants:
                    acteur_uid = votant.get("acteurRef", "")
                    if not acteur_uid:
                        continue

                    vote = ScrutinVote(
                        scrutin_numero=numero_int,
                        scrutin_titre=titre[:500] if titre else "",
                        scrutin_date=scrutin_date,
                        scrutin_type=scrutin_type,
                        acteur_uid=acteur_uid,
                        position=position_label,
                        groupe_ref=groupe_ref or None,
                        nombre_votants=nombre_votants,
                        pour_total=pour_total,
                        contre_total=contre_total,
                        abstentions_total=abstentions_total,
                        resultat=resultat,
                        source="assemblee",
                    )
                    db.add(vote)
                    stats["new"] += 1
                    stats["new_uids"]["scrutin_vote"].append(
                        f"{numero_int}-{acteur_uid}"
                    )

        stats["by_type"]["scrutin"] += 1


def _to_int(val) -> int | None:
    """Conversion sûre en int."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
