"""Trend features on month-end prices (Faber 2007 uses month-end closes)."""

from __future__ import annotations

import pandas as pd


def month_end(prices: pd.Series) -> pd.Series:
    """Last available price in each calendar month, indexed by that price's date."""
    prices = prices.dropna().sort_index()
    return prices.groupby(prices.index.to_period("M")).tail(1)


def sma(monthly: pd.Series, n: int = 10) -> pd.Series:
    return monthly.rolling(n, min_periods=n).mean()
