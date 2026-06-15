#Trade To Go


**Python version** : `3.11`

Scrapes Bursa Malaysia gold prices, stores them in a database, and pushes
notifications to Telegram.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your values
```

Create a Telegram bot with [@BotFather](https://t.me/BotFather) to get a
`TELEGRAM_BOT_TOKEN`. Send your bot a message, then find your chat id at
`https://api.telegram.org/bot<TOKEN>/getUpdates` and set `TELEGRAM_CHAT_ID`.

## Run

From the project root:

```bash
python -m src.main
```

This scrapes the latest prices, stores them in the SQLite database
(`DB_PATH`, default `stock.db`), and sends the latest rows to your Telegram
chat.

To send a notification from whatever is already in the database without
re-scraping:

```python
from src.notify.notifier import notify_latest
notify_latest()
```
