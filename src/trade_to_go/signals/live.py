"""Live signals: the same rule functions as the backtest, evaluated on the last COMPLETED
month (rules are month-end rules; a half-finished month is not a month-end).
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from trade_to_go.core.config import get_settings
from trade_to_go.features.macro import monthly_asof
from trade_to_go.features.trend import month_end
from trade_to_go.pipelines.prices import price_series
from trade_to_go.signals import gold_rules
from trade_to_go.signals.base import Signal


def completed_month_ends(daily: pd.Series, today: date | None = None) -> pd.Series:
    today = pd.Timestamp(today or date.today())
    monthly = month_end(daily)
    return monthly[monthly.index.to_period("M") < today.to_period("M")]


def evaluate(name: str, spec: dict, today: date | None = None, macro: dict[str, pd.Series] | None = None) -> Signal:
    daily = price_series(spec["instrument"])
    monthly = completed_month_ends(daily, today)
    params = spec.get("params", {})
    rule = spec["rule"]

    if rule in ("regime", "sma_with_regime"):
        macro = macro or _macro(monthly.index)
        ry, usd = macro["real_yield_10y"], macro["broad_dollar"]
        target = (gold_rules.regime(ry, usd) if rule == "regime"
                  else gold_rules.sma_with_regime(monthly, ry, usd, **params))
    else:
        target = getattr(gold_rules, rule)(monthly, **params)

    if pd.isna(target.iloc[-1]):
        raise ValueError(f"{name}: not enough history for a signal")
    invalidation = None
    if rule in ("sma_filter", "sma_with_regime"):
        invalidation = gold_rules.sma_invalidation(monthly, params.get("n", 10))
    elif rule == "tsmom":
        invalidation = gold_rules.tsmom_invalidation(monthly, params.get("lookback", 12))

    hit_rate, backtest_id = _backtest_stats(spec.get("backtest_rule", name))
    return Signal(
        name=name, instrument=spec["instrument"], as_of=monthly.index[-1].date(),
        state="long" if target.iloc[-1] == 1 else "flat", price=float(daily.iloc[-1]),
        invalidation=invalidation, hit_rate=hit_rate, backtest_id=backtest_id,
    )


def _macro(month_ends: pd.DatetimeIndex) -> dict[str, pd.Series]:
    from trade_to_go.core.storage import read_table

    md = read_table("staging", "macro_daily")
    return {alias: monthly_asof(md[md["series"] == alias].set_index("date")["value"], month_ends, lag)
            for alias, lag in (("real_yield_10y", 0), ("broad_dollar", 7))}


def _backtest_stats(rule: str) -> tuple[dict[int, float] | None, str | None]:
    """Hit rates from the latest non-provisional gold backtest report."""
    reports = sorted(get_settings().reports_dir.glob("gold_backtest_2*.json"))
    if not reports:
        return None, None
    data = json.loads(reports[-1].read_text())
    hits = data["rules"].get(rule, {}).get("hit_rate")
    return ({int(k): v for k, v in hits.items()} if hits else None), reports[-1].stem
