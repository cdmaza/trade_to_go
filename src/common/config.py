import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


DB_PATH = os.getenv("DB_PATH", "stock.db")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def require_telegram_config():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Telegram is not configured. Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID (see .env.example)."
        )
    return TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
