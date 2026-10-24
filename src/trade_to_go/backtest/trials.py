"""Registry of every backtest configuration run. The deflated Sharpe ratio needs the
number of trials and the spread of their Sharpe ratios, so nothing is run off the books.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from trade_to_go.core.storage import warehouse

SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_trials (
    trial_id      VARCHAR PRIMARY KEY,
    created_at    TIMESTAMPTZ,
    family        VARCHAR,      -- trials compared against each other, e.g. 'gold_myr_monthly'
    rule          VARCHAR,
    params        VARCHAR,      -- JSON
    data_hash     VARCHAR,
    start_date    DATE,
    end_date      DATE,
    n_periods     INTEGER,
    sr_period     DOUBLE,
    sharpe        DOUBLE,
    cagr          DOUBLE,
    max_dd        DOUBLE
)
"""


def data_hash(series: pd.Series) -> str:
    payload = pd.util.hash_pandas_object(series.dropna(), index=True).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:16]


def record(family: str, rule: str, params: dict, dhash: str, returns: pd.Series, metrics: dict) -> str:
    """Insert (or refresh) one trial; identical rule+params+data map to the same id."""
    key = json.dumps({"f": family, "r": rule, "p": params, "d": dhash}, sort_keys=True)
    trial_id = hashlib.sha256(key.encode()).hexdigest()[:16]
    r = returns.dropna()
    con = warehouse()
    con.execute(SCHEMA)
    con.execute("DELETE FROM backtest_trials WHERE trial_id = ?", [trial_id])
    con.execute(
        "INSERT INTO backtest_trials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [trial_id, datetime.now(timezone.utc), family, rule, json.dumps(params, sort_keys=True), dhash,
         r.index[0].date() if len(r) else None, r.index[-1].date() if len(r) else None, len(r),
         metrics.get("sr_period"), metrics.get("sharpe"), metrics.get("cagr"), metrics.get("max_dd")],
    )
    con.close()
    return trial_id


def family_srs(family: str) -> list[float]:
    con = warehouse()
    con.execute(SCHEMA)
    rows = con.execute("SELECT sr_period FROM backtest_trials WHERE family = ?", [family]).fetchall()
    con.close()
    return [r[0] for r in rows if r[0] is not None]
