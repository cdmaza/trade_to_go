"""Price-only indicators for the buy/hold/sell calls.

The trend states reuse the backtested rule functions (signals/gold_rules.py), so a call and a
backtest can never disagree about what "above the 10-month average" means. Two readings are given:

official  month-end rule on COMPLETED months (what the backtest tested, what alerts fire on)
live      same rule with today's price standing in for this month's close (an early warning that
          the official state would flip if the month ended today)
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from trade_to_go.signals import gold_rules
from trade_to_go.signals.live import completed_month_ends

MIN_MONTHS = 13  # 12-month momentum needs 13 month-ends


def _state(series: pd.Series) -> str | None:
    last = series.iloc[-1] if len(series) else float("nan")
    return None if pd.isna(last) else ("long" if last == 1 else "flat")


def _live_monthly(official: pd.Series, daily: pd.Series) -> pd.Series:
    """Completed month-ends plus today's price as this month's provisional close."""
    last_day = daily.index[-1]
    if len(official) and last_day.to_period("M") <= official.index[-1].to_period("M"):
        return official
    return pd.concat([official, daily.iloc[[-1]]])


def trend_view(daily: pd.Series, today: date | None = None, n: int = 10, lookback: int = 12) -> dict:
    """SMA-n and TSMOM-lookback states (official and live) with the price levels that flip them."""
    daily = daily.dropna().sort_index()
    official = completed_month_ends(daily, today)
    live = _live_monthly(official, daily)
    out: dict = {"months": int(len(official)), "price": float(daily.iloc[-1]), "as_of": daily.index[-1].date()}
    out["sma_official"] = _state(gold_rules.sma_filter(official, n))
    out["sma_live"] = _state(gold_rules.sma_filter(live, n))
    out["tsmom_official"] = _state(gold_rules.tsmom(official, lookback))
    out["tsmom_live"] = _state(gold_rules.tsmom(live, lookback))

    out["sma_level"] = None
    out["tsmom_level"] = None
    if len(official) >= n - 1 and len(live) >= n:
        # Price p at which p == mean(previous n-1 month-ends, p): the average of those n-1 closes.
        # If today is already in the current month the live SMA includes p, so the flip level is
        # that average; otherwise (no data yet this month) it is the plain n-month SMA.
        out["sma_level"] = (float(official.iloc[-(n - 1):].mean()) if len(live) > len(official)
                            else float(gold_rules.sma_invalidation(official, n)))
    if len(live) > lookback:
        out["tsmom_level"] = float(live.iloc[-1 - lookback])
    return out


def return_over(daily: pd.Series, months: int) -> float | None:
    """Total return from `months` calendar months before the last date to the last date."""
    daily = daily.dropna().sort_index()
    start = daily.index[-1] - pd.DateOffset(months=months)
    if daily.index[0] > start:
        return None
    return float(daily.iloc[-1] / daily.asof(start) - 1)


def momentum_12_1(daily: pd.Series) -> float | None:
    """12-month return skipping the latest month (Jegadeesh-Titman)."""
    daily = daily.dropna().sort_index()
    end = daily.index[-1] - pd.DateOffset(months=1)
    start = daily.index[-1] - pd.DateOffset(months=12)
    if daily.index[0] > start:
        return None
    return float(daily.asof(end) / daily.asof(start) - 1)


def rsi(daily: pd.Series, n: int = 14) -> float | None:
    """Wilder RSI of the last close."""
    delta = daily.dropna().diff().dropna()
    if len(delta) < n + 1:
        return None
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return 100.0 if down == 0 else float(100 - 100 / (1 + up / down))


def drawdown_from_high(daily: pd.Series, days: int = 365) -> float | None:
    """How far the last price sits below the highest price of the last `days` calendar days (<= 0)."""
    daily = daily.dropna().sort_index()
    window = daily[daily.index > daily.index[-1] - pd.Timedelta(days=days)]
    if len(window) < 20:
        return None
    return float(daily.iloc[-1] / window.max() - 1)


def annual_vol(daily: pd.Series, window: int = 60) -> float | None:
    r = np.log(daily.dropna().sort_index()).diff().dropna().tail(window)
    return float(r.std() * np.sqrt(252)) if len(r) >= 20 else None


def pct_rank(values: dict[str, float | None]) -> dict[str, float]:
    """Percentile rank (0 worst .. 1 best) of the non-missing values; missing ones rank 0."""
    s = pd.Series({k: v for k, v in values.items() if v is not None}, dtype=float)
    ranks = s.rank(pct=True) if len(s) else s
    return {k: float(ranks.get(k, 0.0)) for k in values}

