# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Telegram notifications: `src/notify/telegram.py` sends messages via the
  Telegram Bot API, and `src/notify/notifier.py` reads the latest rows from
  the database and pushes a formatted price update to the chat.
- `src/main.py` pipeline that scrapes gold prices, stores them, and sends a
  Telegram notification (`python -m src.main`).
- `src/common/config.py` to load `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and
  `DB_PATH` from the environment / `.env`.
- Database helpers `insert_stocks()` and `get_latest_stocks()` in
  `src/common/conn_details.py`.
- `.env.example` template and `python-dotenv` dependency.
- Setup and usage instructions in `README.md`.

### Changed
- `src/common/conn_details.py` now reads `DB_PATH` from `config` instead of a
  hard-coded constant.
- `.gitignore` now excludes `.env` and `*.db`.
