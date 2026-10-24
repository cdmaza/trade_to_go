"""End to end on synthetic data: LBMA import -> curated -> reconciliation -> daily backtest.
Kijang is built as the derived series x 1.04 with small noise, so reconciliation must pass.
"""

import json

import numpy as np
import pandas as pd

from trade_to_go.backtest.gold_study import run as run_study
from trade_to_go.core.storage import read_table, write_table
from trade_to_go.pipelines import gold
from trade_to_go.reconcile.gold_myr import run as run_reconcile


def test_gold_pipeline_end_to_end(project, tmp_path):
    rng = np.random.default_rng(3)
    days = pd.bdate_range("2007-06-01", "2026-09-30")
    usd = 650 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, len(days))))
    fx = 3.4 * np.exp(np.cumsum(rng.normal(0.00002, 0.003, len(days))))

    lbma_csv = tmp_path / "lbma_gold_pm.csv"
    pd.DataFrame({"Date": days.strftime("%d/%m/%Y"), "USD (PM)": usd.round(2)}).to_csv(lbma_csv, index=False)
    write_table(pd.DataFrame({"date": days, "usdmyr_buy": fx - 0.002, "usdmyr_sell": fx + 0.002, "usdmyr_mid": fx}),
                "staging", "usdmyr_daily")

    gold.import_lbma(lbma_csv)
    gold.build_lbma_staging()
    gold.build_gold_curated()
    curated = read_table("curated", "gold_myr_daily")
    assert curated["date"].min() >= pd.Timestamp("2008-01-01")
    assert (curated["convention"] == "kl_noon").all()

    derived = curated.set_index("date")["gold_myr_oz"]
    kj = derived[derived.index >= "2020-07-01"] * 1.04 * np.exp(rng.normal(0, 0.001, (derived.index >= "2020-07-01").sum()))
    write_table(pd.DataFrame({"date": kj.index, "kijang_buy_oz": kj * 0.98, "kijang_sell_oz": kj * 1.02,
                              "kijang_mid_oz": kj}), "staging", "kijang_daily")

    recon = run_reconcile()
    primary = next(c for c in recon["checks"] if c["name"] == "kijang (kl_noon)")
    assert primary["status"] == "pass"
    assert abs(primary["mean_premium"] - 0.04) < 0.002
    same_day = next(c for c in recon["checks"] if c["name"] == "kijang (same_day)")
    assert same_day["te_daily_ann"] > primary["te_daily_ann"]   # wrong timing shows up as tracking error

    result = run_study(provisional=False)
    assert result["decision"]["answer"] in {"DCA", "sma10", "tsmom12"}
    assert set(result["rules"]["sma10"]["hit_rate"]) == {5, 20, 60}
    saved = json.loads(open(result["report"].replace(".md", ".json")).read())
    assert saved["n_trials"] == 8 and not saved["provisional"]
