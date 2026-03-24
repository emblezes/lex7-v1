"""Export PDF — génération de briefings et notes d'impact en PDF."""

import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


def export_briefing_pdf(
    company_name: str,
    date_str: str,
    content_sections: dict,
) -> bytes:
    """Génère un PDF de briefing quotidien.

    Args:
        company_name: Nom de l'entreprise
        date_str: Date du briefing (ex: "14/03/2026")
        content_sections: Dict avec clés synthese, alertes, signaux, agenda, actions

    Returns:
        bytes du PDF généré
    """
    from weasyprint import HTML

    template = _env.get_template("briefing.html")
    html_str = template.render(
        company_name=company_name,
        date=date_str,
        sections=content_sections,
    )
    return HTML(string=html_str).write_pdf()


def export_impact_note_pdf(
    company_name: str,
    alert_summary: str,
    impact_level: str,
    content: str,
    metadata: dict | None = None,
) -> bytes:
    """Génère un PDF de note d'impact.

    Args:
        company_name: Nom de l'entreprise
        alert_summary: Résumé de l'alerte
        impact_level: critical/high/medium/low
        content: Contenu markdown de la note (déjà généré par RedacteurAgent)
        metadata: Métadonnées additionnelles (auteur, date, etc.)

    Returns:
        bytes du PDF généré
    """
    from weasyprint import HTML

    template = _env.get_template("impact_note.html")
    html_str = template.render(
        company_name=company_name,
        alert_summary=alert_summary,
        impact_level=impact_level,
        content=content,
        metadata=metadata or {},
        color=_level_color(impact_level),
    )
    return HTML(string=html_str).write_pdf()


def _level_color(level: str) -> str:
    """Couleur CSS par niveau d'impact."""
    return {
        "critical": "#dc2626",
        "high": "#ea580c",
        "medium": "#d97706",
        "low": "#16a34a",
    }.get(level, "#6b7280")
