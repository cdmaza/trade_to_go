import numpy as np
import pandas as pd
import pytest

from trade_to_go.backtest.deflated_sharpe import deflated_sharpe, expected_max_sharpe, probabilistic_sharpe
from trade_to_go.backtest.engine import money_weighted_return, simulate
from trade_to_go.backtest.metrics import cagr, max_drawdown, sharpe, state_change_hit_rates
from trade_to_go.backtest.walk_forward import walk_forward
from trade_to_go.signals import gold_rules

IDX = pd.date_range("2020-01-31", periods=6, freq="ME")
PRICES = pd.Series([100.0, 110.0, 121.0, 110.0, 99.0, 110.0], IDX)


def test_buy_and_hold_without_costs_tracks_price():
    sim = simulate(PRICES, pd.Series(1.0, IDX), one_way_cost=0.0, initial=1.0)
    assert sim.terminal_net == pytest.approx(1.10)
    assert (1 + sim.twr).prod() == pytest.approx(1.10)
    assert sim.trades == 1


def test_costs_are_paid_on_entry_exit_and_liquidation():
    target = pd.Series([1, 1, 0, 0, 1, 1], IDX, dtype=float)
    sim = simulate(PRICES, target, one_way_cost=0.01, initial=1.0)
    # in at 100, out at 121, in at 99, liquidate at 110; four one-way costs
    expected = 0.99 * 1.21 * 0.99 * 0.99 * (110 / 99) * 0.99
    assert sim.terminal_net == pytest.approx(expected)
    assert sim.trades == 3


def test_costs_reduce_twr_in_the_period_they_are_paid():
    sim = simulate(PRICES, pd.Series(1.0, IDX), one_way_cost=0.02, initial=1.0)
    assert sim.value.iloc[0] == pytest.approx(0.98)
    assert (1 + sim.twr).prod() == pytest.approx(1.10)  # first period has no prior value


def test_dca_contributions_and_irr():
    flat = pd.Series(100.0, IDX)
    sim = simulate(flat, pd.Series(1.0, IDX), one_way_cost=0.0, contribution=1.0)
    assert sim.terminal_net == pytest.approx(6.0)
    assert money_weighted_return(sim.flows, sim.terminal_net) == pytest.approx(0.0, abs=1e-9)

    growing = pd.Series(100 * 1.01 ** np.arange(6), IDX)
    sim = simulate(growing, pd.Series(1.0, IDX), one_way_cost=0.0, contribution=1.0)
    assert money_weighted_return(sim.flows, sim.terminal_net) == pytest.approx(1.01 ** 12 - 1, rel=1e-6)


def test_nan_target_keeps_cash():
    target = pd.Series([np.nan, np.nan, 1, 1, 1, 1], IDX)
    sim = simulate(PRICES, target, one_way_cost=0.0, contribution=1.0)
    assert sim.position.tolist() == [0, 0, 1, 1, 1, 1]


def test_metrics():
    r = pd.Series([0.1, -0.5, 0.2])
    assert cagr(pd.Series([0.01] * 12)) == pytest.approx(1.01 ** 12 - 1)
    assert max_drawdown(r) == pytest.approx(-0.5)
    assert sharpe(pd.Series([0.01, 0.03])) == pytest.approx(0.02 / np.std([0.01, 0.03], ddof=1) * np.sqrt(12))


def test_hit_rates():
    daily = pd.Series(np.arange(100, 200, dtype=float), pd.bdate_range("2024-01-01", periods=100))
    changes = pd.Series([1.0, 0.0], [daily.index[0], daily.index[10]])
    hits = state_change_hit_rates(daily, changes, horizons=(5,))
    assert hits[5] == 0.5  # rising market: the entry is right, the exit is wrong


def test_probabilistic_sharpe_behaviour():
    rng = np.random.default_rng(0)
    good = pd.Series(rng.normal(0.02, 0.04, 240))
    noise = pd.Series(rng.normal(0.0, 0.04, 240))
    assert probabilistic_sharpe(good) > 0.99
    assert 0.05 < probabilistic_sharpe(noise) < 0.95


def test_deflated_sharpe_penalises_more_trials():
    rng = np.random.default_rng(1)
    r = pd.Series(rng.normal(0.01, 0.04, 240))
    few = [0.25, 0.2]
    many = list(rng.normal(0.0, 0.1, 200))
    assert expected_max_sharpe(many) > expected_max_sharpe(few) > 0
    assert deflated_sharpe(r, many) < deflated_sharpe(r, few) < probabilistic_sharpe(r)
    assert deflated_sharpe(r, [0.3]) == pytest.approx(probabilistic_sharpe(r))  # one trial = PSR


def test_walk_forward_only_uses_past_data():
    idx = pd.date_range("2010-01-31", periods=48, freq="ME")
    a = pd.Series(1.0, idx)
    b = pd.Series(0.0, idx)
    seen = []

    def score(target, train_index):
        seen.append(train_index[-1])
        return float(target.loc[train_index].mean())

    oos, choices = walk_forward({"a": a, "b": b}, score, min_train=24, test_len=12)
    assert oos.iloc[:24].isna().all()
    assert (oos.iloc[24:] == 1.0).all()
    assert [c["test_start"] for c in choices] == ["2012-01-31", "2013-01-31"]
    assert all(last < pd.Timestamp(c["test_start"]) for last, c in zip(seen[::2], choices))


def test_rules_on_known_series():
    idx = pd.date_range("2020-01-31", periods=14, freq="ME")
    up = pd.Series(np.arange(100, 114, dtype=float), idx)
    assert gold_rules.sma_filter(up, 10).dropna().eq(1).all()
    assert gold_rules.sma_filter(up, 10).iloc[:9].isna().all()
    assert gold_rules.tsmom(up, 12).dropna().tolist() == [1.0, 1.0]
    assert gold_rules.tsmom(up, 12, cash_return_annual=0.5).dropna().tolist() == [0.0, 0.0]
    assert gold_rules.sma_invalidation(up, 10) == pytest.approx(np.mean(np.arange(104, 114)))
    assert gold_rules.tsmom_invalidation(up, 12) == 101.0


def test_regime_rule():
    idx = pd.date_range("2020-01-31", periods=24, freq="ME")
    ry_falling = pd.Series(np.linspace(2, 0, 24), idx)
    usd_rising = pd.Series(np.linspace(100, 120, 24), idx)
    reg = gold_rules.regime(ry_falling, usd_rising)
    assert reg.dropna().eq(1).all() and reg.iloc[:12].isna().all()
    reg = gold_rules.regime(ry_falling[::-1].set_axis(idx), usd_rising)
    assert reg.dropna().eq(0).all()
