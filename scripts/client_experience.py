"""LegiX — Experience client en terminal.

Simule ce qu'un client recevrait au quotidien.
Usage :
    python3 -m legix.scripts.client_experience              # Liste les clients
    python3 -m legix.scripts.client_experience --client 11  # Experience Danone
    python3 -m legix.scripts.client_experience --client 11 --brief  # Genere les briefs manquants
"""

import asyncio
import argparse
import json
import logging
import sys
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

logging.basicConfig(level=logging.WARNING)

# Couleurs terminal
RED = "\033[91m"
ORANGE = "\033[93m"
GREEN = "\033[92m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

LEVEL_COLORS = {
    "critical": RED,
    "high": ORANGE,
    "medium": BLUE,
    "low": DIM,
}


def _parse_json(val):
    if not val:
        return []
    try:
        return json.loads(val) if isinstance(val, str) else val
    except (json.JSONDecodeError, TypeError):
        return []


def _fmt_eur(n):
    if not n:
        return "-"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} Md\u20ac"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.0f} M\u20ac"
    if n >= 1_000:
        return f"{n / 1_000:.0f} K\u20ac"
    return f"{n:.0f} \u20ac"


async def list_clients():
    from legix.core.database import async_session, init_db
    from legix.core.models import ClientProfile, ImpactAlert, TexteFollowUp, TexteBrief

    await init_db()
    async with async_session() as db:
        profiles = (await db.execute(
            select(ClientProfile).where(ClientProfile.is_active.is_(True)).order_by(ClientProfile.name)
        )).scalars().all()

        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}  LegiX — Clients actifs{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        for p in profiles:
            alerts = (await db.execute(select(func.count()).where(ImpactAlert.profile_id == p.id))).scalar()
            followups = (await db.execute(select(func.count()).where(TexteFollowUp.profile_id == p.id))).scalar()
            briefs = (await db.execute(select(func.count()).where(TexteBrief.profile_id == p.id))).scalar()
            sectors = _parse_json(p.sectors)

            print(f"  {BOLD}[{p.id:2d}]{RESET} {p.name}")
            print(f"       Secteurs : {', '.join(sectors)}")
            print(f"       {alerts} alertes | {followups} textes suivis | {briefs} briefs")
            print()

        print(f"{DIM}  Usage : python3 -m legix.scripts.client_experience --client ID{RESET}\n")


async def client_dashboard(profile_id: int, generate_briefs: bool = False):
    from legix.core.database import async_session, init_db
    from legix.core.models import (
        ClientProfile, ImpactAlert, TexteFollowUp, TexteBrief,
        Texte, Amendement, Signal
    )

    await init_db()
    async with async_session() as db:
        profile = await db.get(ClientProfile, profile_id)
        if not profile:
            print(f"{RED}Profil {profile_id} introuvable{RESET}")
            return

        sectors = _parse_json(profile.sectors)
        business_lines = _parse_json(profile.business_lines)
        regulatory_focus = _parse_json(profile.regulatory_focus)

        # === EN-TETE ===
        print(f"\n{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}  LegiX — Briefing pour {profile.name}{RESET}")
        print(f"  {datetime.now().strftime('%A %d %B %Y, %Hh%M')}")
        print(f"{BOLD}{'='*70}{RESET}\n")

        # Profil
        print(f"  {DIM}Secteurs : {', '.join(sectors)}{RESET}")
        if business_lines:
            print(f"  {DIM}Metiers  : {', '.join(business_lines[:3])}...{RESET}")
        if regulatory_focus:
            print(f"  {DIM}Veille   : {', '.join(regulatory_focus[:3])}...{RESET}")
        print()

        # === STATS GLOBALES ===
        total_alerts = (await db.execute(
            select(func.count()).where(ImpactAlert.profile_id == profile_id)
        )).scalar()
        urgent_alerts = (await db.execute(
            select(func.count()).where(
                ImpactAlert.profile_id == profile_id,
                ImpactAlert.impact_level.in_(["critical", "high"])
            )
        )).scalar()
        exposure = (await db.execute(
            select(func.sum(ImpactAlert.exposure_eur)).where(
                ImpactAlert.profile_id == profile_id
            )
        )).scalar() or 0
        threats = (await db.execute(
            select(func.count()).where(
                ImpactAlert.profile_id == profile_id,
                ImpactAlert.is_threat.is_(True)
            )
        )).scalar()

        print(f"  {RED}{BOLD}{urgent_alerts} URGENTS{RESET}     "
              f"{ORANGE}{total_alerts - urgent_alerts} a suivre{RESET}     "
              f"{BOLD}Exposition : {_fmt_eur(exposure)}{RESET}")
        print(f"  {RED}{threats} menaces{RESET}  |  {GREEN}{total_alerts - threats} opportunites{RESET}")
        print()

        # === TEXTES SUIVIS ===
        followups = (await db.execute(
            select(TexteFollowUp)
            .options(joinedload(TexteFollowUp.texte))
            .where(TexteFollowUp.profile_id == profile_id)
            .order_by(TexteFollowUp.updated_at.desc())
        )).unique().scalars().all()

        print(f"  {BOLD}--- TEXTES SOUS SURVEILLANCE ({len(followups)}) ---{RESET}\n")

        for fu in followups:
            texte = fu.texte
            if not texte:
                continue
            themes = _parse_json(texte.themes)
            source = texte.source or "?"

            # Brief associe ?
            brief = (await db.execute(
                select(TexteBrief).where(
                    TexteBrief.profile_id == profile_id,
                    TexteBrief.texte_uid == texte.uid,
                )
            )).scalar_one_or_none()

            status_icon = {
                "watching": f"{BLUE}[SUIVI]{RESET}",
                "escalated": f"{RED}[ESCALADE]{RESET}",
                "resolved": f"{GREEN}[RESOLU]{RESET}",
            }.get(fu.status, f"[{fu.status}]")

            # Compter amendements
            nb_amdts = (await db.execute(
                select(func.count()).where(Amendement.texte_ref == texte.uid)
            )).scalar()

            print(f"  {status_icon} {BOLD}{texte.titre_court or texte.titre or texte.uid}{RESET}")
            print(f"    Source: {source} | {nb_amdts} amendements | Themes: {', '.join(themes[:3])}")
            if texte.resume_ia:
                print(f"    {DIM}{texte.resume_ia[:150]}...{RESET}")

            if brief:
                level_color = LEVEL_COLORS.get(brief.impact_level, "")
                print(f"    {level_color}{BOLD}Impact: {brief.impact_level}{RESET}"
                      f" | Exposition: {_fmt_eur(brief.exposure_eur)}"
                      f" | {'MENACE' if brief.is_threat else 'OPPORTUNITE'}")
                if brief.executive_summary:
                    summary = brief.executive_summary[:300]
                    if "**" in summary:
                        # Simplifier le markdown pour le terminal
                        summary = summary.replace("**", "")
                    print(f"    {summary}")

                # Actions
                actions = _parse_json(brief.action_plan)
                if actions:
                    print(f"    {CYAN}Actions recommandees :{RESET}")
                    for a in actions[:3]:
                        if isinstance(a, dict):
                            print(f"      {a.get('priority', '?')}. {a.get('action', '?')}"
                                  f" {DIM}(deadline: {a.get('deadline', '?')}){RESET}")

                # Contacts cles
                contacts = _parse_json(brief.key_contacts)
                if contacts:
                    print(f"    {CYAN}Contacts cles :{RESET}")
                    for c in contacts[:3]:
                        if isinstance(c, dict):
                            print(f"      - {c.get('nom', '?')} ({c.get('groupe', '?')})"
                                  f" {DIM}— {c.get('why_relevant', '')[:80]}{RESET}")
            else:
                print(f"    {DIM}[Pas de brief genere — lance avec --brief pour en creer]{RESET}")

            print()

        # === ALERTES RECENTES ===
        recent_alerts = (await db.execute(
            select(ImpactAlert)
            .where(ImpactAlert.profile_id == profile_id)
            .order_by(ImpactAlert.created_at.desc())
            .limit(10)
        )).scalars().all()

        print(f"  {BOLD}--- ALERTES RECENTES (top 10 / {total_alerts}) ---{RESET}\n")

        for a in recent_alerts:
            level_color = LEVEL_COLORS.get(a.impact_level, "")
            threat_label = f"{RED}MENACE{RESET}" if a.is_threat else f"{GREEN}OPP.{RESET}"
            summary = (a.impact_summary or "")[:120]
            themes = _parse_json(a.matched_themes)

            print(f"  {level_color}[{a.impact_level:8s}]{RESET} {threat_label}"
                  f" | {_fmt_eur(a.exposure_eur):>8s}"
                  f" | {', '.join(themes[:2])}")
            if summary:
                print(f"    {summary}")
            print()

        # === CE QUI MANQUE (diagnostic) ===
        print(f"  {BOLD}--- DIAGNOSTIC : CE QUE LE CLIENT NE RECOIT PAS ENCORE ---{RESET}\n")

        # Followups sans brief
        no_brief = 0
        for fu in followups:
            brief = (await db.execute(
                select(TexteBrief).where(
                    TexteBrief.profile_id == profile_id,
                    TexteBrief.texte_uid == fu.texte_uid,
                )
            )).scalar_one_or_none()
            if not brief:
                no_brief += 1

        issues = []
        if no_brief > 0:
            issues.append(f"{RED}  {no_brief} texte(s) suivi(s) sans brief genere{RESET}")
        if not profile.telegram_chat_id:
            issues.append(f"{ORANGE}  Telegram non configure — pas d'alertes push{RESET}")
        if not profile.email:
            issues.append(f"{ORANGE}  Email non configure — pas de digest{RESET}")
        if not profile.description or len(profile.description or "") < 50:
            issues.append(f"{ORANGE}  Profil client pauvre — enrichissement insuffisant{RESET}")
        if not _parse_json(profile.key_risks):
            issues.append(f"{ORANGE}  Aucun risque cle identifie (key_risks vide){RESET}")
        if not _parse_json(profile.products):
            issues.append(f"{ORANGE}  Produits non renseignes — briefs generiques{RESET}")

        if issues:
            for issue in issues:
                print(issue)
        else:
            print(f"  {GREEN}Tout semble OK{RESET}")
        print()

        # === GENERATION DE BRIEFS ===
        if generate_briefs and no_brief > 0:
            print(f"  {BOLD}--- GENERATION DE BRIEFS ---{RESET}\n")
            from legix.services.texte_brief import generate_texte_brief

            for fu in followups:
                brief_exists = (await db.execute(
                    select(TexteBrief).where(
                        TexteBrief.profile_id == profile_id,
                        TexteBrief.texte_uid == fu.texte_uid,
                    )
                )).scalar_one_or_none()

                if brief_exists:
                    continue

                nb_amdts = (await db.execute(
                    select(func.count()).where(Amendement.texte_ref == fu.texte_uid)
                )).scalar()

                if nb_amdts == 0:
                    print(f"  {DIM}Skip {fu.texte_uid} — pas d'amendements{RESET}")
                    continue

                print(f"  Generating brief for {fu.texte_uid} ({nb_amdts} amdts)...")
                try:
                    brief = await generate_texte_brief(db, fu.texte_uid, profile, fu)
                    print(f"  {GREEN}OK — impact={brief.impact_level}, "
                          f"exposure={_fmt_eur(brief.exposure_eur)}{RESET}")
                except Exception as e:
                    print(f"  {RED}ERREUR : {e}{RESET}")

            print()


async def main():
    parser = argparse.ArgumentParser(description="LegiX — Experience client")
    parser.add_argument("--client", type=int, help="ID du profil client")
    parser.add_argument("--brief", action="store_true", help="Generer les briefs manquants")
    args = parser.parse_args()

    if args.client:
        await client_dashboard(args.client, generate_briefs=args.brief)
    else:
        await list_clients()


if __name__ == "__main__":
    asyncio.run(main())
