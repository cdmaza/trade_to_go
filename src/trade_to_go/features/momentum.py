"""Momentum features (Moskowitz, Ooi and Pedersen 2012; Jegadeesh-Titman 12-1)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def trailing_return(monthly: pd.Series, lookback: int = 12) -> pd.Series:
    """Return over the last `lookback` months, known at each month-end."""
    return monthly / monthly.shift(lookback) - 1


def mom_12_1(monthly: pd.Series) -> pd.Series:
    """12-month return skipping the most recent month."""
    return monthly.shift(1) / monthly.shift(12) - 1


def ex_ante_vol(daily_prices: pd.Series, com: int = 60) -> pd.Series:
    """MOP (2012) ex-ante volatility: EWMA of squared daily returns, centre of mass 60 days,
    annualised with 261 trading days.
    """
    r = np.log(daily_prices).diff()
    var = (r - r.ewm(com=com).mean()) ** 2
    return np.sqrt(261 * var.ewm(com=com).mean())
