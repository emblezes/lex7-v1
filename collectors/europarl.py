"""Collecteur Parlement europeen — MEPs, votes, procedures.

Sources :
- EP Open Data API v2 : eurodeputes (720 MEPs), organisations, procedures
- HowTheyVote.eu API : votes nominatifs avec position de chaque MEP

Tout est accessible sans authentification.
"""

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import Acteur, Organe

logger = logging.getLogger(__name__)

EP_API = "https://data.europarl.europa.eu/api/v2"
HTV_API = "https://howtheyvote.eu/api"

# Mapping groupes PE → codes courts
EP_GROUP_SHORTS = {
    "Group of the European People's Party (Christian Democrats)": "EPP",
    "European People's Party": "EPP",
    "Group of the Progressive Alliance of Socialists and Democrats in the European Parliament": "S&D",
    "Progressive Alliance of Socialists and Democrats": "S&D",
    "Renew Europe Group": "Renew",
    "Renew Europe": "Renew",
    "Group of the Greens/European Free Alliance": "Greens/EFA",
    "Greens/European Free Alliance": "Greens/EFA",
    "Identity and Democracy Group": "ID",
    "Identity and Democracy": "ID",
    "European Conservatives and Reformists Group": "ECR",
    "European Conservatives and Reformists": "ECR",
    "The Left group in the European Parliament - GUE/NGL": "GUE/NGL",
    "The Left": "GUE/NGL",
    "Non-attached Members": "NI",
    "Non-attached": "NI",
    "Patriots for Europe": "PfE",
    "Europe of Sovereign Nations": "ESN",
}


