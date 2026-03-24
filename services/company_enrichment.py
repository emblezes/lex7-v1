"""Service d'enrichissement entreprise — API publiques + scraping + BODACC + Claude.

Pipeline d'onboarding : à partir du nom de l'entreprise, du site web et des secteurs,
on collecte un maximum de données publiques AVANT de demander quoi que ce soit au client.

Sources de données :
1. API Recherche d'Entreprises (données SIRENE : CA, effectifs, NAF, dirigeants)
2. Scraping du site web (accueil, à propos, produits, actualités, stratégie)
3. API BODACC (annonces légales récentes : rachats, créations, modifications)
4. Claude génère la fiche entreprise à partir de tout ce contexte
"""

import asyncio
import json
import logging
import re

import httpx
from anthropic import AsyncAnthropic
from bs4 import BeautifulSoup

from legix.core.config import settings

logger = logging.getLogger(__name__)


# ── Étape 1 : API Recherche d'Entreprises (SIRENE) ───────────────────


async def fetch_company_data(company_name: str) -> dict | None:
    """Recherche une entreprise française via l'API Recherche d'Entreprises.

    Retourne les données SIRENE (CA, effectifs, NAF, dirigeants, etc.)
    ou None si l'entreprise n'est pas trouvée.
    """
    url = "https://recherche-entreprises.api.gouv.fr/search"
    params = {"q": company_name, "per_page": 5}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, Exception) as e:
        logger.warning("API Recherche d'Entreprises indisponible: %s", e)
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Prendre le meilleur match (premier résultat)
    company = results[0]

    # Extraire les finances
    finances = company.get("finances", {})
    latest_year = max(finances.keys()) if finances else None
    ca = finances[latest_year].get("ca") if latest_year else None
    resultat_net = finances[latest_year].get("resultat_net") if latest_year else None

    # Extraire les dirigeants principaux
    dirigeants_raw = company.get("dirigeants", [])
    dirigeants = []
    for d in dirigeants_raw[:10]:
        if d.get("type_dirigeant") == "personne physique":
            dirigeants.append({
                "nom": f"{d.get('prenoms', '')} {d.get('nom', '')}".strip(),
                "qualite": d.get("qualite", ""),
            })
        elif d.get("type_dirigeant") == "personne morale":
            dirigeants.append({
                "nom": d.get("denomination", ""),
                "qualite": d.get("qualite", ""),
            })

    siege = company.get("siege", {})

    return {
        "siren": company.get("siren"),
        "nom_complet": company.get("nom_complet"),
        "chiffre_affaires": ca,
        "resultat_net": resultat_net,
        "categorie_entreprise": company.get("categorie_entreprise"),
        "code_naf": company.get("activite_principale"),
        "tranche_effectif": company.get("tranche_effectif_salarie"),
        "siege_social": siege.get("adresse", ""),
        "dirigeants": dirigeants,
        "nombre_etablissements": company.get("nombre_etablissements_ouverts", 0),
        "date_creation": company.get("date_creation"),
        "nature_juridique": company.get("nature_juridique"),
    }


# ── Étape 2 : Scraping approfondi du site web ────────────────────────


def _extract_text(html: str) -> str:
    """Extrait le texte nettoyé d'une page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "noscript", "iframe", "svg", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text


def _discover_links(html: str, base_url: str) -> list[str]:
    """Découvre les liens internes pertinents dans une page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    keywords = [
        "about", "a-propos", "qui-sommes", "notre-groupe", "group",
        "activit", "metier", "business", "strateg", "strategy",
        "produit", "product", "service", "solution", "offre",
        "actualit", "news", "press", "communiqu", "media",
        "investisseur", "investor", "finance", "gouvernance", "governance",
        "innovation", "r-d", "recherche", "technology",
        "developpement-durable", "rse", "csr", "sustainability", "esg",
    ]

    base = base_url.rstrip("/")
    found: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # Ignorer les ancres, mailto, tel, javascript
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        # Normaliser
        if href.startswith("/"):
            full_url = base + href
        elif href.startswith("http"):
            # Garder seulement les liens du même domaine
            if base.split("//")[-1].split("/")[0] not in href:
                continue
            full_url = href
        else:
            full_url = base + "/" + href

        # Nettoyer
        full_url = full_url.split("?")[0].split("#")[0].rstrip("/")

        if full_url in seen or full_url == base:
            continue

        # Vérifier si le chemin contient un mot-clé pertinent
        path = full_url.lower()
        if any(kw in path for kw in keywords):
            seen.add(full_url)
            found.append(full_url)

    return found[:15]  # Max 15 liens candidats


