"""Equities pipeline: prices (Tiingo or Moomoo) and EDGAR fundamentals -> staging,
plus the US long-term report (ETF trend filter + factor screen).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings, load_yaml
from trade_to_go.core.storage import raw_files, read_table, table_path, write_raw, write_table
from trade_to_go.features.factors import factor_table
from trade_to_go.features.trend import month_end
from trade_to_go.schemas.equities import EQUITY_PRICES_DAILY, FUNDAMENTALS_FACTS
from trade_to_go.signals import factor_screen, gold_rules
from trade_to_go.sources.base import RawPayload
from trade_to_go.sources.edgar import EdgarSource, point_in_time
from trade_to_go.sources.moomoo import MoomooSource
from trade_to_go.sources.tiingo import TiingoSource


def _land(source: str, payloads: list[RawPayload]) -> list[Path]:
    return [write_raw(source, p.name, p.payload, url=p.url, fetched_at=p.fetched_at) for p in payloads]


def universe_symbols() -> list[str]:
    from trade_to_go.calls import watchlist

    universe = load_yaml("universe.yaml")
    u = universe["us_long_term"]
    candidates = {str(s).upper() for s in universe.get("candidates", []) or []}
    return sorted(set(u.get("trend_etfs", [])) | set(u.get("screen", {}).get("symbols", []) or [])
                  | candidates | set(watchlist.load()))


def ingest_prices(provider: str = "tiingo", symbols: list[str] | None = None) -> list[Path]:
    symbols = symbols or universe_symbols()
    if provider == "tiingo":
        src = TiingoSource.from_settings()
        return _land(src.name, [src.fetch(s) for s in symbols])
    src = MoomooSource()
    return _land(src.name, [src.fetch_daily(s, start="2000-01-01") for s in symbols])


def build_prices_staging() -> Path:
    frames = [TiingoSource.parse(raw_files("tiingo", "*.json")), MoomooSource.parse(raw_files("moomoo", "*.json"))]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) \
        else frames[0]
    # Prefer Tiingo when both sources have the same day.
    df = df.sort_values("source", key=lambda s: s.map({"tiingo": 0, "moomoo": 1}))
    df = df.drop_duplicates(["date", "symbol"]).sort_values(["symbol", "date"])
    return write_table(df, "staging", "equity_prices_daily", EQUITY_PRICES_DAILY)


def ingest_edgar(symbols: list[str] | None = None) -> list[Path]:
    src = EdgarSource.from_settings()
    paths = _land(src.name, [src.fetch_tickers()])
    tickers = EdgarSource.parse_tickers(paths[0])
    wanted = set(symbols or load_yaml("universe.yaml")["us_long_term"].get("screen", {}).get("symbols", []) or [])
    for cik in tickers[tickers["ticker"].isin(wanted)]["cik"]:
        paths += _land(src.name, [src.fetch_company_facts(int(cik))])
    return paths


def build_edgar_staging() -> list[Path]:
    paths = raw_files("edgar", "*.json")
    latest_tickers = sorted(p for p in paths if p.name.startswith("company_tickers__"))
    out = []
    if latest_tickers:
        tickers = EdgarSource.parse_tickers(latest_tickers[-1])
        out.append(write_table(tickers, "staging", "edgar_tickers"))
    latest: dict[str, Path] = {}
    for p in sorted((p for p in paths if p.name.startswith("companyfacts_")), key=lambda p: p.stem.split("__")[1]):
        latest[p.stem.split("__")[0]] = p
    facts = EdgarSource.parse_company_facts(list(latest.values()))
    out.append(write_table(facts, "staging", "fundamentals_facts", FUNDAMENTALS_FACTS))
    return out


def us_report(as_of: date | None = None) -> str:
    """ETF monthly trend states + factor screen picks, written to reports/."""
    as_of_ts = pd.Timestamp(as_of or date.today())
    prices = read_table("staging", "equity_prices_daily")
    prices = prices[prices["date"] <= as_of_ts]
    universe = load_yaml("universe.yaml")["us_long_term"]

    trend = {}
    for etf in universe.get("trend_etfs", []):
        s = prices[prices["symbol"] == etf].set_index("date")["adj_close"]
        if s.empty:
            continue
        monthly = month_end(s)
        monthly = monthly[monthly.index.to_period("M") < as_of_ts.to_period("M")]
        state = gold_rules.sma_filter(monthly, 10)
        if len(state.dropna()):
            trend[etf] = {"state": "long" if state.iloc[-1] == 1 else "flat", "price": float(s.iloc[-1]),
                          "sma10": gold_rules.sma_invalidation(monthly, 10)}

    picks = []
    if table_path("staging", "fundamentals_facts").exists() and table_path("staging", "edgar_tickers").exists():
        facts = read_table("staging", "fundamentals_facts")
        tickers = read_table("staging", "edgar_tickers").drop_duplicates("cik").set_index("cik")["ticker"]
        pit = point_in_time(facts, as_of_ts)
        pit.index = pit.index.map(tickers)
        table = factor_table(pit, prices, as_of_ts)
        picks = factor_screen.select(table, universe.get("screen", {}).get("top_fraction", 0.2))

    folder = get_settings().reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"us_long_term_{as_of_ts.date().isoformat()}.json"
    path.write_text(json.dumps({"as_of": as_of_ts.date().isoformat(), "etf_trend": trend, "screen_picks": picks,
                                "survivorship": "see doc/survivorship.md"}, indent=2))
    return str(path)
