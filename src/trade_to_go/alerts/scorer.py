"""Forward-score every logged alert at 5, 20 and 60 trading days.

Strategy return over the horizon: the asset's return if the new state is long, 0 if flat
(cash), the negative return if short. Benchmark return: holding the benchmark over the
same days (for gold, DCA/buy-and-hold means holding gold).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pandas as pd

from trade_to_go.core.config import load_yaml
from trade_to_go.core.storage import ops

HORIZONS = (5, 20, 60)
SIDE = {"long": 1.0, "flat": 0.0, "short": -1.0}


def score_pending(prices: Callable[[str], pd.Series], benchmark_of: Callable[[str], str],
                  con: sqlite3.Connection | None = None) -> int:
    """Fill ret_h / bench_h for alerts whose horizon has passed. Returns the number of cells filled."""
    own = con is None
    con = con or ops()
    filled = 0
    try:
        alerts = con.execute("SELECT * FROM alert_log WHERE ret_60d IS NULL OR ret_20d IS NULL OR ret_5d IS NULL")
        for a in alerts.fetchall():
            px = prices(a["instrument"])
            bench = prices(benchmark_of(a["instrument"]))
            start = pd.Timestamp(a["created_at"]).tz_localize(None).normalize()
            for h in HORIZONS:
                if a[f"ret_{h}d"] is not None:
                    continue
                r = _forward_return(px, start, h)
                b = _forward_return(bench, start, h)
                if r is None or b is None:
                    continue
                with con:
                    con.execute(f"UPDATE alert_log SET ret_{h}d = ?, bench_{h}d = ? WHERE id = ?",
                                (SIDE.get(a["state"], 0.0) * r, b, a["id"]))
                filled += 1
        return filled
    finally:
        if own:
            con.close()


def _forward_return(px: pd.Series, start: pd.Timestamp, h: int) -> float | None:
    px = px.dropna().sort_index()
    i = px.index.searchsorted(start)  # first price on/after the alert day
    if i + h >= len(px):
        return None
    return float(px.iloc[i + h] / px.iloc[i] - 1)


def summary(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Per horizon: scored alerts, hit rate (strategy > benchmark) and mean excess return."""
    own = con is None
    con = con or ops()
    try:
        df = pd.read_sql_query("SELECT * FROM alert_log", con)
    finally:
        if own:
            con.close()
    rows = []
    for h in HORIZONS:
        d = df.dropna(subset=[f"ret_{h}d", f"bench_{h}d"])
        excess = d[f"ret_{h}d"] - d[f"bench_{h}d"]
        rows.append({"horizon_days": h, "scored": len(d),
                     "beat_benchmark": float((excess > 0).mean()) if len(d) else None,
                     "mean_excess": float(excess.mean()) if len(d) else None})
    return pd.DataFrame(rows)


def benchmark_from_config(instrument: str) -> str:
    """Benchmark instrument for scoring, from config/alerts.yaml (defaults to the instrument itself)."""
    return load_yaml("alerts.yaml").get("benchmark_instruments", {}).get(instrument, instrument)
