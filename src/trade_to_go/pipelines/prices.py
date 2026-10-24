"""Daily price series by instrument name, used by live signals and the alert scorer."""

from __future__ import annotations

import pandas as pd

from trade_to_go.core.storage import read_table, table_path


def price_series(instrument: str) -> pd.Series:
    if instrument == "GOLD_MYR":
        df = read_table("curated", "gold_myr_daily")
        return df.set_index("date")["gold_myr_g"].sort_index()
    if instrument == "KIJANG":
        return read_table("staging", "kijang_daily").set_index("date")["kijang_mid_oz"].sort_index()
    if instrument == "BGD":
        q = read_table("staging", "bgd_quotes")
        q["date"] = q["quoted_at"].dt.tz_convert("Asia/Kuala_Lumpur").dt.tz_localize(None).dt.normalize()
        q["mid"] = (q["buy_price"] + q["sell_price"]) / 2
        return q.sort_values("quoted_at").groupby("date")["mid"].last()
    if table_path("staging", "equity_prices_daily").exists():
        eq = read_table("staging", "equity_prices_daily")
        s = eq[eq["symbol"] == instrument].set_index("date")["adj_close"].sort_index()
        if not s.empty:
            return s
    raise KeyError(f"No price series for instrument {instrument!r}")
