"""Monthly long/flat simulator with contributions and one-way trading costs.

At each month-end t the rule sees the month-end price and sets a target (0 or 1).
Trades execute at `exec_prices[t]` (the next available price after the month-end
when daily data exist). Contributions arrive just before each trade. The final
value is liquidated (exit cost paid) so DCA and timing rules are compared net.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SimResult:
    value: pd.Series          # portfolio value after trades at each step
    twr: pd.Series            # time-weighted return per step (flows removed, costs included)
    position: pd.Series       # position held after each step's trade
    flows: pd.Series          # contributions
    trades: int
    costs_paid: float
    terminal_net: float       # value after paying the exit cost on any gold held


def simulate(exec_prices: pd.Series, target: pd.Series, *, one_way_cost: float,
             contribution: float = 0.0, initial: float = 0.0, cash_rate_annual: float = 0.0) -> SimResult:
    target = target.reindex(exec_prices.index)
    cash_growth = (1 + cash_rate_annual) ** (1 / 12)
    units, cash, costs, trades = 0.0, 0.0, 0.0, 0
    values, twr, pos, flows = [], [], [], []
    prev_value = None

    for i, (date, price) in enumerate(exec_prices.items()):
        cash *= cash_growth if i else 1.0
        flow = (initial if i == 0 else 0.0) + contribution
        cash += flow
        want = target.loc[date]
        holding = 1.0 if units > 0 else 0.0
        if not np.isnan(want) and want != holding:
            trades += 1
            if want == 1.0:
                fee = cash * one_way_cost
                units += (cash - fee) / price
                cash = 0.0
            else:
                gross = units * price
                fee = gross * one_way_cost
                cash += gross - fee
                units = 0.0
            costs += fee
        elif holding and cash > 0:
            # New contributions go straight into gold while the rule is long.
            fee = cash * one_way_cost
            units += (cash - fee) / price
            costs += fee
            cash = 0.0
        value = units * price + cash
        twr.append(np.nan if not prev_value else (value - flow) / prev_value - 1)
        values.append(value)
        pos.append(1.0 if units > 0 else 0.0)
        flows.append(flow)
        prev_value = value

    idx = exec_prices.index
    terminal = cash + units * exec_prices.iloc[-1] * (1 - one_way_cost)
    return SimResult(pd.Series(values, idx), pd.Series(twr, idx).dropna(), pd.Series(pos, idx),
                     pd.Series(flows, idx), trades, costs, terminal)


def money_weighted_return(flows: pd.Series, terminal: float) -> float:
    """Annualised IRR of monthly contributions against the terminal (net) value."""
    cf = -flows.to_numpy(dtype=float)
    cf[-1] += terminal  # the terminal value is valued at the same date as the last contribution

    def npv(rate: float) -> float:
        return float(np.sum(cf / (1 + rate) ** np.arange(len(cf))))

    lo, hi = -0.5, 1.0  # monthly rate bounds
    if npv(lo) * npv(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (1 + (lo + hi) / 2) ** 12 - 1
