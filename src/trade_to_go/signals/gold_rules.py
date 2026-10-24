"""Gold timing rules. Each returns the target position (1 = hold gold, 0 = cash) decided
at each month-end from data known at that month-end. NaN = not enough history yet.

BGD cannot be shorted or leveraged, so the MOP (2012) long/short, volatility-scaled
TSMOM becomes long/flat here. The signal (sign of the 12-month excess return) is
unchanged; position sizing is not.
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.features.macro import dollar_weak, real_yield_falling
from trade_to_go.features.momentum import trailing_return
from trade_to_go.features.trend import sma


def _flag(cond: pd.Series, valid: pd.Series) -> pd.Series:
    return cond.astype(float).where(valid)


def sma_filter(monthly: pd.Series, n: int = 10) -> pd.Series:
    """Faber (2007): hold when the month-end price is above its n-month SMA."""
    avg = sma(monthly, n)
    return _flag(monthly > avg, avg.notna())


def tsmom(monthly: pd.Series, lookback: int = 12, cash_return_annual: float = 0.0) -> pd.Series:
    """MOP (2012), long/flat: hold when the trailing return beats cash over the same window."""
    ret = trailing_return(monthly, lookback)
    hurdle = (1 + cash_return_annual) ** (lookback / 12) - 1
    return _flag(ret > hurdle, ret.notna())


def regime(real_yield_m: pd.Series, dollar_m: pd.Series) -> pd.Series:
    """Hold when real yields are falling (12m) or the dollar is below its 10-month SMA."""
    ry = real_yield_falling(real_yield_m)
    usd = dollar_weak(dollar_m)
    valid = ry.notna() & usd.notna()
    return _flag(ry.fillna(False).astype(bool) | usd.fillna(False).astype(bool), valid)


def sma_with_regime(monthly: pd.Series, real_yield_m: pd.Series, dollar_m: pd.Series, n: int = 10) -> pd.Series:
    """SMA filter, but only exit to cash when the macro regime is also unfavourable."""
    trend = sma_filter(monthly, n)
    reg = regime(real_yield_m, dollar_m)
    valid = trend.notna() & reg.notna()
    return _flag((trend == 1) | (reg == 1), valid)


def sma_invalidation(monthly: pd.Series, n: int = 10) -> float:
    """Price level at which the SMA state flips: the current n-month SMA."""
    return float(sma(monthly, n).iloc[-1])


def tsmom_invalidation(monthly: pd.Series, lookback: int = 12, cash_return_annual: float = 0.0) -> float:
    """Price level at which the TSMOM state flips: price `lookback` months ago times the hurdle."""
    hurdle = (1 + cash_return_annual) ** (lookback / 12)
    return float(monthly.iloc[-1 - lookback] * hurdle)
