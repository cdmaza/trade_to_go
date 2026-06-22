import requests

from src.common.config import require_telegram_config

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text, parse_mode="HTML", disable_web_page_preview=True):
    """Push a message to the configured Telegram chat.

    Returns the Telegram API response JSON. Raises on network errors or a
    non-ok response from Telegram.
    """
    token, chat_id = require_telegram_config()

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
