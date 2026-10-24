"""Live signal at date T must equal the backtest signal for the last completed month before T,
computed on the FULL history. A mismatch means look-ahead or diverging code paths.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from trade_to_go.features.trend import month_end
from trade_to_go.signals import gold_rules, live

DAILY = pd.Series(
    100 * np.exp(np.cumsum(np.random.default_rng(7).normal(0.0003, 0.01, 1500))),
    pd.bdate_range("2019-01-01", periods=1500),
)
SPECS = {
    "sma10": ({"rule": "sma_filter", "params": {"n": 10}, "instrument": "X"}, gold_rules.sma_filter, {"n": 10}),
    "tsmom12": ({"rule": "tsmom", "params": {"lookback": 12}, "instrument": "X"}, gold_rules.tsmom, {"lookback": 12}),
}


@pytest.mark.parametrize("name", SPECS)
def test_live_equals_backtest(name, monkeypatch, project):
    spec, rule, params = SPECS[name]
    backtest = rule(month_end(DAILY), **params)

    for today in pd.date_range("2021-03-15", "2024-09-15", freq="47D"):
        # Live only sees prices up to 'today'.
        monkeypatch.setattr(live, "price_series", lambda _, t=today: DAILY[DAILY.index <= t])
        signal = live.evaluate(name, spec, today=today.date())
        expected = backtest[backtest.index.to_period("M") < today.to_period("M")].iloc[-1]
        assert signal.state == ("long" if expected == 1 else "flat"), today
        assert signal.as_of < today.date()
