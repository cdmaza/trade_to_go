from datetime import date

import numpy as np
import pandas as pd
import pytest

from trade_to_go.alerts.formatter import format_alert
from trade_to_go.alerts.scorer import score_pending, summary
from trade_to_go.alerts.service import process
from trade_to_go.core import storage
from trade_to_go.signals.base import Signal
from trade_to_go.signals.live import completed_month_ends


def sig(state, as_of=date(2026, 9, 30), price=550.0):
    return Signal(name="gold_sma10", instrument="GOLD_MYR", as_of=as_of, state=state, price=price,
                  invalidation=530.0, hit_rate={5: 0.55, 20: 0.6, 60: 0.65}, backtest_id="gold_backtest_x")


def test_fires_only_on_state_change(project):
    sent = []
    assert process(sig("long"), sent.append) is None            # first observation initialises only
    assert process(sig("long"), sent.append) is None            # unchanged
    alert_id = process(sig("flat", date(2026, 10, 31)), sent.append)
    assert alert_id is not None and len(sent) == 1
    assert process(sig("flat", date(2026, 10, 31)), sent.append) is None
    assert "long → flat" in sent[0] and "530.00" in sent[0] and "20d 60%" in sent[0]

    con = storage.ops()
    row = con.execute("SELECT * FROM alert_log").fetchone()
    assert (row["prev_state"], row["state"], row["invalidation"], row["hit_rate"]) == ("long", "flat", 530.0, 0.6)


def test_send_failure_does_not_mark_as_sent(project):
    process(sig("long"))

    def boom(_):
        raise RuntimeError("telegram down")

    with pytest.raises(RuntimeError):
        process(sig("flat", date(2026, 10, 31)), boom)
    con = storage.ops()
    assert con.execute("SELECT count(*) FROM sent_dedupe").fetchone()[0] == 0


def test_format_macro_rule_without_level():
    s = Signal("gold_regime", "GOLD_MYR", date(2026, 9, 30), "long", 550.0, None, None, None)
    assert "macro regime flip" in format_alert(s, "flat")


def test_scorer_fills_horizons_and_summary(project):
    con = storage.ops()
    with con:
        con.execute("INSERT INTO alert_log (created_at, signal, instrument, prev_state, state, price, invalidation) "
                    "VALUES ('2026-01-05T04:00:00+00:00', 's', 'GOLD_MYR', 'long', 'flat', 100, 90)")
    days = pd.bdate_range("2026-01-05", periods=70)
    up = pd.Series(np.linspace(100, 170, 70), days)

    filled = score_pending(lambda _: up, lambda inst: inst, con)
    assert filled == 3
    row = con.execute("SELECT * FROM alert_log").fetchone()
    assert row["ret_5d"] == 0.0                     # flat = in cash
    assert row["bench_5d"] == pytest.approx(up.iloc[5] / up.iloc[0] - 1)
    s = summary(con)
    assert s.loc[s.horizon_days == 20, "beat_benchmark"].item() == 0.0  # exiting a rising market lost


def test_scorer_waits_for_enough_data(project):
    con = storage.ops()
    with con:
        con.execute("INSERT INTO alert_log (created_at, signal, instrument, state, price, invalidation) "
                    "VALUES ('2026-01-05T04:00:00+00:00', 's', 'GOLD_MYR', 'long', 100, 90)")
    short = pd.Series(np.linspace(100, 110, 10), pd.bdate_range("2026-01-05", periods=10))
    assert score_pending(lambda _: short, lambda i: i, con) == 1   # only the 5-day horizon


def test_live_uses_completed_months_only():
    daily = pd.Series(1.0, pd.bdate_range("2026-08-01", "2026-10-21"))
    assert completed_month_ends(daily, date(2026, 10, 21)).index[-1] == pd.Timestamp("2026-09-30")
