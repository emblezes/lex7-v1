"""Notifier Telegram — envoi d'alertes via Bot API."""

import logging

import httpx

from legix.core.config import settings

logger = logging.getLogger(__name__)

LEVEL_EMOJI = {
    "critical": "\u26a0\ufe0f",  # ⚠️
    "high": "\U0001f534",        # 🔴
    "medium": "\U0001f7e0",      # 🟠
    "low": "\U0001f7e2",         # 🟢
}


class TelegramNotifier:
    """Envoi de messages via Telegram Bot API."""

    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.client = httpx.AsyncClient(timeout=10.0)

    async def send_message(self, chat_id: str, text: str) -> bool:
        """Envoie un message texte via Telegram."""
        if not self.bot_token:
            logger.warning("Telegram bot token non configuré — skip")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            response = await self.client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            })
            if response.status_code == 200:
                return True
            logger.warning("Telegram API status %d: %s", response.status_code, response.text[:200])
            return False
        except Exception as e:
            logger.error("Erreur envoi Telegram: %s", e)
            return False

    def format_alert(
        self,
        subject: str,
        body: str,
        impact_level: str = "medium",
        alert_id: int | None = None,
    ) -> str:
        """Formate un message d'alerte pour Telegram."""
        emoji = LEVEL_EMOJI.get(impact_level, "\u2139\ufe0f")
        dashboard_link = settings.dashboard_url

        parts = [
            f"{emoji} <b>{subject}</b>",
            "",
            body[:400],
        ]

        if alert_id and dashboard_link:
            parts.append("")
            parts.append(f'\U0001f4ca <a href="{dashboard_link}/alertes/{alert_id}">Voir dans LegiX</a>')

        return "\n".join(parts)

    def format_briefing_summary(self, title: str, summary: str) -> str:
        """Formate un résumé de briefing pour Telegram."""
        return (
            f"\U0001f4cb <b>{title}</b>\n\n"
            f"{summary[:500]}\n\n"
            f'\U0001f4ca <a href="{settings.dashboard_url}/briefings">Lire le briefing complet</a>'
        )
