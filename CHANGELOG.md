# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Gold price scraper `src/extract/get_gold.py` that reads buy/sell prices from
  the Bursa Malaysia websocket price stream.
- SQLite storage `src/data/store_gold.py` writing to the `bursaGold` table in
  `gold.db`.
- Running min/max tracker (`get_MinMax` in `src/main.py`): keeps the all-time
  min and max price with the timestamp each was recorded in
  `data/temp/goldMinMax.json`, only rewriting when a record is beaten.
- `notify_gold()` in `src/notify/notifier.py` — pushes the scraped buy/sell
  prices to Telegram after every run.
- Telegram notifications: `src/notify/telegram.py` sends messages via the
  Telegram Bot API, and `src/notify/notifier.py` reads the latest rows from
  the database and pushes a formatted price update to the chat.
- `src/main.py` pipeline that scrapes gold prices, stores them, updates
  min/max, and sends a Telegram notification (`cd src && python main.py`).
- `src/common/config.py` to load `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and
  `DB_PATH` from the environment / `.env`.
- Database helpers `insert_stocks()` and `get_latest_stocks()` in
  `src/common/conn_details.py`.
- `.env.example` template and `python-dotenv` dependency.
- Setup and usage instructions in `README.md`.

### Changed
- Imports are now relative to `src/` (no `src.` prefix), so the app runs with
  `python main.py` from inside `src/`.
- `src/common/conn_details.py` now reads `DB_PATH` from `config` instead of a
  hard-coded constant.
- `.gitignore` now excludes `.env` and `*.db`.
- `requirements.txt` cleaned up: removed non-installable `sqlite3` entry,
  added `websocket-client`.

### Fixed
- `INSERT` in `src/data/store_gold.py` had 5 placeholders for 4 columns and
  missing spaces in the concatenated SQL, so the table was created but no rows
  were ever inserted. Now uses `INSERT OR REPLACE` with matching placeholders.
- `goldMinMax.json` migration: old flat-format files (`{"min": 1.0, "max": 2.0}`)
  are upgraded to the new per-record `{price, timedate}` structure on read.
