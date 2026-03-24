"""Seed profil demo Eramet — metaux critiques et mines."""

import asyncio
import json
import sys
sys.path.insert(0, "/Users/emmanuelblezes/legix")

from legix.core.database import async_session, init_db
from legix.core.models import ClientProfile


async def seed():
    await init_db()

    async with async_session() as db:
        profile = ClientProfile(
            name="Eramet",
            description=(
                "Groupe minier et metallurgique francais, leader mondial du manganese "
                "et du nickel. Present dans les metaux critiques pour la transition "
                "energetique (lithium, nickel, cobalt). Usines en France (Nouvelle-Caledonie, "
                "Dunkerque) et a l'international (Gabon, Indonesie, Argentine)."
            ),
            sectors=json.dumps(["industrie", "energie", "mines"]),
            business_lines=json.dumps([
                "Manganese (Comilog)",
                "Nickel (SLN Nouvelle-Caledonie)",
                "Sables mineraux (TiZir)",
                "Lithium (Argentine)",
                "Recyclage batteries",
            ]),
            products=json.dumps([
                "Manganese haute purete",
                "Ferronickel",
                "Dioxyde de titane",
                "Carbonate de lithium",
                "Alliages haute performance",
            ]),
            regulatory_focus=json.dumps([
                "Code minier",
                "CSRD / taxonomie verte",
                "Reglement batteries UE",
                "Critical Raw Materials Act",
                "Devoir de vigilance",
                "CBAM (mecanisme d'ajustement carbone)",
                "Directive minerais de conflit",
                "REACh (substances chimiques)",
                "Loi climat et resilience",
            ]),
            is_active=True,

            # --- Configuration de veille personnalisee ---
            watch_keywords=json.dumps([
                "metaux critiques", "matieres premieres strategiques",
                "manganese", "nickel", "lithium", "cobalt",
                "mines", "code minier", "permis minier",
                "CSRD", "taxonomie", "devoir de vigilance",
                "batteries", "vehicules electriques",
                "CBAM", "carbone aux frontieres",
                "Nouvelle-Caledonie", "SLN",
                "minerais de conflit", "due diligence",
                "recyclage batteries", "economie circulaire",
                "Critical Raw Materials", "CRM Act",
            ]),
            watch_keywords_exclude=json.dumps([
                "crypto", "bitcoin", "NFT",
                "agriculture biologique", "pesticides",
            ]),
            watched_politicians=json.dumps([
                "Emmanuel Macron",
                "Roland Lescure",
                "Christophe Bechu",
            ]),
            watched_ngos=json.dumps([
                "France Nature Environnement",
                "Les Amis de la Terre",
                "Greenpeace France",
                "Sherpa",
                "Notre Affaire a Tous",
                "Transparency International",
            ]),
            watched_regulators=json.dumps([
                "ADEME",
                "BRGM",
                "Commission europeenne - DG GROW",
                "Autorite environnementale",
            ]),
            eu_watched_committees=json.dumps([
                "ITRE",
                "ENVI",
                "INTA",
            ]),
            eu_watch_keywords=json.dumps([
                "Critical Raw Materials Act",
                "Battery Regulation",
                "CBAM",
                "CSRD",
                "conflict minerals",
            ]),
            watched_media=json.dumps([
                "Les Echos", "Le Monde", "L'Usine Nouvelle",
                "BFM Business", "Reuters", "Bloomberg",
                "Mining Weekly", "Metal Bulletin",
            ]),
            watched_federations=json.dumps([
                "France Industrie",
                "A3M (Alliance des mineraux, mineraux et metaux)",
                "MEDEF",
                "Euromines",
            ]),
            watched_think_tanks=json.dumps([
                "France Strategie",
                "IFRI",
                "Fondation pour la Nature et l'Homme",
                "Institut Montaigne",
            ]),
            watched_inspections=json.dumps([
                "Cour des Comptes",
                "CGEDD",
                "IGF",
            ]),

            # --- Strategie PA ---
            pa_strategy=(
                "Positionner Eramet comme acteur cle de la souverainete europeenne "
                "sur les metaux critiques. Defendre un cadre reglementaire favorable "
                "a l'extraction responsable en Europe. Soutenir le CRM Act et le "
                "recyclage. Anticiper et influencer le code minier reforme."
            ),
            pa_priorities=json.dumps([
                "Critical Raw Materials Act — implementation favorable",
                "Reforme du code minier — permis acceleres",
                "CSRD — reporting mine responsable",
                "Reglement batteries — approvisionnement responsable",
                "CBAM — inclusion des metaux transformes",
                "Devoir de vigilance — cadre EU harmonise",
            ]),
        )
        db.add(profile)
        await db.commit()
        print(f"Profil Eramet cree (id={profile.id})")
        print(f"  Secteurs: {json.loads(profile.sectors)}")
        print(f"  Keywords: {len(json.loads(profile.watch_keywords))} mots-cles")
        print(f"  ONG surveillees: {len(json.loads(profile.watched_ngos))}")
        print(f"  Priorites PA: {len(json.loads(profile.pa_priorities))}")


if __name__ == "__main__":
    asyncio.run(seed())