async def fetch_website_deep(website_url: str) -> dict | None:
    """Scraping approfondi du site web : accueil + pages découvertes.

    Retourne un dict structuré par section :
    {
        "homepage": "texte...",
        "about": "texte...",
        "products": "texte...",
        "news": "texte...",
        "strategy": "texte...",
    }
    """
    if not website_url:
        return None

    if not website_url.startswith("http"):
        website_url = f"https://{website_url}"

    base = website_url.rstrip("/")
    sections: dict[str, str] = {}

    async with httpx.AsyncClient(
        timeout=12.0,
        follow_redirects=True,
        headers={"User-Agent": "LegiX-Bot/1.0 (regulatory intelligence platform)"},
    ) as client:
        # 1. Page d'accueil
        try:
            resp = await client.get(base)
            if resp.status_code == 200:
                homepage_text = _extract_text(resp.text)
                if len(homepage_text) > 200:
                    sections["homepage"] = homepage_text[:3000]
                # Découvrir les liens pertinents
                discovered_links = _discover_links(resp.text, base)
            else:
                return None
        except Exception as e:
            logger.warning("Impossible d'accéder à %s: %s", base, e)
            return None

        # 2. Classifier et scraper les liens découverts
        section_keywords = {
            "about": ["about", "a-propos", "qui-sommes", "notre-groupe", "group"],
            "products": ["produit", "product", "service", "solution", "offre", "metier", "business", "activit"],
            "strategy": ["strateg", "strategy", "innovation", "r-d", "recherche", "technology",
                         "developpement-durable", "rse", "csr", "sustainability", "esg"],
            "news": ["actualit", "news", "press", "communiqu", "media"],
            "investors": ["investisseur", "investor", "finance", "gouvernance", "governance"],
        }

        # Scraper en parallèle (max 6 pages)
        pages_to_fetch = discovered_links[:6]

        async def _fetch_page(url: str) -> tuple[str, str | None]:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    text = _extract_text(r.text)
                    if len(text) > 200:
                        return url, text[:2500]
                return url, None
            except Exception:
                return url, None

        results = await asyncio.gather(*[_fetch_page(u) for u in pages_to_fetch])

        for url, text in results:
            if not text:
                continue
            url_lower = url.lower()
            for section_name, kws in section_keywords.items():
                if any(kw in url_lower for kw in kws):
                    if section_name not in sections:
                        sections[section_name] = text
                    else:
                        # Concaténer si la section existe déjà (ex: 2 pages "produits")
                        sections[section_name] = (sections[section_name] + "\n---\n" + text)[:4000]
                    break

    if not sections:
        return None

    return sections


# ── Étape 3 : API BODACC (annonces légales récentes) ─────────────────


