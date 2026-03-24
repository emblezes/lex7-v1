"""Seed 10 profils clients + alertes d'impact avec analyses IA reelles.

Usage:
    python -m legix.scripts.seed_profiles

Cree les 10 ClientProfile et genere des ImpactAlert basees sur les
vrais textes/amendements de la DB, avec des analyses d'impact generees
par Claude API (pas des templates).
"""

import asyncio
import json
import logging
import random
import re
from datetime import datetime, timedelta

import anthropic
import bcrypt
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.core.config import settings
from legix.core.database import engine, async_session
from legix.core.models import (
    Acteur,
    Amendement,
    ClientProfile,
    ImpactAlert,
    Organe,
    Texte,
)
from legix.services.alert_generation import (
    _build_contextual_actions,
    _build_doc_context,
    _clean_html,
    _generate_batch_analyses as _service_generate_batch_analyses,
    _get_auteur_name,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Les 10 profils clients ──────────────────────────────────────────

PROFILES = [
    {
        "name": "Sanofi",
        "email": "veille@sanofi.com",
        "sectors": ["santé"],
        "business_lines": [
            "Pharma innovante (immunologie, oncologie, maladies rares)",
            "Vaccins (Sanofi Pasteur)",
            "Consumer Healthcare (Doliprane, Mucosolvan)",
            "Biosimilaires et generiques",
        ],
        "products": [
            "Dupixent (dermatite atopique, asthme)",
            "Kevzara (polyarthrite rhumatoide)",
            "Aubagio (sclerose en plaques)",
            "Doliprane (paracetamol, OTC)",
            "Vaccins grippe / COVID",
        ],
        "regulatory_focus": [
            "AMM et procedures accelerees EMA/ANSM",
            "Prix et remboursement (CEPS, UNCAM)",
            "Pharmacovigilance et transparence",
            "Essais cliniques et bioethique",
            "Brevets et propriete intellectuelle pharma",
        ],
        "context_note": (
            "Groupe pharmaceutique mondial (CA ~43 Md EUR). 3 divisions : Pharma innovante, "
            "Vaccins, Consumer Healthcare. Enjeu strategique : Dupixent (blockbuster >10 Md EUR). "
            "Tres sensible aux textes sur le prix du medicament, l'acces aux soins, les AMM, "
            "la pharmacovigilance et la reforme de la Securite sociale."
        ),
        # Données publiques réelles (API Recherche d'Entreprises / SIRENE)
        "siren": "395030844",
        "code_naf": "2120Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 43_000_000_000,
        "resultat_net": 5_400_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "54 rue La Boetie, 75008 Paris",
        "site_web": "https://www.sanofi.com",
        "description": (
            "Sanofi est un groupe pharmaceutique mondial base a Paris, specialise dans "
            "l'immunologie, l'oncologie, les maladies rares et les vaccins. Avec un chiffre "
            "d'affaires de 43 milliards d'euros et plus de 90 000 collaborateurs dans 100 pays, "
            "Sanofi est le 1er acteur pharma francais et parmi les 10 premiers mondiaux."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Sanofi tous les textes legislatifs et amendements touchant "
            "a la sante, au prix du medicament, aux AMM, a la pharmacovigilance et a la "
            "Securite sociale. Chaque alerte identifie les divisions concernees (Pharma innovante, "
            "Vaccins, CHC) et chiffre l'exposition financiere par rapport au CA de 43 Md EUR."
        ),
        "exposure_range": (500_000, 50_000_000),
        "impact_angles": {
            "threat": [
                "pourrait imposer de nouvelles contraintes sur {division}, augmentant les couts de mise en conformite",
                "risque de plafonnement tarifaire impactant les revenus de {division}",
                "obligation de transparence accrue pouvant fragiliser la strategie de propriete intellectuelle",
                "nouvelles exigences reglementaires susceptibles de retarder le pipeline de {division}",
            ],
            "opportunity": [
                "pourrait ouvrir de nouvelles opportunites de financement pour {division}",
                "cadre reglementaire favorable au deploiement de {product}",
                "acceleration des procedures beneficiant au pipeline de {division}",
                "incitations publiques alignees avec la strategie de {division}",
            ],
        },
    },
    {
        "name": "TotalEnergies",
        "email": "affaires-publiques@totalenergies.com",
        "sectors": ["énergie", "environnement / climat"],
        "business_lines": [
            "Exploration-Production (petrole, gaz, GNL)",
            "Raffinage-Chimie (carburants, polymeres)",
            "Marketing & Services (stations-service, lubrifiants)",
            "Gas Renewables & Power (solaire, eolien, batteries)",
            "Integrated LNG (liquefaction, transport, regazeification)",
        ],
        "products": [
            "GNL (1er acteur mondial prive)",
            "Carburants et biocarburants (SAF inclus)",
            "Electricite renouvelable (35 GW cible 2025)",
            "Hydrogene vert (projets industriels)",
            "Lubrifiants et bitumes",
        ],
        "regulatory_focus": [
            "Taxe carbone et marche EU-ETS",
            "Taxonomie verte europeenne",
            "CSRD et reporting extra-financier",
            "Concessions et redevances petrolieres",
            "Normes d'emission et quotas CO2",
            "Sobriete energetique et plan climat",
        ],
        "context_note": (
            "Major energetique integre (CA ~220 Md EUR). En pleine transition vers les ENR "
            "et le GNL. Tres expose aux legislations climat/carbone (EU-ETS, taxonomie), "
            "aux redevances petrolieres, a la CSRD. Enjeu : maintenir la licence to operate "
            "tout en accelerant la diversification renouvelable."
        ),
        "siren": "542051180",
        "code_naf": "0610Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 218_000_000_000,
        "resultat_net": 21_400_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "2 place Jean Millier, 92400 Courbevoie",
        "site_web": "https://www.totalenergies.com",
        "description": (
            "TotalEnergies est un major energetique mondial integre, present dans la production "
            "de petrole et gaz, le raffinage, la distribution de carburants et les energies "
            "renouvelables. Avec 218 milliards d'euros de CA et 100 000+ collaborateurs, "
            "le groupe accelere sa transition vers le GNL et les renouvelables."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour TotalEnergies les textes touchant a l'energie, au climat, "
            "a la fiscalite carbone (EU-ETS), a la taxonomie verte et aux obligations CSRD. "
            "Chaque alerte distingue l'impact sur Exploration-Production vs Gas Renewables & Power "
            "et calibre l'exposition financiere sur un CA de 218 Md EUR."
        ),
        "exposure_range": (1_000_000, 100_000_000),
        "impact_angles": {
            "threat": [
                "renforcement des contraintes carbone impactant directement {division}",
                "nouvelles obligations de reporting alourdissant les couts de conformite pour {division}",
                "restriction sur les activites fossiles menacant la rentabilite de {division}",
                "hausse de la fiscalite energetique pesant sur les marges de {division}",
            ],
            "opportunity": [
                "soutien aux energies renouvelables beneficiant a {division}",
                "cadre reglementaire favorable au deploiement de {product}",
                "subventions transition energetique alignees avec la strategie {division}",
                "ouverture de marche pour {division} grace a de nouvelles obligations",
            ],
        },
    },
    {
        "name": "Orange",
        "email": "regulation@orange.com",
        "sectors": ["numérique"],
        "business_lines": [
            "Fibre et reseaux fixes (FTTH, xDSL)",
            "Mobile et 5G (B2C, B2B)",
            "Orange Business (cloud, cybersecurite, IoT)",
            "Orange Cyberdefense",
            "Contenus et services digitaux (OCS, Orange Bank)",
        ],
        "products": [
            "Livebox et offres fibre",
            "Forfaits mobile (Sosh, Orange)",
            "Solutions cloud entreprises",
            "SOC et services cybersecurite managee",
            "Orange Money (Afrique)",
        ],
        "regulatory_focus": [
            "Regulation du marche telecom (ARCEP)",
            "DMA/DSA et regulation des plateformes",
            "Cybersecurite (NIS2, DORA)",
            "Attribution du spectre 5G/6G",
            "Deploiement fibre (obligations de couverture)",
            "Protection des donnees (RGPD, ePrivacy)",
        ],
        "context_note": (
            "1er operateur telecom francais (CA ~44 Md EUR). Investissements massifs fibre "
            "et 5G. Division cybersecurite en forte croissance. Tres sensible aux decisions "
            "ARCEP, aux obligations de couverture, a la regulation des plateformes (DMA/DSA) "
            "et aux normes cybersecurite (NIS2)."
        ),
        "siren": "380129866",
        "code_naf": "6110Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 44_100_000_000,
        "resultat_net": 2_600_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "111 quai du President Roosevelt, 92130 Issy-les-Moulineaux",
        "site_web": "https://www.orange.com",
        "description": (
            "Orange est le premier operateur de telecommunications francais et l'un des leaders "
            "europeens. Present dans la fibre, la 5G, le cloud et la cybersecurite, le groupe "
            "realise 44 milliards d'euros de CA avec 137 000 collaborateurs dans 26 pays."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Orange les textes relatifs au numerique, aux telecoms, "
            "a la cybersecurite (NIS2), au spectre 5G/6G et a la protection des donnees. "
            "Les alertes identifient les impacts sur les reseaux fixes, le mobile, "
            "Orange Business et Orange Cyberdefense."
        ),
        "exposure_range": (200_000, 20_000_000),
        "impact_angles": {
            "threat": [
                "nouvelles obligations de couverture alourdissant les investissements de {division}",
                "regulation des plateformes impactant le modele economique de {division}",
                "exigences de cybersecurite renforcees augmentant les couts pour {division}",
                "contraintes sur les donnees limitant les capacites de {division}",
            ],
            "opportunity": [
                "investissements publics en cybersecurite creant un marche pour {division}",
                "obligations de deploiement fibre/5G accelerant les revenus de {division}",
                "cadre reglementaire favorable a {product}",
                "subventions numeriques beneficiant au deploiement de {division}",
            ],
        },
    },
    {
        "name": "BNP Paribas",
        "email": "compliance@bnpparibas.com",
        "sectors": ["économie / finances"],
        "business_lines": [
            "Banque de detail (France, Belgique, Italie)",
            "BNP Paribas Personal Finance (credit conso)",
            "CIB - Corporate & Institutional Banking",
            "Investment & Protection Services (assurance, AM)",
            "Arval (LLD automobile)",
        ],
        "products": [
            "Credits immobiliers et consommation",
            "Comptes courants et epargne (Livret A, PEL)",
            "Services de marche (trading, prime brokerage)",
            "Assurance vie et OPCVM",
            "Location longue duree vehicules",
        ],
        "regulatory_focus": [
            "Bale IV et exigences de fonds propres",
            "DORA (resilience operationnelle numerique)",
            "LCB-FT et conformite anti-blanchiment",
            "Finance durable (SFDR, taxonomie)",
            "MiFID II et protection des investisseurs",
            "Plafonnement des frais bancaires",
        ],
        "context_note": (
            "1ere banque de la zone euro (PNB ~46 Md EUR). Banque systemique mondiale (G-SIB). "
            "4 metiers : retail, CIB, IPS, Personal Finance. Tres sensible aux evolutions "
            "prudentielles (Bale IV, DORA), a la regulation ESG (SFDR), au plafonnement "
            "des frais et aux obligations LCB-FT."
        ),
        "siren": "662042449",
        "code_naf": "6419Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 46_200_000_000,
        "resultat_net": 11_200_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "16 boulevard des Italiens, 75009 Paris",
        "site_web": "https://group.bnpparibas",
        "description": (
            "BNP Paribas est la premiere banque de la zone euro et une institution financiere "
            "systemique mondiale (G-SIB). Presente dans la banque de detail, la banque de "
            "financement et d'investissement, l'assurance et la gestion d'actifs, elle emploie "
            "190 000 collaborateurs dans 63 pays pour un PNB de 46 milliards d'euros."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour BNP Paribas les textes relatifs a la regulation bancaire "
            "(Bale IV, DORA), a la conformite (LCB-FT), a la finance durable (SFDR, taxonomie) "
            "et aux frais bancaires. Les analyses distinguent l'impact sur retail, CIB, "
            "Personal Finance et IPS."
        ),
        "exposure_range": (1_000_000, 200_000_000),
        "impact_angles": {
            "threat": [
                "renforcement des exigences prudentielles impactant {division}",
                "plafonnement des frais erosant les revenus de {division}",
                "nouvelles obligations de conformite alourdissant les couts de {division}",
                "contraintes ESG limitant les activites de {division}",
            ],
            "opportunity": [
                "cadre reglementaire ouvrant de nouveaux marches pour {division}",
                "finance durable creant des opportunites pour {product}",
                "simplification reglementaire beneficiant a {division}",
                "ouverture concurrentielle favorable a {division}",
            ],
        },
    },
    {
        "name": "Vinci",
        "email": "direction-juridique@vinci.com",
        "sectors": ["transports", "logement / urbanisme"],
        "business_lines": [
            "Vinci Autoroutes (concessions autoroutieres)",
            "VINCI Airports (gestion aeroportuaire)",
            "Vinci Energies (installations electriques, IT)",
            "Eurovia (routes et infrastructures)",
            "Vinci Construction (batiment, genie civil)",
        ],
        "products": [
            "Concessions autoroutieres (ASF, Cofiroute, Escota)",
            "Gestion d'aeroports (Nantes, Lyon, Gatwick)",
            "Construction d'immeubles et d'infrastructures",
            "Travaux routiers et ferroviaires",
            "Smart buildings et efficacite energetique",
        ],
        "regulatory_focus": [
            "Regime des concessions et PPP",
            "RE2020 et normes de construction",
            "ZAN (zero artificialisation nette)",
            "Mobilite durable et LOM",
            "Commande publique et code des marches",
            "Transition energetique des batiments",
        ],
        "context_note": (
            "Leader mondial du BTP et des concessions (CA ~65 Md EUR). Double exposition : "
            "concessions (autoroutes, aeroports) tres regulees + construction soumise aux "
            "normes RE2020/ZAN. Enjeu : perenite des concessions autoroutieres et adaptation "
            "aux nouvelles normes environnementales."
        ),
        "siren": "552037806",
        "code_naf": "4299Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 65_500_000_000,
        "resultat_net": 4_700_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "1 cours Ferdinand de Lesseps, 92500 Rueil-Malmaison",
        "site_web": "https://www.vinci.com",
        "description": (
            "Vinci est le leader mondial du BTP et des concessions. Le groupe exploite "
            "4 443 km d'autoroutes en France (ASF, Cofiroute, Escota) et 70 aeroports "
            "dans le monde. Avec 65 milliards d'euros de CA et 280 000 collaborateurs, "
            "Vinci couvre la construction, l'energie et les infrastructures de mobilite."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Vinci les textes relatifs aux concessions, a la commande "
            "publique, aux normes de construction (RE2020), au ZAN et a la mobilite durable. "
            "Les alertes distinguent l'impact sur Autoroutes, Airports, Construction et Energies."
        ),
        "exposure_range": (500_000, 50_000_000),
        "impact_angles": {
            "threat": [
                "evolution du cadre des concessions menacant la rentabilite de {division}",
                "normes de construction renforcees augmentant les couts de {division}",
                "restriction du foncier impactant le pipeline de projets {division}",
                "reforme de la commande publique modifiant l'acces aux marches de {division}",
            ],
            "opportunity": [
                "plan d'investissement en infrastructures beneficiant a {division}",
                "renovation energetique creant un volume de marche pour {division}",
                "mobilite durable ouvrant des opportunites pour {division}",
                "subventions construction/renovation alignees avec {division}",
            ],
        },
    },
    {
        "name": "Carrefour",
        "email": "affaires-publiques@carrefour.com",
        "sectors": ["agriculture / alimentation", "travail / emploi"],
        "business_lines": [
            "Hypermarches Carrefour",
            "Supermarches (Carrefour Market)",
            "Proximite (Carrefour City, Express)",
            "E-commerce alimentaire",
            "Carrefour Supply Chain (logistique)",
        ],
        "products": [
            "Marques distributeur (Carrefour Bio, Reflets de France)",
            "Produits frais (fruits, legumes, boucherie)",
            "Non-alimentaire (electromenager, textile)",
            "Services financiers (Carrefour Banque)",
            "Livraison a domicile et drive",
        ],
        "regulatory_focus": [
            "Loi Egalim et negociations commerciales",
            "Etiquetage nutritionnel (Nutri-Score)",
            "Droit du travail (temps partiel, dimanche)",
            "Origine et tracabilite alimentaire",
            "Lutte contre le gaspillage alimentaire",
            "Remuneration et pouvoir d'achat",
        ],
        "context_note": (
            "2e distributeur europeen (CA ~84 Md EUR). 12 000+ magasins dans 30 pays. "
            "320 000 collaborateurs en France, tres expose au droit du travail. "
            "Double enjeu : negociations Egalim avec les fournisseurs et droit social "
            "(temps partiel subi, travail du dimanche, pouvoir d'achat)."
        ),
        "siren": "652014051",
        "code_naf": "4711F",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 83_800_000_000,
        "resultat_net": 1_300_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "93 avenue de Paris, 91300 Massy",
        "site_web": "https://www.carrefour.com",
        "description": (
            "Carrefour est le deuxieme distributeur europeen et le huitieme mondial. "
            "Present dans 30 pays avec plus de 12 000 magasins (hypermarches, supermarches, "
            "proximite, e-commerce), le groupe realise 84 milliards d'euros de CA et emploie "
            "320 000 collaborateurs, dont une grande majorite en France."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Carrefour les textes touchant a l'alimentation (Egalim, "
            "Nutri-Score, tracabilite), au droit du travail (temps partiel, dimanche, "
            "remuneration) et au commerce. Les alertes couvrent l'impact sur les hypermarches, "
            "la proximite, l'e-commerce et la supply chain."
        ),
        "exposure_range": (200_000, 30_000_000),
        "impact_angles": {
            "threat": [
                "renforcement des obligations alimentaires alourdissant les couts de {division}",
                "evolution du droit du travail impactant les 320 000 collaborateurs de {division}",
                "contraintes sur les negociations commerciales comprimant les marges de {division}",
                "nouvelles obligations de tracabilite augmentant les couts logistiques de {division}",
            ],
            "opportunity": [
                "soutien aux circuits courts beneficiant aux {product}",
                "simplification du droit du travail reduisant les couts de {division}",
                "incitations alimentaires creant un avantage pour {division}",
                "cadre favorable au e-commerce alimentaire pour {division}",
            ],
        },
    },
    {
        "name": "Thales",
        "email": "public-affairs@thalesgroup.com",
        "sectors": ["sécurité / défense", "numérique"],
        "business_lines": [
            "Defense & Security (systemes d'armes, C4I)",
            "Avionique (Thales Avionics)",
            "Spatial (satellites, segment sol)",
            "Digital Identity & Security (ex-Gemalto)",
            "Cybersecurite (Thales Cyber Solutions)",
        ],
        "products": [
            "Systemes de combat naval (AESA, sonar)",
            "Radars et systemes de defense aerienne",
            "Satellites d'observation et telecom",
            "Solutions d'identite numerique (passeports, eID)",
            "Chiffrement et HSM (CipherTrust, Luna)",
        ],
        "regulatory_focus": [
            "LPM (loi de programmation militaire)",
            "Export de defense (licences, controle)",
            "Cybersecurite (NIS2, certification)",
            "Spatial europeen (reglements ESA/UE)",
            "Identite numerique (eIDAS 2)",
            "IA de confiance et ethique de defense",
        ],
        "context_note": (
            "Leader technologique defense et securite (CA ~18 Md EUR). Double activite : "
            "systemes de defense (50% CA) et digital (identite, cyber). Tres dependant "
            "de la LPM et des budgets defense. Enjeu export : licences d'armement. "
            "Croissance forte sur la cybersecurite et l'identite numerique."
        ),
        "siren": "552059024",
        "code_naf": "2651A",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 18_400_000_000,
        "resultat_net": 1_700_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "Tour Carpe Diem, 31 place des Corolles, 92400 Courbevoie",
        "site_web": "https://www.thalesgroup.com",
        "description": (
            "Thales est un leader mondial de la haute technologie dans les domaines de la "
            "defense, de l'aeronautique, du spatial, de l'identite numerique et de la "
            "cybersecurite. Avec 18 milliards d'euros de CA et 81 000 collaborateurs dans "
            "68 pays, Thales est un fournisseur strategique des armees et gouvernements."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Thales les textes relatifs a la defense (LPM, export), "
            "a la cybersecurite (NIS2), a l'identite numerique (eIDAS 2) et au spatial. "
            "Les alertes distinguent l'impact sur Defense & Security, Digital Identity, "
            "Avionique et Spatial, et evaluent les budgets publics concernes."
        ),
        "exposure_range": (1_000_000, 80_000_000),
        "impact_angles": {
            "threat": [
                "evolution des budgets defense impactant les commandes de {division}",
                "restriction des exportations menacant le carnet de {division}",
                "normes de certification alourdissant les delais pour {division}",
                "reorientation strategique de defense impactant {division}",
            ],
            "opportunity": [
                "hausse des budgets defense creant des commandes pour {division}",
                "cadre reglementaire accelerant le deploiement de {product}",
                "investissements cybersecurite ouvrant des marches pour {division}",
                "obligations identite numerique beneficiant a {division}",
            ],
        },
    },
    {
        "name": "Veolia",
        "email": "relations-institutionnelles@veolia.com",
        "sectors": ["environnement / climat"],
        "business_lines": [
            "Eau (production, distribution, assainissement)",
            "Dechets (collecte, tri, valorisation, enfouissement)",
            "Energie (chauffage urbain, valorisation energetique)",
            "Solutions industrielles (traitement effluents, depollution)",
        ],
        "products": [
            "Gestion deleguee de services d'eau",
            "Centres de tri et recyclage",
            "Incineration avec valorisation energetique",
            "Depollution des sols et sites industriels",
            "Reseaux de chaleur urbains",
        ],
        "regulatory_focus": [
            "Regulation des services d'eau (DSP, regies)",
            "REP (responsabilite elargie du producteur)",
            "Normes PFAS et micropolluants",
            "Economie circulaire et taux de recyclage",
            "Taxonomie verte et finance durable",
            "Tarification de l'eau et accessibilite",
        ],
        "context_note": (
            "N°1 mondial des services environnementaux (CA ~45 Md EUR). 3 metiers : eau, "
            "dechets, energie. Tres sensible aux normes environnementales (PFAS, REP), "
            "a la regulation des DSP, et aux objectifs de recyclage. Enjeu : les normes "
            "PFAS peuvent generer des investissements massifs de mise en conformite."
        ),
        "siren": "403210032",
        "code_naf": "3600Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 45_300_000_000,
        "resultat_net": 1_200_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "21 rue La Boetie, 75008 Paris",
        "site_web": "https://www.veolia.com",
        "description": (
            "Veolia est le numero un mondial des services a l'environnement. Le groupe gere "
            "l'eau, les dechets et l'energie pour des collectivites et industriels dans plus "
            "de 40 pays. Avec 45 milliards d'euros de CA et 220 000 collaborateurs, Veolia "
            "est au coeur des enjeux d'economie circulaire et de depollution."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Veolia les textes relatifs a l'environnement, aux normes "
            "PFAS, a la REP, a l'economie circulaire et a la gestion de l'eau. Les alertes "
            "couvrent l'impact sur les metiers Eau, Dechets, Energie et Solutions industrielles "
            "et evaluent les investissements de conformite necessaires."
        ),
        "exposure_range": (300_000, 40_000_000),
        "impact_angles": {
            "threat": [
                "nouvelles normes environnementales imposant des investissements massifs a {division}",
                "revision des tarifs de DSP comprimant les marges de {division}",
                "objectifs de recyclage rehausses augmentant les couts de {division}",
                "obligations de depollution alourdissant la charge de {division}",
            ],
            "opportunity": [
                "obligations de traitement creant un marche en expansion pour {division}",
                "objectifs d'economie circulaire augmentant les volumes de {division}",
                "incitations a la transition energetique beneficiant a {division}",
                "normes environnementales renforcees positionnant {division} en reference",
            ],
        },
    },
    {
        "name": "Publicis",
        "email": "legal@publicisgroupe.com",
        "sectors": ["culture / médias", "numérique"],
        "business_lines": [
            "Publicis Media (achat media, planning)",
            "Publicis Sapient (transformation digitale)",
            "Publicis Creative (agences creatives)",
            "Epsilon (data marketing, CRM)",
            "Publicis Health (communication sante)",
        ],
        "products": [
            "Campagnes publicitaires multi-canal",
            "Plateformes data (Epsilon PeopleCloud)",
            "Consulting en transformation digitale",
            "Communication pharmaceutique",
            "Solutions de commerce connecte",
        ],
        "regulatory_focus": [
            "Regulation de la publicite (ARPP, loi Evin)",
            "DSA et publicite en ligne",
            "RGPD et donnees publicitaires",
            "IA generative et droits d'auteur",
            "Influence commerciale (loi influenceurs)",
            "Publicite pour produits reglementes (alcool, jeux)",
        ],
        "context_note": (
            "3e groupe de communication mondial (CA ~13 Md EUR). Fort pivot data/tech via "
            "Epsilon et Sapient. Tres expose a la regulation publicitaire, au RGPD (donnees "
            "1st party), a l'IA generative (creation de contenus) et au DSA. Enjeu : "
            "evolution des regles de ciblage publicitaire (cookies, tracking)."
        ),
        "siren": "542080601",
        "code_naf": "7311Z",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 13_100_000_000,
        "resultat_net": 1_600_000_000,
        "effectifs": "10 000 salaries et plus",
        "siege_social": "133 avenue des Champs-Elysees, 75008 Paris",
        "site_web": "https://www.publicisgroupe.com",
        "description": (
            "Publicis Groupe est le troisieme groupe de communication mondial, leader en "
            "publicite, media, data et transformation digitale. Avec 13 milliards d'euros de CA "
            "et 100 000 collaborateurs dans 100 pays, le groupe s'appuie sur Epsilon (data), "
            "Sapient (tech) et ses agences creatives pour servir les plus grandes marques."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour Publicis les textes relatifs a la publicite, au numerique, "
            "au RGPD, a l'IA generative et au DSA. Les alertes evaluent l'impact sur "
            "Publicis Media, Epsilon, Sapient et Publicis Health, avec focus sur les regles "
            "de ciblage publicitaire et de protection des donnees."
        ),
        "exposure_range": (100_000, 15_000_000),
        "impact_angles": {
            "threat": [
                "regulation du ciblage publicitaire impactant les revenus de {division}",
                "contraintes sur les donnees limitant les capacites de {division}",
                "obligations de transparence alourdissant les processus de {division}",
                "normes IA generative restreignant les outils de {division}",
            ],
            "opportunity": [
                "cadre reglementaire favorisant les acteurs transparents comme {division}",
                "investissements numeriques creant des opportunites pour {division}",
                "credit d'impot contenu beneficiant a {division}",
                "regulation des plateformes repositionnant {division} favorablement",
            ],
        },
    },
    {
        "name": "Unibail-Rodamco-Westfield",
        "email": "legal@urw.com",
        "sectors": ["logement / urbanisme", "économie / finances"],
        "business_lines": [
            "Centres commerciaux (flagship et regionaux)",
            "Bureaux et immobilier d'entreprise",
            "Convention & Exhibition (Viparis)",
            "Developpement et promotion immobiliere",
        ],
        "products": [
            "Centres commerciaux premium (Westfield, Les 4 Temps)",
            "Tours de bureaux (Majunga, Trinity)",
            "Espaces evenementiels (Palais des Congres)",
            "Projets de reconversion urbaine",
        ],
        "regulatory_focus": [
            "Urbanisme commercial (CDAC/CNAC)",
            "ZAN (zero artificialisation nette)",
            "Bail commercial et reforme locative",
            "Fiscalite immobiliere (SIIC, plus-values)",
            "Normes energetiques des batiments tertiaires",
            "Accessibilite PMR et ERP",
        ],
        "context_note": (
            "1ere fonciere commerciale europeenne (patrimoine ~54 Md EUR). Portefeuille de "
            "centres commerciaux premium et tours de bureaux. Tres sensible a l'urbanisme "
            "commercial (CDAC), au ZAN, au bail commercial et a la fiscalite SIIC. "
            "Enjeu : rarefaction du foncier commercial et adaptation energetique du parc."
        ),
        "siren": "682024785",
        "code_naf": "6820A",
        "categorie_entreprise": "GE",
        "chiffre_affaires": 3_000_000_000,
        "resultat_net": -700_000_000,
        "effectifs": "5 000 a 9 999 salaries",
        "siege_social": "7 place du Chancelier Adenauer, 75016 Paris",
        "site_web": "https://www.urw.com",
        "description": (
            "Unibail-Rodamco-Westfield est la premiere fonciere commerciale en Europe, "
            "proprietaire et operateur de centres commerciaux premium (Westfield, Les 4 Temps, "
            "Forum des Halles) et de tours de bureaux. Avec un patrimoine de 54 milliards d'euros, "
            "le groupe est un acteur majeur de l'immobilier commercial et evenementiel."
        ),
        "monitoring_explanation": (
            "LegiX surveille pour URW les textes relatifs a l'urbanisme commercial (CDAC/CNAC), "
            "au ZAN, aux baux commerciaux, a la fiscalite immobiliere et aux normes energetiques. "
            "Les alertes couvrent l'impact sur les centres commerciaux, les bureaux et Viparis."
        ),
        "exposure_range": (500_000, 60_000_000),
        "impact_angles": {
            "threat": [
                "restriction du foncier commercial menacant le pipeline de {division}",
                "evolution fiscale pesant sur les revenus de {division}",
                "normes energetiques imposant des investissements pour {division}",
                "reforme des baux impactant les conditions locatives de {division}",
            ],
            "opportunity": [
                "subventions renovation energetique beneficiant a {division}",
                "cadre favorable a la reconversion de friches pour {division}",
                "simplification des procedures d'urbanisme accelerant {division}",
                "incitations fiscales alignees avec la strategie de {division}",
            ],
        },
    },
]


def _clean_html(text: str | None) -> str:
    """Nettoie le HTML basique (balises) d'un expose/dispositif."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:300]


# ── Génération IA des analyses ──────────────────────────────────────

def _build_doc_context(
    texte: Texte | None = None,
    amendement: Amendement | None = None,
    auteur_name: str | None = None,
    groupe_name: str | None = None,
) -> dict:
    """Construit le contexte d'un document pour le prompt Claude."""
    ctx: dict = {}
    if amendement:
        ctx["type"] = "amendement"
        ctx["uid"] = amendement.uid
        ctx["numero"] = amendement.numero or ""
        ctx["article_vise"] = amendement.article_vise or ""
        ctx["etat"] = amendement.etat or ""
        ctx["sort"] = amendement.sort or ""
        ctx["resume_ia"] = amendement.resume_ia or ""
        ctx["expose_sommaire"] = _clean_html(amendement.expose_sommaire)[:200]
        ctx["themes"] = json.loads(amendement.themes) if amendement.themes else []
        ctx["date_depot"] = amendement.date_depot.isoformat() if amendement.date_depot else ""
        if auteur_name:
            ctx["auteur"] = auteur_name
        if groupe_name:
            ctx["groupe_politique"] = groupe_name
        if amendement.texte_ref:
            ctx["texte_ref"] = amendement.texte_ref
    elif texte:
        ctx["type"] = "texte"
        ctx["uid"] = texte.uid
        ctx["titre"] = texte.titre_court or texte.titre or ""
        ctx["type_libelle"] = texte.type_libelle or texte.type_code or ""
        ctx["resume_ia"] = texte.resume_ia or ""
        ctx["themes"] = json.loads(texte.themes) if texte.themes else []
        ctx["date_depot"] = texte.date_depot.isoformat() if texte.date_depot else ""
        ctx["source"] = texte.source or ""
        if texte.auteur_texte:
            ctx["auteur"] = texte.auteur_texte
    return ctx


def _generate_batch_analyses(
    client: anthropic.Anthropic,
    profile_config: dict,
    documents: list[dict],
) -> list[dict]:
    """Appelle Claude pour generer des analyses d'impact pour un batch de documents."""
    company = profile_config["name"]
    sectors = ", ".join(profile_config["sectors"])
    divisions = ", ".join(profile_config.get("business_lines", []))
    products = ", ".join(profile_config.get("products", []))
    context = profile_config.get("context_note", "")

    docs_json = json.dumps(documents, ensure_ascii=False, indent=2)

    prompt = f"""Tu es analyste senior en affaires publiques pour {company}.

CONTEXTE CLIENT :
- Entreprise : {company}
- Secteurs surveilles : {sectors}
- Divisions : {divisions}
- Produits cles : {products}
- Note strategique : {context}

MISSION : Pour chaque document legislatif ci-dessous, produis une analyse d'impact precise et professionnelle en francais impeccable.

REGLES D'ECRITURE :
- Francais soutenu, phrases completes et grammaticalement correctes
- Cite les divisions et produits specifiques de {company} concernes
- Sois factuel : mentionne l'auteur, le groupe politique, l'article vise quand disponibles
- Evalue l'urgence : le texte est-il en commission ? Adopte ? En examen ?
- Chiffre l'exposition financiere de maniere realiste pour une entreprise comme {company}

FORMAT DE REPONSE — un tableau JSON strict :
[
  {{
    "doc_index": 0,
    "impact_level": "critical|high|medium|low",
    "is_threat": true/false,
    "impact_summary": "• Premiere ligne = conclusion directe\\n• Deuxieme ligne = explication du contenu du texte\\n• Troisieme ligne = impact concret pour {company}\\n• Quatrieme ligne = ou en est le texte et urgence",
    "exposure_eur": 5000000
  }},
  ...
]

IMPORTANT :
- impact_summary utilise des bullet points separes par \\n, chaque ligne prefixee par •
- La premiere ligne est la conclusion (ex: "• Menace majeure pour la division Pharma Innovante")
- Les lignes suivantes expliquent (quoi, qui, impact, statut)
- exposure_eur est un entier en euros, realiste pour {company}
- Reponds UNIQUEMENT avec le JSON, sans texte avant ni apres

DOCUMENTS A ANALYSER :
{docs_json}"""

    try:
        response = client.messages.create(
            model=settings.enrichment_model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Extraire le JSON meme si entoure de ```json
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as e:
        logger.error("Erreur API Claude pour batch: %s", e)
        return []


def _build_contextual_actions(
    profile_config: dict,
    level: str,
    is_threat: bool,
    amendement: Amendement | None = None,
    auteur_name: str | None = None,
) -> list[dict]:
    """Construit une liste d'actions structurees (JSON-serialisable)."""
    company = profile_config["name"]
    actions = []

    if level == "critical":
        if is_threat:
            actions.append({
                "type": "draft_note",
                "label": f"Rediger une note d'impact COMEX sous 48h",
                "agent_prompt": f"Redige une note d'impact urgente pour le COMEX de {company} analysant les risques de ce texte legislatif, les divisions concernees et le chiffrage financier.",
            })
            if auteur_name:
                actions.append({
                    "type": "draft_email",
                    "label": f"Contacter {auteur_name} (auteur de l'amendement)",
                    "agent_prompt": f"Redige un email professionnel a {auteur_name} pour solliciter un echange sur cet amendement au nom de {company}. Ton diplomatique et constructif.",
                })
            actions.append({
                "type": "draft_note",
                "label": "Preparer un scenario de mitigation avec chiffrage",
                "agent_prompt": f"Redige un plan de mitigation structure pour {company} face a ce risque reglementaire, incluant les options juridiques, le calendrier et l'estimation des couts.",
            })
            actions.append({
                "type": "monitor",
                "label": "Suivre le texte en commission et en seance",
                "agent_prompt": None,
            })
        else:
            actions.append({
                "type": "draft_note",
                "label": "Rediger une note d'opportunite pour la direction",
                "agent_prompt": f"Redige une note d'opportunite strategique pour la direction de {company} expliquant comment capitaliser sur ce texte legislatif favorable.",
            })
            if auteur_name:
                actions.append({
                    "type": "draft_email",
                    "label": f"Prendre contact avec {auteur_name} pour soutenir l'initiative",
                    "agent_prompt": f"Redige un email a {auteur_name} au nom de {company} pour exprimer un soutien a cette initiative et proposer une collaboration.",
                })
            actions.append({
                "type": "draft_note",
                "label": "Preparer un plan de captation avec calendrier",
                "agent_prompt": f"Redige un plan d'action pour {company} pour saisir cette opportunite reglementaire, incluant les etapes, les interlocuteurs et le budget.",
            })
    elif level == "high":
        if is_threat:
            actions.append({
                "type": "draft_note",
                "label": f"Analyse d'impact detaillee pour {company}",
                "agent_prompt": f"Redige une analyse d'impact detaillee pour {company} evaluant les couts de mise en conformite par division et les risques juridiques.",
            })
            actions.append({
                "type": "draft_amendment",
                "label": "Preparer un contre-amendement",
                "agent_prompt": f"Redige une proposition de contre-amendement au nom de {company} pour attenuer l'impact negatif de ce texte, avec expose des motifs.",
            })
            if auteur_name:
                actions.append({
                    "type": "monitor",
                    "label": f"Surveiller les interventions de {auteur_name}",
                    "agent_prompt": None,
                })
            actions.append({
                "type": "monitor",
                "label": "Suivre le texte en commission",
                "agent_prompt": None,
            })
        else:
            actions.append({
                "type": "draft_note",
                "label": "Evaluer les benefices potentiels par division",
                "agent_prompt": f"Redige une analyse des benefices potentiels de ce texte pour chaque division de {company}, avec estimation chiffree.",
            })
            actions.append({
                "type": "draft_email",
                "label": "Identifier et contacter les interlocuteurs parlementaires",
                "agent_prompt": f"Identifie les deputes et senateurs cles sur ce sujet et redige un courrier de prise de contact au nom de {company}.",
            })
    elif level == "medium":
        actions.append({
            "type": "draft_note",
            "label": f"Inclure dans le briefing reglementaire de {company}",
            "agent_prompt": f"Redige un paragraphe de briefing reglementaire pour {company} sur ce texte legislatif, a inclure dans le prochain rapport hebdomadaire.",
        })
        actions.append({
            "type": "monitor",
            "label": "Suivre l'evolution du texte en commission",
            "agent_prompt": None,
        })
        if is_threat:
            actions.append({
                "type": "draft_note",
                "label": "Documenter l'impact potentiel",
                "agent_prompt": f"Redige une fiche de veille documentant l'impact potentiel de ce texte sur {company} pour le registre de suivi reglementaire.",
            })
    else:  # low
        actions.append({
            "type": "monitor",
            "label": "Veille passive — remonter si le texte avance",
            "agent_prompt": None,
        })

    return actions


async def seed_profiles(db: AsyncSession) -> list[ClientProfile]:
    """Insere les 10 profils clients."""
    await db.execute(delete(ImpactAlert).where(ImpactAlert.profile_id.isnot(None)))
    await db.execute(delete(ClientProfile))
    await db.commit()

    # Hash du mot de passe demo commun a tous les profils seed
    demo_password_hash = bcrypt.hashpw(b"demo2026", bcrypt.gensalt()).decode("utf-8")

    profiles = []
    for p in PROFILES:
        profile = ClientProfile(
            name=p["name"],
            email=p["email"],
            password_hash=demo_password_hash,
            sectors=json.dumps(p["sectors"], ensure_ascii=False),
            business_lines=json.dumps(p.get("business_lines", []), ensure_ascii=False),
            products=json.dumps(p.get("products", []), ensure_ascii=False),
            regulatory_focus=json.dumps(p.get("regulatory_focus", []), ensure_ascii=False),
            context_note=p["context_note"],
            # Données publiques entreprise (SIRENE)
            siren=p.get("siren"),
            code_naf=p.get("code_naf"),
            categorie_entreprise=p.get("categorie_entreprise"),
            chiffre_affaires=p.get("chiffre_affaires"),
            resultat_net=p.get("resultat_net"),
            effectifs=p.get("effectifs"),
            siege_social=p.get("siege_social"),
            site_web=p.get("site_web"),
            dirigeants=json.dumps(p.get("dirigeants", []), ensure_ascii=False),
            # Fiches générées (onboarding)
            description=p.get("description"),
            monitoring_explanation=p.get("monitoring_explanation"),
            is_active=True,
            receive_briefing=True,
            briefing_frequency="daily",
            min_signal_severity="medium",
        )
        db.add(profile)
        profiles.append(profile)

    await db.flush()
    logger.info("10 profils clients crees")
    return profiles


async def _get_auteur_name(db: AsyncSession, auteur_ref: str | None) -> str | None:
    """Recupere le nom complet d'un acteur."""
    if not auteur_ref:
        return None
    acteur = await db.get(Acteur, auteur_ref)
    if acteur:
        return f"{acteur.prenom} {acteur.nom}"
    return None


async def seed_alerts_for_profile(
    db: AsyncSession,
    profile: ClientProfile,
    profile_config: dict,
    claude_client: anthropic.Anthropic,
) -> int:
    """Genere des alertes avec analyses IA reelles pour un profil."""
    sectors = json.loads(profile.sectors)

    # 1. Collecter tous les documents matchants
    all_docs: list[dict] = []  # {"doc_ctx": dict, "texte": Texte|None, "amendement": Amendement|None, "sector": str}

    for sector in sectors:
        pattern = f'%"{sector}"%'

        # Textes matchant le secteur
        result = await db.execute(
            select(Texte)
            .where(Texte.themes.ilike(pattern))
            .order_by(func.random())
            .limit(8)
        )
        for texte in result.scalars().all():
            ctx = _build_doc_context(texte=texte)
            all_docs.append({"doc_ctx": ctx, "texte": texte, "amendement": None, "sector": sector})

        # Amendements avec resume_ia
        result = await db.execute(
            select(Amendement)
            .where(
                Amendement.themes.ilike(pattern),
                Amendement.resume_ia.isnot(None),
            )
            .order_by(func.random())
            .limit(20)
        )
        for amdt in result.scalars().all():
            auteur_name = await _get_auteur_name(db, amdt.auteur_ref)
            if not auteur_name and amdt.auteur_nom:
                auteur_name = amdt.auteur_nom
            groupe_name = None
            if amdt.groupe_ref:
                g = await db.get(Organe, amdt.groupe_ref)
                if g:
                    groupe_name = g.libelle_court or g.libelle
            elif amdt.groupe_nom:
                groupe_name = amdt.groupe_nom
            ctx = _build_doc_context(amendement=amdt, auteur_name=auteur_name, groupe_name=groupe_name)
            all_docs.append({"doc_ctx": ctx, "texte": None, "amendement": amdt, "sector": sector, "auteur_name": auteur_name})

    # 2. Traiter par batch de 10
    BATCH_SIZE = 10
    count = 0
    total_batches = (len(all_docs) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(all_docs), BATCH_SIZE):
        batch = all_docs[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        logger.info("    Batch %d/%d (%d docs)...", batch_num, total_batches, len(batch))

        # Preparer les contextes pour Claude
        doc_contexts = []
        for i, item in enumerate(batch):
            ctx = item["doc_ctx"].copy()
            ctx["doc_index"] = i
            doc_contexts.append(ctx)

        # Appel Claude
        analyses = await asyncio.to_thread(
            _generate_batch_analyses, claude_client, profile_config, doc_contexts
        )

        if not analyses:
            logger.warning("    Batch %d: pas de reponse Claude, skip", batch_num)
            continue

        # Creer les alertes
        for analysis in analyses:
            idx = analysis.get("doc_index", -1)
            if idx < 0 or idx >= len(batch):
                continue
            item = batch[idx]

            level = analysis.get("impact_level", "medium")
            if level not in ("critical", "high", "medium", "low"):
                level = "medium"
            is_threat = analysis.get("is_threat", True)
            summary = analysis.get("impact_summary", "")
            exposure = analysis.get("exposure_eur", 0)

            # Actions structurees basees sur le level
            auteur_name = item.get("auteur_name")
            actions = _build_contextual_actions(
                profile_config, level, is_threat,
                amendement=item["amendement"], auteur_name=auteur_name,
            )

            # Themes matches
            doc = item["texte"] or item["amendement"]
            doc_themes = []
            if doc and doc.themes:
                try:
                    doc_themes = json.loads(doc.themes)
                except (json.JSONDecodeError, TypeError):
                    pass
            client_sectors = json.loads(profile.sectors)
            matched = list(set(doc_themes) & set(client_sectors))

            # Date repartie sur 30 jours
            days_ago = random.randint(0, 30)
            created = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))

            alert = ImpactAlert(
                profile_id=profile.id,
                impact_level=level,
                impact_summary=summary,
                exposure_eur=exposure,
                matched_themes=json.dumps(matched, ensure_ascii=False),
                action_required=json.dumps(actions, ensure_ascii=False),
                is_threat=is_threat,
                is_read=random.random() < 0.3,
                created_at=created,
            )

            if item["texte"]:
                alert.texte_uid = item["texte"].uid
            if item["amendement"]:
                alert.amendement_uid = item["amendement"].uid
                if item["amendement"].texte_ref:
                    alert.texte_uid = item["amendement"].texte_ref

            db.add(alert)
            count += 1

        # Rate limiting
        await asyncio.sleep(0.3)

    return count


async def main():
    """Point d'entree principal."""
    # Verifier la cle API
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY non configuree dans .env — impossible de generer les analyses IA.")
        return

    claude_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    logger.info("Claude API configuree (modele: %s)", settings.enrichment_model)

    async with async_session() as db:
        profiles = await seed_profiles(db)
        await db.commit()

        total_alerts = 0
        for profile, config in zip(profiles, PROFILES):
            logger.info("Generation alertes pour %s...", profile.name)
            n = await seed_alerts_for_profile(db, profile, config, claude_client)
            logger.info("  %s : %d alertes", profile.name, n)
            total_alerts += n
            await db.commit()  # Commit apres chaque profil pour ne pas perdre le travail

        logger.info("=== SEED TERMINE ===")
        logger.info("  Profils : %d", len(profiles))
        logger.info("  Alertes : %d", total_alerts)

        for profile in profiles:
            result = await db.execute(
                select(func.count()).where(ImpactAlert.profile_id == profile.id)
            )
            n = result.scalar() or 0
            result2 = await db.execute(
                select(func.count()).where(
                    ImpactAlert.profile_id == profile.id,
                    ImpactAlert.impact_level.in_(["critical", "high"]),
                )
            )
            n_urgent = result2.scalar() or 0
            logger.info("  %s : %d alertes (%d urgentes)", profile.name, n, n_urgent)


if __name__ == "__main__":
    asyncio.run(main())
