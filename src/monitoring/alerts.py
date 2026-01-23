from __future__ import annotations

import json
from urllib.request import Request, urlopen

from loguru import logger


class AlertManager:
    """Sends trading alerts via Slack or Telegram."""

    def __init__(
        self,
        slack_webhook: str = "",
        telegram_token: str = "",
        telegram_chat_id: str = "",
    ):
        self.slack_webhook = slack_webhook
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id

    def send(self, message: str, level: str = "info") -> None:
        """Send alert to all configured channels."""
        if self.slack_webhook:
            self._send_slack(message)
        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(message)
        logger.log(level.upper(), f"Alert: {message}")

    def _send_slack(self, message: str) -> None:
        try:
            data = json.dumps({"text": f"[Autostock] {message}"}).encode()
            req = Request(
                self.slack_webhook,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urlopen(req, timeout=5)
        except Exception as e:
            logger.warning(f"Slack alert failed: {e}")

    def _send_telegram(self, message: str) -> None:
        try:
            url = (
                f"https://api.telegram.org/bot{self.telegram_token}"
                f"/sendMessage?chat_id={self.telegram_chat_id}"
                f"&text=[Autostock] {message}"
            )
            urlopen(url, timeout=5)
        except Exception as e:
            logger.warning(f"Telegram alert failed: {e}")
