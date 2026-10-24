"""Quality / value / 12-1 momentum composite screen: equal-weight average of the
cross-sectional z-scores; stocks missing any factor are excluded rather than imputed.
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.features.factors import zscore


def composite(factors: pd.DataFrame, columns=("quality", "value", "mom_12_1")) -> pd.Series:
    complete = factors.dropna(subset=list(columns))
    complete = complete[complete["market_cap"] > 0]
    z = pd.concat({c: zscore(complete[c]) for c in columns}, axis=1)
    return z.mean(axis=1).sort_values(ascending=False)


def select(factors: pd.DataFrame, top_fraction: float = 0.2) -> list[str]:
    scores = composite(factors)
    n = max(1, int(round(len(scores) * top_fraction)))
    return list(scores.index[:n])
