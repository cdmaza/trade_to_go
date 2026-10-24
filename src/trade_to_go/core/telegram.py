"""Send-only Telegram client (ported from the legacy src/notify/telegram.py)."""

from __future__ import annotations

import requests

from trade_to_go.core.config import require_env

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str, parse_mode: str = "HTML", disable_web_page_preview: bool = True) -> dict:
    """Push a message to the configured chat.

    Returns the Telegram API response JSON. Raises on network errors or a
    non-ok response from Telegram.
    """
    token, chat_id = require_env("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")

    response = requests.post(
        API_URL.format(token=token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        },
        timeout=15,
    )
    response.raise_for_status()

    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API error: {payload}")
    return payload
