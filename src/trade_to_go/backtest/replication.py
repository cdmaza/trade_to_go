"""Compute the statistics named in config/replication.yaml from reference data, using the
same rule, simulator and metric code as the live studies.
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.backtest.engine import simulate
from trade_to_go.backtest.metrics import cagr, max_drawdown, sharpe
from trade_to_go.features.trend import month_end
from trade_to_go.signals import gold_rules


def compute(spec: dict, data: pd.DataFrame) -> dict[str, float]:
    data = data.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.set_index("date").sort_index()
    rule = spec["rule"]

    if rule == "returns_only":
        r = data["return"].dropna()
        return {"sharpe": sharpe(r)}

    if rule == "gold_cpi_ratio":
        d = data.loc[slice(*spec.get("window", [None, None]))]
        return {"mean_ratio": float((d["gold_usd"] / d["cpi"]).mean())}

    monthly = month_end(data["price"])
    target = getattr(gold_rules, rule)(monthly, **spec.get("params", {}))
    start, end = spec.get("window", [None, None])
    first = max(target.first_valid_index(), pd.Timestamp(start)) if start else target.first_valid_index()
    prices = monthly.loc[first:end]
    cost = spec.get("one_way_cost", 0.0)
    timing = simulate(prices, target.loc[prices.index], one_way_cost=cost, initial=1.0).twr
    hold = simulate(prices, pd.Series(1.0, prices.index), one_way_cost=cost, initial=1.0).twr
    return {
        "timing_cagr": cagr(timing), "timing_max_dd": max_drawdown(timing),
        "buy_hold_cagr": cagr(hold), "buy_hold_max_dd": max_drawdown(hold),
    }
