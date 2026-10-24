"""Replay the gold trend rules on the price history behind a call (in-sample sanity check).

Not the pre-registered decision (that is `ttg backtest gold` on LBMA daily data). A few years and a
handful of trades cannot prove a rule works; they show whether it is obviously worse than simply
holding once the real trading cost is paid. Costs: half the buy/sell spread each way on the mid price.
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.backtest.engine import money_weighted_return, simulate
from trade_to_go.backtest.metrics import cagr, max_drawdown, sharpe
from trade_to_go.features.trend import month_end
from trade_to_go.signals import gold_rules

MIN_MONTHS = 30


def replay(daily: pd.Series, spread: float | None) -> dict | None:
    """Per-rule lump-sum stats and DCA IRR; None when there is too little history."""
    daily = daily.dropna().sort_index()
    one_way = (spread if spread is not None else 0.0) / 2
    monthly = month_end(daily)
    monthly = monthly[monthly.index.to_period("M") < daily.index[-1].to_period("M")]   # completed months only
    exec_prices = daily.shift(-1).reindex(monthly.index).dropna()                      # trade on the next price
    monthly = monthly.loc[exec_prices.index]

    sma, mom = gold_rules.sma_filter(monthly, 10), gold_rules.tsmom(monthly, 12)
    both = ((sma == 1) & (mom == 1)).astype(float).where(sma.notna() & mom.notna())
    rules = {"buy_hold": pd.Series(1.0, monthly.index), "sma10": sma, "tsmom12": mom, "sma10_and_tsmom12": both}
    first = max(t.first_valid_index() for t in rules.values())
    if first is None:
        return None
    px = exec_prices.loc[first:]
    if len(px) < MIN_MONTHS:
        return None

    rows = {}
    for name, target in rules.items():
        target = target.loc[first:]
        lump = simulate(px, target, one_way_cost=one_way, initial=1.0)
        dca = simulate(px, target, one_way_cost=one_way, contribution=1.0)
        rows[name] = {"cagr": cagr(lump.twr), "max_dd": max_drawdown(lump.twr), "sharpe": sharpe(lump.twr),
                      "trades": lump.trades, "time_in_gold": float(target.mean()),
                      "dca_irr": money_weighted_return(dca.flows, dca.terminal_net)}
    return {"start": px.index[0].date().isoformat(), "end": px.index[-1].date().isoformat(), "months": len(px),
            "one_way_cost": one_way, "rules": rows}
