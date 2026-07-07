# Trade To Go

**Python version** : `3.11`

Scrapes Bursa Malaysia gold prices from the live price stream, stores them in
SQLite, tracks the running min/max, and pushes updates to Telegram.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in your values
```

Create a Telegram bot with [@BotFather](https://t.me/BotFather) to get a
`TELEGRAM_BOT_TOKEN`. Send your bot a message, then find your chat id at
`https://api.telegram.org/bot<TOKEN>/getUpdates` and set `TELEGRAM_CHAT_ID`.

## Run

From the `src` directory:

```bash
cd src
python main.py
```

Each run:

1. Fetches the current buy/sell price from the Bursa gold websocket
   (`wss://bgd-adam.bursamalaysia.com/bgd/pricestream`).
2. Stores the row in the `bursaGold` table (`gold.db`).
3. Updates `data/temp/goldMinMax.json` — the all-time min and max price, each
   with the timestamp it was recorded. Only rewritten when a record is beaten.
4. Sends the buy/sell prices to your Telegram chat.

## Project layout

```
src/
├── main.py            # pipeline entry point
├── extract/get_gold.py    # websocket price scraper
├── data/store_gold.py     # SQLite writer (bursaGold table)
├── notify/telegram.py     # Telegram Bot API client
├── notify/notifier.py     # message formatting (notify_gold, notify_latest)
└── common/config.py       # .env loading (token, chat id, DB_PATH)
```