async def fetch_bodacc_announcements(siren: str | None, company_name: str) -> list[dict] | None:
    """Récupère les annonces légales récentes via l'API BODACC.

    Recherche par SIREN (prioritaire) ou par nom d'entreprise.
    Retourne les annonces les plus récentes (rachats, modifications, etc.)
    """
    if not siren and not company_name:
        return None

    base_url = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.0"
    endpoint = f"{base_url}/catalog/datasets/annonces-commerciales/records"

    # Construire la requête
    if siren:
        where_clause = f'registre LIKE "%{siren}%" OR numerodepartement LIKE "%{siren[:3]}%"'
        q = siren
    else:
        q = company_name

    params = {
        "q": q,
        "limit": 10,
        "order_by": "dateparution DESC",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(endpoint, params=params)
            if resp.status_code != 200:
                logger.warning("API BODACC status %d", resp.status_code)
                return None
            data = resp.json()
    except (httpx.HTTPError, Exception) as e:
        logger.warning("API BODACC indisponible: %s", e)
        return None

    records = data.get("results", [])
    if not records:
        return None

    announcements = []
    for r in records[:8]:
        announcements.append({
            "type": r.get("typeavis", ""),
            "famille": r.get("familleavis", ""),
            "date": r.get("dateparution", ""),
            "description": (r.get("listepersonnes", "") or "")[:300],
            "tribunal": r.get("tribunal", ""),
            "registre": r.get("registre", ""),
        })

    return announcements if announcements else None


# ── Étape 4 : Claude génère la fiche entreprise ──────────────────────


THEMES_DISPONIBLES = [
    "santé", "énergie", "numérique", "sécurité/défense",
    "agriculture/alimentation", "environnement/climat", "économie/finances",
    "éducation/recherche", "justice", "transports", "logement/urbanisme",
    "travail/emploi", "culture/médias", "outre-mer",
    "institutions/constitution", "affaires étrangères", "immigration",
]


async def generate_company_profile(
    company_name: str,
    company_data: dict | None,
    website_sections: dict | None,
    sectors: list[str],
    website_url: str | None,
    bodacc: list[dict] | None,
) -> dict:
    """Claude génère la fiche entreprise à partir de toutes les données collectées."""

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # --- Construire le contexte riche ---
    context_parts = [f"Entreprise : {company_name}"]

    # Données SIRENE
    if company_data:
        ca = company_data.get("chiffre_affaires")
        rn = company_data.get("resultat_net")
        context_parts.append(f"\n=== DONNÉES OFFICIELLES (SIRENE) ===")
        context_parts.append(f"SIREN : {company_data.get('siren')}")
        if ca:
            context_parts.append(f"Chiffre d'affaires : {ca:,.0f} EUR")
        if rn:
            context_parts.append(f"Résultat net : {rn:,.0f} EUR")
        context_parts.append(f"Code NAF : {company_data.get('code_naf', 'inconnu')}")
        context_parts.append(f"Catégorie : {company_data.get('categorie_entreprise', 'inconnue')}")
        context_parts.append(f"Effectifs : {company_data.get('tranche_effectif', 'inconnu')}")
        context_parts.append(f"Siège : {company_data.get('siege_social', 'inconnu')}")
        context_parts.append(f"Établissements : {company_data.get('nombre_etablissements', '?')}")
        context_parts.append(f"Date création : {company_data.get('date_creation', 'inconnue')}")
        dirigeants = company_data.get("dirigeants", [])
        if dirigeants:
            dir_str = ", ".join(f"{d['nom']} ({d['qualite']})" for d in dirigeants[:5])
            context_parts.append(f"Dirigeants : {dir_str}")

    if website_url:
        context_parts.append(f"\nSite web : {website_url}")

    # Site web — sections scrappées
    if website_sections:
        context_parts.append("\n=== CONTENU DU SITE WEB ===")
        section_labels = {
            "homepage": "Page d'accueil",
            "about": "À propos / Qui sommes-nous",
            "products": "Produits / Services / Métiers",
            "strategy": "Stratégie / Innovation / RSE",
            "news": "Actualités / Communiqués de presse",
            "investors": "Investisseurs / Gouvernance",
        }
        for key, text in website_sections.items():
            label = section_labels.get(key, key)
            # Tronquer chaque section pour le prompt
            context_parts.append(f"\n--- {label} ---\n{text[:2000]}")

    # BODACC
    if bodacc:
        context_parts.append("\n=== ANNONCES LÉGALES RÉCENTES (BODACC) ===")
        for a in bodacc[:5]:
            parts = [a.get("type", ""), a.get("famille", "")]
            if a.get("date"):
                parts.append(f"({a['date']})")
            if a.get("description"):
                parts.append(f": {a['description'][:150]}")
            context_parts.append(f"- {' '.join(p for p in parts if p)}")

    context_parts.append(f"\nSecteurs d'intérêt sélectionnés par le client : {', '.join(sectors)}")

    context = "\n".join(context_parts)

    prompt = f"""Tu es expert en veille réglementaire et affaires publiques en France.
Tu connais parfaitement le paysage législatif et réglementaire français et européen.

À partir des données ci-dessous (sources publiques + site web), génère une fiche entreprise
complète, précise et STRATÉGIQUE. Le but est de connaître cette entreprise mieux qu'elle-même
se connaît, pour anticiper les impacts réglementaires.

DONNÉES DISPONIBLES :
{context}

GÉNÈRE en JSON strict :
{{
  "description": "Description de l'activité de l'entreprise en 3-4 phrases. Mentionne le secteur, les produits/services principaux, la taille (CA, effectifs). Positionnement concurrentiel. En français soutenu.",
  "business_lines": ["Liste de 3-6 divisions ou lignes métiers principales, déduites du site web et du code NAF"],
  "products": ["Liste de 4-8 produits ou services clés de l'entreprise, spécifiques (noms de marques/produits si trouvés sur le site)"],
  "regulatory_focus": ["Liste de 4-6 enjeux réglementaires SPÉCIFIQUES à surveiller pour cette entreprise. Pas des généralités — des enjeux concrets liés à son activité, ses produits, sa taille"],
  "context_note": "Note de contexte stratégique en 3-4 phrases : positionnement marché, enjeux actuels déduits des actualités/BODACC, défis réglementaires majeurs, concurrence.",
  "monitoring_explanation": "Explication en 3-4 phrases de ce que LegiX va surveiller pour cette entreprise : quels types de textes (lois, amendements, décrets), quels thèmes précis, quels impacts potentiels sur quelles divisions. Doit rassurer le client sur la valeur ajoutée.",
  "key_risks": ["Liste de 2-4 risques réglementaires majeurs identifiés pour cette entreprise"],
  "key_opportunities": ["Liste de 2-3 opportunités réglementaires potentielles"]
}}

RÈGLES :
- Sois ULTRA-SPÉCIFIQUE à cette entreprise (pas de réponses génériques)
- Déduis les informations du site web : si tu vois des pages produits, cite les vrais produits
- Si le site mentionne une stratégie RSE/ESG, intègre les enjeux réglementaires correspondants
- Si des actualités ou annonces BODACC sont disponibles, intègre ce contexte récent
- Si le CA est connu, calibre les enjeux en conséquence (PME ≠ GE)
- Les regulatory_focus doivent être des enjeux CONCRETS et ACTUELS (cite les textes quand possible : CSRD, NIS2, Egalim, etc.)
- Le monitoring_explanation doit être personnalisé et convaincant
- Français impeccable, style professionnel
- Réponds UNIQUEMENT avec le JSON, pas de texte autour"""

    try:
        response = await client.messages.create(
            model=settings.enrichment_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```json")[-1].split("```")[0] if "```json" in text else text.split("```")[1].split("```")[0]

        result = json.loads(text)

        # S'assurer que toutes les clés sont présentes
        for key in ["description", "business_lines", "products", "regulatory_focus",
                     "context_note", "monitoring_explanation", "key_risks", "key_opportunities"]:
            if key not in result:
                result[key] = "" if key in ("description", "context_note", "monitoring_explanation") else []

        return result

    except Exception as e:
        logger.error("Erreur génération fiche entreprise: %s", e)
        return {
            "description": f"{company_name} — entreprise active dans les secteurs {', '.join(sectors)}.",
            "business_lines": sectors,
            "products": [],
            "regulatory_focus": sectors,
            "context_note": f"Entreprise suivie sur les thématiques : {', '.join(sectors)}.",
            "monitoring_explanation": f"LegiX surveille les textes législatifs et amendements touchant aux secteurs {', '.join(sectors)} pour identifier les impacts potentiels sur votre activité.",
            "key_risks": [],
            "key_opportunities": [],
        }


# ── Pipeline complet ─────────────────────────────────────────────────


async def enrich_and_build_profile(
    company_name: str,
    email: str,
    sectors: list[str],
    website_url: str | None = None,
) -> dict:
    """Pipeline complet d'enrichissement : API publiques + scraping + BODACC + Claude.

    Retourne un dict prêt à être inséré dans ClientProfile.
    Toutes les étapes sont lancées en parallèle quand possible.
    """
    # 1. Lancer les requêtes en parallèle
    company_task = asyncio.create_task(fetch_company_data(company_name))
    website_task = asyncio.create_task(fetch_website_deep(website_url)) if website_url else None

    # Attendre les données SIRENE d'abord (on a besoin du SIREN pour BODACC)
    company_data = await company_task
    siren = company_data.get("siren") if company_data else None

    # Lancer BODACC avec le SIREN (ou le nom)
    bodacc_task = asyncio.create_task(
        fetch_bodacc_announcements(siren, company_name)
    )

    # Attendre le site web et BODACC
    website_sections = await website_task if website_task else None
    bodacc = await bodacc_task

    logger.info(
        "Enrichissement %s : SIRENE=%s, site=%d sections, BODACC=%d annonces",
        company_name,
        "OK" if company_data else "NON",
        len(website_sections) if website_sections else 0,
        len(bodacc) if bodacc else 0,
    )

    # 2. Claude génère la fiche avec TOUT le contexte
    profile_data = await generate_company_profile(
        company_name=company_name,
        company_data=company_data,
        website_sections=website_sections,
        sectors=sectors,
        website_url=website_url,
        bodacc=bodacc,
    )

    # 3. Assembler le profil complet
    result = {
        "name": company_data.get("nom_complet", company_name) if company_data else company_name,
        "email": email,
        "sectors": json.dumps(sectors, ensure_ascii=False),
        "business_lines": json.dumps(profile_data.get("business_lines", []), ensure_ascii=False),
        "products": json.dumps(profile_data.get("products", []), ensure_ascii=False),
        "regulatory_focus": json.dumps(profile_data.get("regulatory_focus", []), ensure_ascii=False),
        "context_note": profile_data.get("context_note", ""),
        "description": profile_data.get("description", ""),
        "monitoring_explanation": profile_data.get("monitoring_explanation", ""),
        "key_risks": json.dumps(profile_data.get("key_risks", []), ensure_ascii=False),
        "key_opportunities": json.dumps(profile_data.get("key_opportunities", []), ensure_ascii=False),
        "site_web": website_url,
        "is_active": True,
    }

    # Ajouter les données SIRENE si disponibles
    if company_data:
        result.update({
            "siren": company_data.get("siren"),
            "chiffre_affaires": company_data.get("chiffre_affaires"),
            "resultat_net": company_data.get("resultat_net"),
            "effectifs": company_data.get("tranche_effectif"),
            "code_naf": company_data.get("code_naf"),
            "siege_social": company_data.get("siege_social"),
            "categorie_entreprise": company_data.get("categorie_entreprise"),
            "dirigeants": json.dumps(company_data.get("dirigeants", []), ensure_ascii=False),
        })

    return result
