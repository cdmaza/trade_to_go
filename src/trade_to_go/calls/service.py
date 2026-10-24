"""Assemble today's report (gold + stocks), remember the last call per symbol and find changes."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone

import pandas as pd

from trade_to_go.calls import gold as gold_calls
from trade_to_go.calls import stocks as stock_calls
from trade_to_go.calls import watchlist
from trade_to_go.calls.models import Call
from trade_to_go.calls.replay import replay
from trade_to_go.core.config import get_settings, load_yaml
from trade_to_go.core.storage import ops, read_table, table_path

log = logging.getLogger(__name__)


@dataclass
class Report:
    generated_at: str
    today: str
    gold: Call | None = None
    gold_error: str | None = None
    watchlist: list[Call] = field(default_factory=list)
    potential: list[Call] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    pool_size: int = 0
    pool_buys: int = 0
    evidence: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def all_calls(self) -> list[Call]:
        return ([self.gold] if self.gold else []) + self.watchlist + self.potential


def _cfg() -> dict:
    return load_yaml("settings.yaml").get("calls", {})


def candidates() -> list[str]:
    return [str(s).upper() for s in load_yaml("universe.yaml").get("candidates", []) or []]


def tracked_symbols() -> list[str]:
    """Everything whose prices `ttg call --refresh` fetches."""
    return list(dict.fromkeys([*watchlist.load(), *candidates()]))


def _screen_picks() -> set[str]:
    files = sorted(get_settings().reports_dir.glob("us_long_term_*.json"))
    return set(json.loads(files[-1].read_text()).get("screen_picks", [])) if files else set()


def _prices() -> pd.DataFrame:
    if not table_path("staging", "equity_prices_daily").exists():
        return pd.DataFrame(columns=["date", "symbol", "adj_close"])
    return read_table("staging", "equity_prices_daily")


def build_report(today: date | None = None) -> Report:
    today = today or date.today()
    cfg = _cfg()
    report = Report(generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), today=today.isoformat())
    report.evidence = gold_calls.evidence()

    try:
        daily, source, unit = gold_calls.load_gold_series()
        spread = gold_calls.kijang_spread()
        report.gold = gold_calls.gold_call(daily, source, unit, spread, report.evidence, today, cfg,
                                           history=replay(daily, spread))
    except (FileNotFoundError, KeyError, IndexError, ValueError) as exc:
        report.gold_error = ("No gold prices yet. Run `ttg call --refresh` (BNM Kijang Emas needs no key). "
                             f"({type(exc).__name__}: {exc})")

    section = stock_calls.build_stock_section(_prices(), watchlist.load(), candidates(), _screen_picks(), today, cfg)
    report.watchlist, report.potential = section["watchlist"], section["potential"]
    report.pool_size, report.pool_buys = section["pool_size"], section["pool_buys"]
    have = {c.symbol for c in report.watchlist}
    report.missing = [s for s in watchlist.load() if s not in have]
    if section["missing"] and not os.environ.get("TIINGO_API_KEY") and not report.watchlist and not report.potential:
        report.notes.append("No stock prices yet: add TIINGO_API_KEY to .env (free), then run `ttg call --refresh`.")
    if not watchlist.load():
        report.notes.append("Your watchlist is empty: add stocks with `ttg watch add AAPL MSFT`.")
    return report


def refresh() -> list[str]:
    """Fetch fresh prices (gold from BNM, stocks from Tiingo when a key is set). Never raises."""
    from trade_to_go.pipelines import equities, gold

    notes = []
    try:
        gold.ingest_bnm()
        gold.build_bnm_staging()
    except Exception as exc:  # network or API trouble should not hide the stale-data report
        notes.append(f"Gold refresh failed: {exc!r}")
    symbols = tracked_symbols()
    get_settings()  # loads .env
    if os.environ.get("TIINGO_API_KEY") and symbols:
        failed = []
        for sym in symbols:
            try:
                equities.ingest_prices("tiingo", [sym])
            except Exception as exc:
                failed.append(f"{sym} ({type(exc).__name__})")
        try:
            equities.build_prices_staging()
        except Exception as exc:
            notes.append(f"Stock staging failed: {exc!r}")
        if failed:
            notes.append("No fresh prices for: " + ", ".join(failed))
    else:
        notes.append("Stock prices not refreshed: TIINGO_API_KEY is not set in .env.")
    return notes


def record_changes(report: Report, con: sqlite3.Connection | None = None) -> list[tuple[Call, str | None]]:
    """Store each shown call's label; return (call, previous label) where it changed.

    The first run only records a baseline (nothing is reported as a change), like the alert state
    machine. After that a stock newly appearing in the potential list counts as a change.
    """
    own = con is None
    con = con or ops()
    try:
        baseline = con.execute("SELECT count(*) FROM call_state").fetchone()[0] == 0
        changes = []
        for call in report.all_calls():
            row = con.execute("SELECT label FROM call_state WHERE symbol = ?", (call.symbol,)).fetchone()
            prev = row["label"] if row else None
            if prev == call.label:
                continue
            with con:
                con.execute(
                    "INSERT INTO call_state (symbol, label, as_of, changed_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (symbol) DO UPDATE SET label = excluded.label, as_of = excluded.as_of, "
                    "changed_at = excluded.changed_at",
                    (call.symbol, call.label, call.as_of, datetime.now(timezone.utc).isoformat(timespec="seconds")))
            if not baseline:
                changes.append((call, prev))
        return changes
    finally:
        if own:
            con.close()


def save(report: Report) -> dict[str, str]:
    """Write reports/call_<date>.json (history) and call_latest.json."""
    folder = get_settings().reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(report), indent=2, default=str)
    dated = folder / f"call_{report.today}.json"
    latest = folder / "call_latest.json"
    dated.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return {"json": str(dated)}
