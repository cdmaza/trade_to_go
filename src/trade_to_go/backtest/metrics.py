"""Performance metrics on periodic (monthly by default) time-weighted returns."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cagr(returns: pd.Series, periods_per_year: int = 12) -> float:
    returns = returns.dropna()
    if returns.empty:
        return float("nan")
    return float((1 + returns).prod() ** (periods_per_year / len(returns)) - 1)


def max_drawdown(returns: pd.Series) -> float:
    wealth = (1 + returns.dropna()).cumprod()
    return float((wealth / wealth.cummax() - 1).min())


def sharpe(returns: pd.Series, rf_annual: float = 0.0, periods_per_year: int = 12) -> float:
    """Annualised Sharpe ratio."""
    return sharpe_per_period(returns, rf_annual, periods_per_year) * np.sqrt(periods_per_year)


def sharpe_per_period(returns: pd.Series, rf_annual: float = 0.0, periods_per_year: int = 12) -> float:
    excess = returns.dropna() - ((1 + rf_annual) ** (1 / periods_per_year) - 1)
    sd = excess.std(ddof=1)
    return float(excess.mean() / sd) if sd > 0 else float("nan")


def state_change_hit_rates(daily: pd.Series, changes: pd.Series, horizons=(5, 20, 60)) -> dict[int, float]:
    """For each state change (index = first trading day the new state applies, value = new state),
    a hit is: price higher `h` trading days later for a move into gold, lower for a move to cash.
    """
    daily = daily.dropna().sort_index()
    out = {}
    for h in horizons:
        hits = []
        for date, state in changes.items():
            i = daily.index.searchsorted(date)
            if i + h < len(daily):
                fwd = daily.iloc[i + h] / daily.iloc[i] - 1
                hits.append(fwd > 0 if state == 1 else fwd < 0)
        out[h] = float(np.mean(hits)) if hits else float("nan")
    return out
