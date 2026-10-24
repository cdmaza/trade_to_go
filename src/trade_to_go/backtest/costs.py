"""Trading costs. On BGD you buy at Bursa's sell price and sell at Bursa's buy price,
so each one-way trade costs half the spread relative to the mid price.
"""

from __future__ import annotations

import pandas as pd

from trade_to_go.core.storage import read_table, table_path

# From the first captured quote (2026-10-21): spread 19.91 on mid 551.565 MYR/g.
DEFAULT_ONE_WAY = 19.91 / 2 / 551.565


def bgd_one_way_cost(min_quotes: int = 20) -> tuple[float, str]:
    """Median observed half-spread / mid, or the default if too few quotes are stored."""
    if table_path("staging", "bgd_quotes").exists():
        q = read_table("staging", "bgd_quotes")
        if len(q) >= min_quotes:
            mid = (q["buy_price"] + q["sell_price"]) / 2
            return float((q["spread"] / 2 / mid).median()), f"median of {len(q)} BGD quotes"
    return DEFAULT_ONE_WAY, "single BGD quote of 2026-10-21 (collect more with the timer)"


def apply_cost(notional: pd.Series | float, one_way: float):
    return notional * one_way
