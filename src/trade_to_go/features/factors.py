"""Cross-sectional factors for the US long-term screen, computed point-in-time.

quality   gross profits / total assets (Novy-Marx 2013)
value     book equity / market cap (book-to-market)
mom_12_1  12-month return skipping the latest month
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.features.momentum import mom_12_1
from trade_to_go.features.trend import month_end


def factor_table(fundamentals: pd.DataFrame, prices: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """fundamentals: point_in_time() output indexed by symbol (assets, equity, gross_profit, shares).
    prices: equity_prices_daily (date, symbol, close, adj_close). Uses data up to `as_of` only.
    """
    px = prices[prices["date"] <= as_of]
    last_close = px.sort_values("date").groupby("symbol")["close"].last()
    mom = {}
    for symbol, g in px.groupby("symbol"):
        monthly = month_end(g.set_index("date")["adj_close"])
        m = mom_12_1(monthly)
        mom[symbol] = m.iloc[-1] if len(m) else float("nan")

    f = fundamentals.reindex(last_close.index)
    market_cap = last_close * f.get("shares")
    out = pd.DataFrame({
        "quality": f.get("gross_profit") / f.get("assets"),
        "value": f.get("equity") / market_cap,
        "mom_12_1": pd.Series(mom),
        "market_cap": market_cap,
    })
    return out


def zscore(s: pd.Series, clip: float = 3.0) -> pd.Series:
    z = (s - s.mean()) / s.std(ddof=0)
    return z.clip(-clip, clip)
