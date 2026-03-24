"""Notifier Email — envoi de digests et alertes par SMTP."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from legix.core.config import settings

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Envoi d'emails via SMTP."""

    async def send_email(
        self,
        to: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
    ) -> bool:
        """Envoie un email via SMTP."""
        if not settings.smtp_host:
            logger.warning("SMTP non configuré — skip email")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception as e:
            logger.error("Erreur envoi email à %s: %s", to, e)
            return False

    def format_alert_html(
        self,
        subject: str,
        body: str,
        impact_level: str = "medium",
        alert_id: int | None = None,
    ) -> str:
        """Génère le HTML d'un email d'alerte."""
        color_map = {
            "critical": "#dc2626",
            "high": "#ea580c",
            "medium": "#d97706",
            "low": "#16a34a",
        }
        color = color_map.get(impact_level, "#6b7280")

        link = ""
        if alert_id:
            link = (
                f'<p><a href="{settings.dashboard_url}/alertes/{alert_id}" '
                f'style="color:{color}">Voir dans LegiX</a></p>'
            )

        return f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="border-left: 4px solid {color}; padding-left: 16px;">
        <h2 style="color: {color}; margin: 0 0 8px 0;">{subject}</h2>
        <p style="color: #374151; line-height: 1.6;">{body}</p>
        {link}
    </div>
    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
    <p style="color: #9ca3af; font-size: 12px;">LegiX — Intelligence réglementaire active</p>
</body>
</html>"""

    def format_digest_html(
        self,
        company_name: str,
        alerts_summary: list[dict],
        briefing_text: str | None = None,
    ) -> str:
        """Génère le HTML d'un digest quotidien/hebdomadaire."""
        alerts_html = ""
        for a in alerts_summary[:10]:
            level = a.get("impact_level", "medium")
            color = {"critical": "#dc2626", "high": "#ea580c", "medium": "#d97706", "low": "#16a34a"}.get(level, "#6b7280")
            alerts_html += f"""
            <div style="border-left: 3px solid {color}; padding: 8px 12px; margin: 8px 0;">
                <strong style="color: {color};">[{level.upper()}]</strong>
                {a.get('summary', '')[:200]}
            </div>"""

        briefing_section = ""
        if briefing_text:
            briefing_section = f"""
            <h3 style="color: #1f2937;">Briefing du jour</h3>
            <div style="background: #f9fafb; padding: 16px; border-radius: 8px;">
                {briefing_text[:1000]}
            </div>"""

        return f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h1 style="color: #1f2937;">LegiX — Digest pour {company_name}</h1>

    <h3 style="color: #1f2937;">Alertes récentes</h3>
    {alerts_html if alerts_html else '<p style="color: #6b7280;">Aucune nouvelle alerte.</p>'}

    {briefing_section}

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;">
    <p style="color: #9ca3af; font-size: 12px;">
        <a href="{settings.dashboard_url}">Accéder à LegiX</a>
    </p>
</body>
</html>"""
