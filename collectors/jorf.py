"""Collecteur JORF — Journal Officiel via API PISTE (DILA).

Strategie :
1. consult/lastNJo → derniers numeros du JO
2. consult/jorfCont → sommaire d'un numero (liste des textes)
3. consult/jorf → texte complet (articles, signataires, NOR, ELI)

Tous les endpoints sont en POST avec body JSON.
Authentification OAuth2 client_credentials.

Alternative sans API : flux XML quotidien sur echanges.dila.gouv.fr/OPENDATA/JORF/
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from legix.collectors.base import BaseCollector
from legix.core.config import settings
from legix.core.models import Texte

logger = logging.getLogger(__name__)

# Types de textes JO pertinents pour la veille reglementaire
JORF_NATURES_PERTINENTES = {
    "LOI", "ORDONNANCE", "DECRET", "ARRETE", "DECISION",
}

# Mapping nature JO → (type_code, type_libelle) LegiX
NATURE_MAPPING = {
    "LOI": ("LOI", "Loi"),
    "ORDONNANCE": ("ORDO", "Ordonnance"),
    "DECRET": ("DECR", "Decret"),
    "ARRETE": ("ARRT", "Arrete"),
    "DECISION": ("DECI", "Decision"),
    "AVIS": ("AVIS", "Avis"),
}


class JORFCollector(BaseCollector):
    """Collecteur JORF via API PISTE — OAuth2 + REST (POST JSON)."""

    def __init__(self):
        super().__init__()
        self._token: str | None = None
        self._token_expires: datetime | None = None

    def get_source_name(self) -> str:
        return "jorf"

    async def _get_oauth_token(self) -> str | None:
        """Obtient ou renouvelle le token OAuth2 PISTE."""
        now = datetime.utcnow()
        if self._token and self._token_expires and now < self._token_expires:
            return self._token

        if not settings.piste_client_id or not settings.piste_client_secret:
            logger.info("[jorf] PISTE non configure — skip")
            return None

        client = await self._get_client()
        try:
            resp = await client.post(
                settings.piste_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.piste_client_id,
                    "client_secret": settings.piste_client_secret,
                    "scope": "openid",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expires = now + timedelta(seconds=expires_in - 60)
            logger.info("[jorf] Token OAuth2 PISTE obtenu (expire dans %ds)", expires_in)
            return self._token
        except Exception as e:
            logger.error("[jorf] Erreur OAuth2: %s", e)
            return None

    async def _piste_post(self, endpoint: str, payload: dict) -> dict | None:
        """Appel POST a l'API PISTE Legifrance."""
        token = await self._get_oauth_token()
        if not token:
            return None

        client = await self._get_client()
        url = f"{settings.piste_api_base}/{endpoint}"
        try:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("[jorf] Erreur API %s: %s", endpoint, e)
            return None

    # --- Etape 1 : Derniers numeros du JO ---

    async def _fetch_last_jo_containers(self, n: int = 3) -> list[dict]:
        """Recupere les N derniers conteneurs JORF (numeros du JO)."""
        data = await self._piste_post("consult/lastNJo", {"nbElement": n})
        if not data:
            return []
        return data.get("containers", [])

    # --- Etape 2 : Sommaire d'un numero ---

    async def _fetch_jo_sommaire(self, container_id: str) -> list[dict]:
        """Recupere le sommaire d'un numero du JO → liste de textes."""
        data = await self._piste_post("consult/jorfCont", {
            "id": container_id,
            "pageSize": 200,
            "pageNumber": 1,
        })
        if not data:
            return []

        textes = []
        items = data.get("items", [])
        for item in items:
            jo_cont = item.get("joCont", item)
            structure = jo_cont.get("structure", {})
            liens = structure.get("liens", [])
            for lien in liens:
                textes.append({
                    "id": lien.get("id", ""),
                    "titre": lien.get("titre", ""),
                    "nature": (lien.get("nature") or "").upper(),
                    "etat": lien.get("etat", ""),
                    "ministere": lien.get("ministere", ""),
                    "emetteur": lien.get("emetteur", ""),
                    "container_id": container_id,
                    "date_publi": jo_cont.get("datePubli"),
                    "titre_jo": jo_cont.get("titre", ""),
                })

        # Si pas de structure liens, tenter le format direct
        if not textes and items:
            for item in items:
                texte_id = item.get("id", item.get("textCid", ""))
                if texte_id:
                    textes.append({
                        "id": texte_id,
                        "titre": item.get("titre", item.get("title", "")),
                        "nature": (item.get("nature", item.get("type", "")) or "").upper(),
                        "etat": item.get("etat", ""),
                        "container_id": container_id,
                    })

        return textes

    # --- Etape 3 : Texte complet ---

    async def _fetch_texte_complet(self, text_cid: str) -> dict | None:
        """Recupere le texte integral d'un document JORF."""
        data = await self._piste_post("consult/jorf", {"textCid": text_cid})
        if not data:
            return None

        # Extraire le contenu des articles
        articles = data.get("articles", [])
        contenu_parts = []
        for art in articles:
            num = art.get("num", art.get("numero", ""))
            content = art.get("content", art.get("contenu", art.get("texte", "")))
            if content:
                prefix = f"Article {num} : " if num else ""
                contenu_parts.append(f"{prefix}{content}")

        return {
            "cid": data.get("cid", data.get("id", text_cid)),
            "titre": data.get("title", data.get("titre", "")),
            "nature": (data.get("nature", "") or "").upper(),
            "nor": data.get("nor", ""),
            "eli": data.get("eli", data.get("idEli", "")),
            "date_texte": data.get("dateTexte", ""),
            "date_parution": data.get("dateParution", data.get("datePubli", "")),
            "num_parution": data.get("numParution", ""),
            "etat": data.get("etat", ""),
            "visa": data.get("visa", ""),
            "notice": data.get("notice", ""),
            "signers": data.get("signers", data.get("signataires", "")),
            "mots_cles": data.get("motsCles", []),
            "resume": data.get("resume", ""),
            "contenu": "\n\n".join(contenu_parts) if contenu_parts else "",
            "nb_articles": len(articles),
            "dossiers_legislatifs": data.get("dossiersLegislatifs", []),
        }

    # --- Stockage ---

    async def _store_jorf_texte(
        self, db: AsyncSession, sommaire_item: dict, detail: dict | None
    ) -> str:
        """Stocke un texte JO en base."""
        cid = sommaire_item["id"]
        uid = f"JORF-{cid}"

        existing = await db.get(Texte, uid)
        if existing:
            return "skipped"

        nature = sommaire_item.get("nature", "").upper()
        type_code, type_libelle = NATURE_MAPPING.get(nature, ("JORF", "Texte du JO"))

        titre = sommaire_item.get("titre", "")
        if detail:
            titre = detail.get("titre") or titre

        date_texte = None
        date_publi = None
        if detail:
            date_texte = _parse_date(detail.get("date_texte"))
            date_publi = _parse_date(detail.get("date_parution"))
        if not date_publi:
            date_publi = _parse_timestamp(sommaire_item.get("date_publi"))

        # Contenu resume pour enrichissement IA
        contenu_resume = ""
        if detail:
            parts = [detail.get("resume", ""), detail.get("notice", "")]
            contenu = detail.get("contenu", "")
            if contenu:
                parts.append(contenu[:1500])
            contenu_resume = "\n".join(p for p in parts if p)

        nor = detail.get("nor", "") if detail else ""

        texte = Texte(
            uid=uid,
            denomination=type_libelle,
            titre=titre,
            titre_court=titre[:120] if titre else "",
            type_code=type_code,
            type_libelle=type_libelle,
            date_depot=date_texte,
            date_publication=date_publi,
            source="jorf",
            url_source=f"https://www.legifrance.gouv.fr/jorf/id/{cid}",
            auteur_texte=contenu_resume[:2000] if contenu_resume else nor,
        )
        db.add(texte)
        return "new"

    # --- Collecte principale ---

    async def collect(self, db: AsyncSession) -> dict:
        """Collecte les textes des derniers numeros du JO."""
        stats = self._empty_stats()

        token = await self._get_oauth_token()
        if not token:
            return stats

        # 1. Recuperer les 3 derniers numeros du JO
        containers = await self._fetch_last_jo_containers(n=3)
        logger.info("[jorf] %d numeros du JO trouves", len(containers))

        for container in containers:
            container_id = container.get("id", "")
            titre_jo = container.get("titre", "")
            if not container_id:
                continue

            # 2. Sommaire de ce numero
            textes_sommaire = await self._fetch_jo_sommaire(container_id)
            logger.info("[jorf] %s: %d textes", titre_jo, len(textes_sommaire))

            for item in textes_sommaire:
                nature = item.get("nature", "").upper()
                text_id = item.get("id", "")

                # Filtrer les types non pertinents
                if nature and nature not in JORF_NATURES_PERTINENTES:
                    stats["skipped"] += 1
                    continue

                uid = f"JORF-{text_id}"
                if await self._is_seen(db, uid):
                    stats["skipped"] += 1
                    continue

                # 3. Recuperer le detail du texte
                detail = None
                if text_id:
                    try:
                        detail = await self._fetch_texte_complet(text_id)
                    except Exception as e:
                        logger.warning("[jorf] Detail echoue pour %s: %s", text_id, e)

                # 4. Stocker
                try:
                    result = await self._store_jorf_texte(db, item, detail)
                    if result == "new":
                        stats["new"] += 1
                        stats["new_uids"]["texte"].append(uid)
                        stats["by_type"]["texte"] += 1

                    await self._mark_seen(db, uid, "texte", uid)
                except Exception as e:
                    stats["errors"] += 1
                    logger.warning("[jorf] Erreur stockage %s: %s", text_id, e)

            await db.commit()

        logger.info(
            "[jorf] Collecte terminee: %d nouveaux, %d skip, %d erreurs",
            stats["new"], stats["skipped"], stats["errors"],
        )
        return stats


def _parse_date(value) -> datetime | None:
    """Parse une date ISO ou timestamp."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_timestamp(value) -> datetime | None:
    """Parse un timestamp millisecondes (format PISTE)."""
    if not value:
        return None
    try:
        ts = int(value)
        if ts > 1e12:  # millisecondes
            ts = ts / 1000
        return datetime.utcfromtimestamp(ts)
    except (ValueError, TypeError, OSError):
        return None
