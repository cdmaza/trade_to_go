# Trade To Go

Evidence-based alerts for gold in ringgit and US equities. Data lands in
raw → staging → curated Parquet layers, is queried through DuckDB, and alerts
are sent to Telegram only for rules that beat their benchmark after costs.

**Python**: 3.12, managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
uv sync                      # core + dev deps
uv sync --extra backtest     # adds vectorbt
uv sync --extra broker       # adds moomoo-api (needs the OpenD gateway running)
cp .env.example .env         # then fill in your secrets
uv run ttg init
```

## Today's call (start here)

```bash
uv run ttg watch add AAPL MSFT      # your own stocks; always shown, whatever the call is
uv run ttg call --refresh           # fresh prices, then the call (also writes reports/dashboard.html)
uv run ttg call --refresh --notify  # same, and a Telegram digest when a call changed
```

You get three things:

- **Gold (MYR)**: BUY / HOLD / SELL from four trend checks (10-month average and 12-month momentum,
  each on the last completed month-end and on today's price), the price levels that would flip it,
  the buy/sell spread you pay, and what the backtest has decided so far. Prices come from BNM Kijang
  Emas (no key needed) until you import LBMA history.
- **Your stocks**: every name in `config/watchlist.yaml` with its call, trend line, returns, RSI
  and the level that breaks the call.
- **Potential stocks**: only the top few names from the `candidates` pool in `config/universe.yaml`
  that are currently rated BUY, ranked by momentum. Nothing else from the pool is shown.

A call is a trend reading from price data, not a proven edge: the gold backtest has not named a
rule that beats plain monthly DCA, and the stock filter has no backtest yet. Stock prices need a free
`TIINGO_API_KEY` in `.env`. The daily systemd job runs `ttg call --refresh --notify`.

## Commands

```bash
# Data
uv run ttg ingest bgd|bnm|worldbank|fred|tiingo|moomoo|edgar
uv run ttg import lbma <file>    # LBMA portal download (manual; non-commercial self-certification)
uv run ttg stage <source>        # rebuild staging from raw/ without fetching
uv run ttg build gold            # curated/gold_myr_daily (needs LBMA)

# Evidence
uv run ttg reconcile             # tracking error vs Kijang Emas, BGD, World Bank -> reports/
uv run ttg backtest gold         # SMA10, TSMOM12, regime vs buy-and-hold and DCA -> reports/
uv run ttg backtest gold --provisional   # World Bank monthly averages; smoke test only
uv run ttg screen us             # ETF trend states + quality/value/12-1 momentum picks
uv run ttg export                # Excel workbook -> reports/

# Alerts
uv run ttg alerts run [--dry-run]   # enabled signals only; fires on state changes
uv run ttg alerts score             # 5/20/60-day forward scores
uv run ttg alerts report            # alert log vs benchmark

uv run ttg call [--refresh] [--notify] [--markdown]   # buy/hold/sell for gold + your stocks
uv run ttg watch add|remove|list SYMBOL...             # your stock list

uv run ttg status
uv run pytest
```

On the homelab, `deploy/systemd/` has the timers: BGD hourly, daily (BNM, FRED, alerts,
scoring), and monthly (World Bank, reconciliation, backtest, Excel).

## What needs you

- **LBMA history**: download the Gold PM table from the LBMA portal and run `ttg import lbma`.
  Until then the gold backtest runs only in `--provisional` mode, and no decision is made.
- **Keys in `.env`**: `FRED_API_KEY` (regime filter), `EDGAR_USER_AGENT` (your name and email),
  `TIINGO_API_KEY`, Telegram. Moomoo needs OpenD running and `uv sync --extra broker`.
- **Replication targets**: fill `config/replication.yaml` from the papers and put the reference
  data in `data/reference/`.
- **US choices**: the screen universe (`universe.yaml` symbols) and the ONE short-term setup.
- **Survivorship**: read `doc/survivorship.md` before trusting any US equity backtest.

## Layout

```
config/          settings.yaml, universe.yaml, alerts.yaml (no secrets)
data/            raw/ (immutable) · staging/ · curated/ · warehouse.duckdb · ops.sqlite
reports/         generated reconciliation, replication and backtest reports
src/trade_to_go/
  core/          config, log, calendars, storage, http, telegram
  schemas/       pandera contracts per dataset
  sources/       extract only: bgd, bnm, lbma, worldbank, fred, edgar, tiingo, moomoo
  pipelines/     raw -> staging -> curated
  reconcile/  features/  signals/  alerts/  backtest/  broker/
  calls/         today's buy/hold/sell: indicators, gold, stocks, service, render
research/        notebooks (read-only on data/)
tests/           unit/ · golden/ · replication/ · parity/
doc/todos.txt    roadmap
codelog/         one change log per work session
legacy/          original scripts, kept until the new package is verified
```
