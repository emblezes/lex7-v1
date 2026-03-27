"""Collecteur Acteurs Assemblée nationale — députés actifs + organes.

Source officielle : Open data AN
https://data.assemblee-nationale.fr/acteurs/deputes-en-exercice

Fichier ZIP contenant un JSON par député (577 fichiers) + organes (groupes, commissions).
Les UID (PA######) correspondent exactement aux acteurRef des scrutins.
"""

import io
import json
import logging
import zipfile
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.models import Acteur, Organe

logger = logging.getLogger(__name__)

def _safe_str(val) -> str:
    """Convertit en string propre, gere les dicts XML nil."""
    if val is None:
        return ""
    if isinstance(val, dict):
        return val.get("#text", "") if "#text" in val else ""
    return str(val).strip()


DEPUTES_ZIP_URL = (
    "https://data.assemblee-nationale.fr/static/openData/repository"
    "/17/amo/deputes_actifs_mandats_actifs_organes"
    "/AMO10_deputes_actifs_mandats_actifs_organes.json.zip"
)


class AssembleeActeursCollector(BaseCollector):
    """Collecteur des 577 députés et organes AN via open data officiel."""

    def get_source_name(self) -> str:
        return "assemblee_acteurs"

    async def collect(self, db: AsyncSession) -> dict:
        stats = self._empty_stats()

        # Télécharger le ZIP
        client = await self._get_client()
        try:
            resp = await client.get(DEPUTES_ZIP_URL, timeout=60.0)
            resp.raise_for_status()
        except Exception as e:
            logger.error("[assemblee_acteurs] Téléchargement échoué: %s", e)
            stats["errors"] += 1
            return stats

        logger.info(
            "[assemblee_acteurs] ZIP téléchargé: %.1f MB",
            len(resp.content) / 1_000_000,
        )

        # Extraire et traiter
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            # Phase 1 : Organes (groupes politiques, commissions)
            organe_files = [
                n for n in zf.namelist()
                if n.startswith("json/organe/") and n.endswith(".json")
            ]
            for name in organe_files:
                try:
                    with zf.open(name) as f:
                        data = json.load(f)
                    await self._process_organe(db, stats, data)
                except Exception:
                    continue

            await db.commit()
            logger.info(
                "[assemblee_acteurs] %d organes traités", len(organe_files)
            )

            # Phase 2 : Députés
            acteur_files = [
                n for n in zf.namelist()
                if n.startswith("json/acteur/PA") and n.endswith(".json")
            ]
            for name in acteur_files:
                try:
                    with zf.open(name) as f:
                        data = json.load(f)
                    await self._process_depute(db, stats, data)
                except Exception as e:
                    await db.rollback()
                    stats["errors"] += 1
                    logger.debug("[assemblee_acteurs] Erreur %s: %s", name, e)
                    continue

            await db.commit()

        logger.info(
            "[assemblee_acteurs] %d nouveaux, %d mis à jour, %d erreurs",
            stats["new"], stats["updated"], stats["errors"],
        )
        return stats

    async def _process_depute(
        self, db: AsyncSession, stats: dict, data: dict
    ):
        """Traite un fichier JSON de député."""
        acteur = data.get("acteur", {})
        uid = acteur.get("uid", {}).get("#text", "")
        if not uid:
            return

        ident = acteur.get("etatCivil", {}).get("ident", {})
        prenom = ident.get("prenom", "")
        nom = ident.get("nom", "")
        civilite = ident.get("civ", "")

        profession = _safe_str(acteur.get("profession", {}).get("libelleCourant", "")
                               if isinstance(acteur.get("profession"), dict)
                               else acteur.get("profession", ""))

        # Trouver le groupe politique actif
        groupe_ref = ""
        mandats = acteur.get("mandats", {}).get("mandat", [])
        if isinstance(mandats, dict):
            mandats = [mandats]
        for m in mandats:
            if m.get("typeOrgane") == "GP" and not m.get("dateFin"):
                groupe_ref = m.get("organes", {}).get("organeRef", "")
                break

        # Trouver les adresses/contacts
        adresses = acteur.get("adresses", {}).get("adresse", [])
        if isinstance(adresses, dict):
            adresses = [adresses]

        email = None
        site_web = None
        twitter = None
        adresse_an = None
        adresse_circo = None

        for adr in adresses:
            type_libelle = adr.get("typeLibelle", "")
            if "mel" in type_libelle.lower() or "@" in adr.get("valElec", ""):
                email = email or adr.get("valElec", "")
            elif "site" in type_libelle.lower():
                val = adr.get("valElec", "")
                if "twitter" in val.lower() or "x.com" in val.lower():
                    twitter = twitter or val
                else:
                    site_web = site_web or val
            elif "assemblée" in type_libelle.lower():
                adresse_an = adr.get("valElec", "") or adr.get(
                    "adresseDeRattachement", ""
                )
            elif "circo" in type_libelle.lower():
                adresse_circo = adr.get("valElec", "") or adr.get(
                    "adresseDeRattachement", ""
                )

        # Collaborateurs
        collabs = acteur.get("collaborateurs", {}).get("collaborateur", [])
        if isinstance(collabs, dict):
            collabs = [collabs]
        collab_str = ", ".join(
            f"{c.get('prenom', '')} {c.get('nom', '')}".strip()
            for c in collabs
        ) if collabs else None

        # Créer ou mettre à jour
        existing = await db.get(Acteur, uid)
        if existing:
            existing.prenom = prenom
            existing.nom = nom
            existing.civilite = civilite
            existing.groupe_politique_ref = groupe_ref
            existing.profession = profession
            existing.email = email or existing.email
            existing.site_web = site_web or existing.site_web
            existing.twitter = twitter or existing.twitter
            existing.adresse_an = adresse_an or existing.adresse_an
            existing.adresse_circo = adresse_circo or existing.adresse_circo
            existing.collaborateurs = collab_str or existing.collaborateurs
            existing.source = "assemblee"
            existing.updated_at = datetime.utcnow()
            stats["updated"] += 1
            stats["updated_uids"]["acteur"].append(uid)
        else:
            act = Acteur(
                uid=uid,
                civilite=civilite,
                prenom=prenom,
                nom=nom,
                groupe_politique_ref=groupe_ref,
                profession=profession,
                email=email,
                site_web=site_web,
                twitter=twitter,
                adresse_an=adresse_an,
                adresse_circo=adresse_circo,
                collaborateurs=collab_str,
                source="assemblee",
            )
            db.add(act)
            stats["new"] += 1
            stats["new_uids"]["acteur"].append(uid)

    async def _process_organe(
        self, db: AsyncSession, stats: dict, data: dict
    ):
        """Traite un fichier JSON d'organe (groupe, commission)."""
        organe = data.get("organe", {})
        uid = organe.get("uid", "")
        if not uid:
            return

        existing = await db.get(Organe, uid)
        if existing:
            return

        org = Organe(
            uid=uid,
            type_code=organe.get("codeType", ""),
            type_libelle=organe.get("libelleType", ""),
            libelle=organe.get("libelle", ""),
            libelle_court=organe.get("libelleAbrev", ""),
            legislature=int(organe.get("legislature", 0) or 0),
            source="assemblee",
        )
        db.add(org)