class EuroparlCollector(BaseCollector):
    """Collecteur Parlement europeen — MEPs + groupes + votes."""

    def get_source_name(self) -> str:
        return "europarl"

    async def collect(self, db: AsyncSession) -> dict:
        """Ingere les MEPs et leurs groupes."""
        stats = self._empty_stats()

        # Phase 1 : Groupes politiques PE
        groupes_created = await self._collect_groupes(db)
        stats["by_type"]["organe"] = groupes_created

        # Phase 2 : Eurodeputes
        meps_created, meps_updated = await self._collect_meps(db)
        stats["new"] = meps_created
        stats["updated"] = meps_updated

        await db.commit()

        logger.info(
            "[europarl] %d MEPs nouveaux, %d mis a jour, %d groupes",
            meps_created, meps_updated, groupes_created,
        )
        return stats

    async def _collect_groupes(self, db: AsyncSession) -> int:
        """Cree les groupes politiques du PE."""
        created = 0
        # Groupes connus du terme 10
        known_groups = [
            ("EPP", "Group of the European People's Party"),
            ("S&D", "Progressive Alliance of Socialists and Democrats"),
            ("Renew", "Renew Europe"),
            ("Greens/EFA", "Greens/European Free Alliance"),
            ("ECR", "European Conservatives and Reformists"),
            ("ID", "Identity and Democracy"),
            ("GUE/NGL", "The Left in the European Parliament"),
            ("NI", "Non-attached Members"),
            ("PfE", "Patriots for Europe"),
            ("ESN", "Europe of Sovereign Nations"),
        ]
        for code, libelle in known_groups:
            uid = f"EP-GP-{code}"
            existing = await db.get(Organe, uid)
            if not existing:
                organe = Organe(
                    uid=uid,
                    type_code="GP",
                    type_libelle="Groupe politique PE",
                    libelle=libelle,
                    libelle_court=code,
                    source="europarl",
                )
                db.add(organe)
                created += 1
        await db.flush()
        return created

    async def _collect_meps(self, db: AsyncSession) -> tuple[int, int]:
        """Ingere les MEPs depuis l'API EP Open Data + HowTheyVote pour les groupes."""
        # Methode : utiliser HowTheyVote car il donne directement nom+pays+groupe
        # en un seul appel (le detail EP API necessite 720 appels individuels)

        # Recuperer un vote recent pour avoir la liste complete des MEPs
        data = await self._fetch_json(f"{HTV_API}/votes?page=1&is_main=true")
        if not data or not data.get("results"):
            logger.warning("[europarl] Pas de votes HowTheyVote")
            return 0, 0

        # Prendre le vote le plus recent avec des member_votes
        latest_vote_id = data["results"][0]["id"]
        vote_detail = await self._fetch_json(f"{HTV_API}/votes/{latest_vote_id}")
        if not vote_detail or not vote_detail.get("member_votes"):
            return 0, 0

        member_votes = vote_detail["member_votes"]
        logger.info("[europarl] %d MEPs dans le vote %s", len(member_votes), latest_vote_id)

        created = 0
        updated = 0

        # Index des groupes PE
        groupe_index = {}
        result = await db.execute(
            select(Organe).where(Organe.source == "europarl", Organe.type_code == "GP")
        )
        for org in result.scalars():
            groupe_index[org.libelle_court] = org.uid

        for mv in member_votes:
            member = mv.get("member", {})
            htv_id = member.get("id")
            if not htv_id:
                continue

            uid = f"EP-{htv_id}"
            first_name = member.get("first_name", "")
            last_name = member.get("last_name", "")
            country = (member.get("country") or {}).get("label", "")
            country_code = (member.get("country") or {}).get("iso_alpha_2", "")
            group_info = member.get("group") or {}
            group_code = group_info.get("code", "")
            group_label = group_info.get("label", "")

            # Resoudre le groupe PE
            groupe_uid = groupe_index.get(group_code)
            if not groupe_uid:
                # Tenter un match sur le label
                short = EP_GROUP_SHORTS.get(group_label, group_code)
                groupe_uid = groupe_index.get(short)

            existing = await db.get(Acteur, uid)
            if existing:
                existing.groupe_politique_ref = groupe_uid
                existing.adresse_circo = country
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                acteur = Acteur(
                    uid=uid,
                    civilite="",
                    prenom=first_name,
                    nom=last_name,
                    groupe_politique_ref=groupe_uid,
                    profession=f"Eurodepute ({country})",
                    adresse_circo=country,
                    email=f"{first_name.lower()}.{last_name.lower()}@europarl.europa.eu".replace(" ", ""),
                    site_web=f"https://www.europarl.europa.eu/meps/en/{htv_id}",
                    source="europarl",
                    collaborateurs=json.dumps({
                        "htv_id": htv_id,
                        "country_code": country_code,
                        "group_code": group_code,
                    }),
                )
                db.add(acteur)
                created += 1

        return created, updated

    async def collect_recent_votes(self, db: AsyncSession, pages: int = 3) -> dict:
        """Collecte les votes recents et stocke les resultats.

        Les votes sont stockes comme Texte source=europarl avec le detail
        des positions par groupe dans auteur_texte (JSON).
        """
        from legix.core.models import Texte

        stats = self._empty_stats()

        for page in range(1, pages + 1):
            data = await self._fetch_json(
                f"{HTV_API}/votes?page={page}&is_main=true"
            )
            if not data or not data.get("results"):
                break

            for vote_summary in data["results"]:
                vote_id = vote_summary["id"]
                uid = f"EP-VOTE-{vote_id}"

                if await self._is_seen(db, uid):
                    stats["skipped"] += 1
                    continue

                # Recuperer le detail
                detail = await self._fetch_json(f"{HTV_API}/votes/{vote_id}")
                if not detail:
                    continue

                titre = detail.get("display_title", "")
                procedure = detail.get("procedure") or {}
                result = detail.get("result", "")
                timestamp = detail.get("timestamp", "")

                # Agreger les votes par groupe
                group_votes = {}
                for mv in detail.get("member_votes", []):
                    group = (mv.get("member", {}).get("group") or {}).get("code", "NI")
                    position = mv.get("position", "DID_NOT_VOTE")
                    if group not in group_votes:
                        group_votes[group] = {"for": 0, "against": 0, "abstention": 0, "dnv": 0}
                    if position == "FOR":
                        group_votes[group]["for"] += 1
                    elif position == "AGAINST":
                        group_votes[group]["against"] += 1
                    elif position == "ABSTENTION":
                        group_votes[group]["abstention"] += 1
                    else:
                        group_votes[group]["dnv"] += 1

                # Stocker
                date_vote = None
                if timestamp:
                    try:
                        date_vote = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    except ValueError:
                        pass

                texte = Texte(
                    uid=uid,
                    denomination=f"Vote PE — {result}",
                    titre=titre[:500] if titre else "",
                    titre_court=titre[:120] if titre else "",
                    type_code="VOTE_EU",
                    type_libelle="Vote Parlement europeen",
                    date_depot=date_vote,
                    date_publication=date_vote,
                    source="europarl",
                    url_source=f"https://howtheyvote.eu/votes/{vote_id}",
                    auteur_texte=json.dumps({
                        "result": result,
                        "procedure": procedure,
                        "group_votes": group_votes,
                        "nb_members": len(detail.get("member_votes", [])),
                    }, ensure_ascii=False),
                )
                db.add(texte)
                await self._mark_seen(db, uid, "vote_eu", uid)
                stats["new"] += 1
                stats["new_uids"]["texte"].append(uid)

            await db.commit()

        if stats["new"] > 0:
            logger.info("[europarl] %d votes collectes", stats["new"])

        return stats
