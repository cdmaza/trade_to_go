"""Macro features for the gold regime filter: US 10y real yield (DFII10) and the broad dollar (DTWEXBGS).

DTWEXBGS is published weekly with a lag, so month-end values are taken as of
`lag_days` before the month-end to avoid using numbers that were not yet public.
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.features.trend import sma


def monthly_asof(daily: pd.Series, month_ends: pd.DatetimeIndex, lag_days: int = 0) -> pd.Series:
    daily = daily.dropna().sort_index()
    at = month_ends - pd.Timedelta(days=lag_days)
    return pd.Series(daily.reindex(at, method="ffill").to_numpy(), index=month_ends)


def real_yield_falling(real_yield_m: pd.Series, lookback: int = 12) -> pd.Series:
    """True when the real yield is below its level `lookback` months ago."""
    out = real_yield_m < real_yield_m.shift(lookback)
    return out.where(real_yield_m.shift(lookback).notna())


def dollar_weak(dollar_m: pd.Series, n: int = 10) -> pd.Series:
    """True when the dollar index is below its n-month SMA."""
    avg = sma(dollar_m, n)
    return (dollar_m < avg).where(avg.notna())
