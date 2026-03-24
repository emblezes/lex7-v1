"""Collecteur Senateurs — ingestion structuree depuis l'API JSON du Senat.

Ingere les 348 senateurs et leurs groupes politiques dans les tables
Acteur et Organe, puis resout les liens texte libre → FK
sur les amendements existants.

Source : https://www.senat.fr/api-senat/senateurs.json
"""

import json
import logging
import re
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import Acteur, Amendement, Organe

logger = logging.getLogger(__name__)

SENAT_API_URL = "https://www.senat.fr/api-senat/senateurs.json"


class SenatActeursCollector(BaseCollector):
    """Ingere les senateurs et groupes senatoriaux."""

    def get_source_name(self) -> str:
        return "senat"

    async def collect(self, db: AsyncSession) -> dict:
        """Ingere les senateurs depuis l'API JSON du Senat."""
        stats = self._empty_stats()

        data = await self._fetch_json(SENAT_API_URL)
        if not data:
            logger.error("[senat_acteurs] Impossible de telecharger l'API senateurs")
            return stats

        senateurs = data if isinstance(data, list) else data.get("senateurs", [])
        logger.info("[senat_acteurs] %d senateurs dans l'API", len(senateurs))

        # Phase 1 : Creer/MAJ les groupes senatoriaux
        groupes_vus: dict[str, str] = {}  # code → uid
        for s in senateurs:
            groupe = s.get("groupe")
            if not groupe or not groupe.get("code"):
                continue
            code = groupe["code"]
            if code in groupes_vus:
                continue

            uid = f"SENAT-GP-{code}"
            groupes_vus[code] = uid

            existing = await db.get(Organe, uid)
            if existing:
                existing.libelle = groupe.get("libelle", "")
                existing.libelle_court = code
            else:
                organe = Organe(
                    uid=uid,
                    type_code="GP",
                    type_libelle="Groupe politique",
                    libelle=groupe.get("libelle", ""),
                    libelle_court=code,
                    source="senat",
                )
                db.add(organe)
                stats["by_type"]["organe"] = stats["by_type"].get("organe", 0) + 1

        # Phase 1b : Creer/MAJ les commissions senatoriales
        commissions_vues: dict[str, str] = {}
        for s in senateurs:
            for org in s.get("organismes", []):
                if org.get("type") != "COMMISSION":
                    continue
                code = org["code"]
                if code in commissions_vues:
                    continue
                uid = f"SENAT-COM-{code}"
                commissions_vues[code] = uid

                existing = await db.get(Organe, uid)
                if not existing:
                    organe = Organe(
                        uid=uid,
                        type_code="COMPER",
                        type_libelle="Commission permanente",
                        libelle=org.get("libelle", ""),
                        libelle_court=code,
                        source="senat",
                    )
                    db.add(organe)

        await db.flush()
        logger.info(
            "[senat_acteurs] %d groupes, %d commissions",
            len(groupes_vus), len(commissions_vues),
        )

        # Phase 2 : Creer/MAJ les senateurs
        new_count = 0
        updated_count = 0
        for s in senateurs:
            matricule = s.get("matricule", "")
            if not matricule:
                continue

            uid = f"SENAT-{matricule}"
            groupe_code = (s.get("groupe") or {}).get("code", "")
            groupe_uid = groupes_vus.get(groupe_code)

            # Commission principale
            commission_uid = None
            for org in s.get("organismes", []):
                if org.get("type") == "COMMISSION":
                    commission_uid = commissions_vues.get(org["code"])
                    break

            # Collaborateurs / organismes
            organismes_json = json.dumps(
                s.get("organismes", []), ensure_ascii=False
            )

            existing = await db.get(Acteur, uid)
            if existing:
                # MAJ
                existing.nom = s.get("nom", "")
                existing.prenom = s.get("prenom", "")
                existing.civilite = s.get("civilite", "")
                existing.groupe_politique_ref = groupe_uid
                existing.twitter = s.get("twitter", "")
                existing.facebook = s.get("facebook", "")
                existing.site_web = f"https://www.senat.fr{s['url']}" if s.get("url") else ""
                existing.profession = (s.get("categorieProfessionnelle") or {}).get("libelle", "")
                existing.adresse_circo = (s.get("circonscription") or {}).get("libelle", "")
                existing.collaborateurs = organismes_json
                existing.updated_at = datetime.utcnow()
                updated_count += 1
            else:
                acteur = Acteur(
                    uid=uid,
                    civilite=s.get("civilite", ""),
                    prenom=s.get("prenom", ""),
                    nom=s.get("nom", ""),
                    groupe_politique_ref=groupe_uid,
                    profession=(s.get("categorieProfessionnelle") or {}).get("libelle", ""),
                    twitter=s.get("twitter", ""),
                    facebook=s.get("facebook", ""),
                    site_web=f"https://www.senat.fr{s['url']}" if s.get("url") else "",
                    adresse_circo=(s.get("circonscription") or {}).get("libelle", ""),
                    collaborateurs=organismes_json,
                    source="senat",
                )
                db.add(acteur)
                stats["new"] += 1
                new_count += 1

        await db.commit()
        logger.info(
            "[senat_acteurs] %d nouveaux, %d mis a jour",
            new_count, updated_count,
        )

        # Phase 3 : Resoudre les liens texte libre → FK sur les amendements
        resolved = await self._resolve_amendment_links(db)
        logger.info("[senat_acteurs] %d amendements lies a leur auteur", resolved)

        stats["updated"] = updated_count
        return stats

    async def _resolve_amendment_links(self, db: AsyncSession) -> int:
        """Resout auteur_nom → auteur_ref et groupe_nom → groupe_ref
        pour les amendements Senat sans FK."""
        # Charger tous les senateurs
        result = await db.execute(
            select(Acteur).where(Acteur.source == "senat")
        )
        senateurs = result.scalars().all()

        # Index par nom (normalise)
        nom_index: dict[str, Acteur] = {}
        for s in senateurs:
            # Cles de recherche : "Nom", "Prenom Nom", "M. Nom", "Mme Nom"
            nom_norm = _normalize(s.nom)
            prenom_nom = _normalize(f"{s.prenom} {s.nom}")
            nom_index[nom_norm] = s
            nom_index[prenom_nom] = s
            if s.civilite:
                civ_nom = _normalize(f"{s.civilite} {s.nom}")
                nom_index[civ_nom] = s

        # Charger les groupes senatoriaux
        result = await db.execute(
            select(Organe).where(Organe.source == "senat", Organe.type_code == "GP")
        )
        groupes = result.scalars().all()
        groupe_index: dict[str, Organe] = {}
        for g in groupes:
            groupe_index[_normalize(g.libelle)] = g
            groupe_index[_normalize(g.libelle_court)] = g

        # Amendements Senat sans auteur_ref
        result = await db.execute(
            select(Amendement).where(
                Amendement.source == "senat",
                Amendement.auteur_ref.is_(None),
                Amendement.auteur_nom.isnot(None),
            )
        )
        amdts = result.scalars().all()

        resolved = 0
        for amdt in amdts:
            # Resoudre auteur
            if amdt.auteur_nom:
                nom_key = _normalize(amdt.auteur_nom)
                match = nom_index.get(nom_key)
                if not match:
                    # Essayer juste le nom de famille
                    parts = amdt.auteur_nom.strip().split()
                    if parts:
                        last_name = _normalize(parts[-1])
                        match = nom_index.get(last_name)
                if match:
                    amdt.auteur_ref = match.uid
                    resolved += 1

            # Resoudre groupe
            if amdt.groupe_nom and not amdt.groupe_ref:
                grp_key = _normalize(amdt.groupe_nom)
                grp_match = groupe_index.get(grp_key)
                if grp_match:
                    amdt.groupe_ref = grp_match.uid

        await db.commit()
        return resolved


def _normalize(s: str) -> str:
    """Normalise un nom pour la comparaison."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]+", "", s).strip()
    return s
