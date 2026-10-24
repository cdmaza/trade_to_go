from datetime import date

import numpy as np
import pandas as pd
import pytest

from trade_to_go.calls import gold as gold_calls
from trade_to_go.calls import indicators as ind
from trade_to_go.calls import render, service, watchlist
from trade_to_go.calls.models import BUY, HOLD, NA, SELL
from trade_to_go.calls.replay import replay
from trade_to_go.calls.stocks import build_stock_section, rank_potential, stock_call
from trade_to_go.core import storage

TODAY = date(2026, 10, 23)
EVIDENCE = {"answer": "undecided", "why": "", "provisional": True, "report": None}


def series(start_price, end_price, start="2025-01-01", end="2026-10-21", wiggle=0.0, seed=1):
    days = pd.bdate_range(start, end)
    base = np.linspace(start_price, end_price, len(days))
    noise = np.random.default_rng(seed).normal(0, wiggle, len(days)) if wiggle else 0
    return pd.Series(base * (1 + noise), days)


def test_trend_view_flip_levels_match_hand_calculation():
    # month-end closes Sep 2025..Sep 2026 = 100..112; Oct 2026 has data, so the live point is the last price
    idx = list(pd.bdate_range("2025-09-01", "2026-10-21"))
    s = pd.Series(100.0, idx)
    ends = pd.Series(range(100, 113), pd.period_range("2025-09", "2026-09", freq="M").to_timestamp("M"))
    for ts, v in ends.items():
        s[s.index.to_period("M") == ts.to_period("M")] = float(v)
    s.iloc[-1] = 120.0
    tv = ind.trend_view(s, TODAY)
    # previous 9 completed month-ends are 104..112 -> mean 108
    assert tv["sma_level"] == pytest.approx(108.0)
    assert tv["tsmom_level"] == pytest.approx(101.0)        # the Oct 2025 close, 12 months before Oct 2026
    assert tv["sma_live"] == "long" and tv["tsmom_live"] == "long"


def test_return_and_momentum_need_enough_history():
    short = series(100, 110, start="2026-06-01")
    assert ind.return_over(short, 12) is None
    assert ind.momentum_12_1(short) is None
    long = series(100, 200)
    assert ind.return_over(long, 12) > 0
    assert ind.momentum_12_1(long) > 0


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float), pd.bdate_range("2026-01-01", periods=59))
    assert ind.rsi(up) == 100.0
    down = pd.Series(np.arange(60, 1, -1, dtype=float), pd.bdate_range("2026-01-01", periods=59))
    assert ind.rsi(down) < 1


def test_gold_call_up_down_and_not_enough_history():
    up = gold_calls.gold_call(series(100, 160), "src", "MYR/oz", 0.04, EVIDENCE, TODAY)
    assert up.label == BUY and up.levels["sma10_flip"] < up.price
    assert any("4.0%" in c for c in up.cautions) and any("Evidence" in c for c in up.cautions)

    down = gold_calls.gold_call(series(160, 100), "src", "MYR/oz", None, EVIDENCE, TODAY)
    assert down.label == SELL

    short = gold_calls.gold_call(series(100, 110, start="2026-05-01"), "src", "MYR/oz", None, EVIDENCE, TODAY)
    assert short.label == NA


def test_gold_call_warns_when_data_is_stale():
    stale = series(100, 160, end="2026-10-01")
    call = gold_calls.gold_call(stale, "src", "MYR/oz", None, EVIDENCE, TODAY, {"stale_days": 4})
    assert any("22 days old" in c for c in call.cautions)


def test_stock_call_labels():
    assert stock_call("UP", series(100, 200, wiggle=0.004), TODAY).label in (BUY, HOLD)
    strong = stock_call("UP", series(100, 160), TODAY, {"rsi_overbought": 101})
    assert strong.label == BUY
    stretched = stock_call("UP", series(100, 160), TODAY, {"rsi_overbought": 50})
    assert stretched.label == HOLD and "stretched" in stretched.summary.lower()
    assert stock_call("DOWN", series(200, 100), TODAY).label == SELL
    assert stock_call("NEW", series(100, 110, start="2026-06-01"), TODAY).label == NA


def test_rank_potential_orders_by_momentum_and_tags_screen_picks():
    calls = [stock_call(sym, series(100, end), TODAY, {"rsi_overbought": 101})
             for sym, end in (("SLOW", 130), ("FAST", 220), ("MID", 170))]
    ranked = rank_potential(calls, screen_picks={"SLOW"}, max_n=2)
    assert [c.symbol for c in ranked][0] == "FAST" and len(ranked) == 2
    all_ranked = rank_potential(calls, screen_picks={"SLOW"}, max_n=3)
    slow = next(c for c in all_ranked if c.symbol == "SLOW")
    assert any("screen" in t for t in slow.tags)


def test_stock_section_shows_only_watchlist_plus_top_candidates():
    rows = []
    for sym, (a, b) in {"MINE": (200, 100), "A": (100, 220), "B": (100, 200), "C": (100, 170), "D": (200, 100)}.items():
        s = series(a, b)
        rows.append(pd.DataFrame({"date": s.index, "symbol": sym, "adj_close": s.values}))
    prices = pd.concat(rows)
    section = build_stock_section(prices, ["MINE", "GONE"], ["A", "B", "C", "D", "MINE", "NOPRICE"], None, TODAY,
                                  {"rsi_overbought": 101, "max_potential": 2})
    assert [c.symbol for c in section["watchlist"]] == ["MINE"]
    assert section["watchlist"][0].label == SELL                 # your own stock is shown even when it is a SELL
    assert [c.symbol for c in section["potential"]] == ["A", "B"]  # top 2 BUYs only; D (SELL) and MINE are not repeated
    assert "GONE" in section["missing"] and "NOPRICE" in section["missing"]
    assert section["pool_size"] == 4 and section["pool_buys"] == 3


def test_watchlist_add_remove_validates(project):
    assert watchlist.load() == []
    assert watchlist.add(["aapl", "MSFT", "aapl"]) == ["AAPL", "MSFT"]
    with pytest.raises(ValueError):
        watchlist.add(["not a ticker!"])
    assert watchlist.remove(["AAPL"]) == ["MSFT"]
    assert watchlist.load() == ["MSFT"]


def test_record_changes_baseline_then_changes(project):
    def report(label, symbols=("GOLD",)):
        r = service.Report(generated_at="x", today="2026-10-23")
        r.gold = gold_calls.gold_call(series(100, 160) if label == BUY else series(160, 100), "s", "MYR/oz", None,
                                      EVIDENCE, TODAY)
        r.potential = [stock_call(s, series(100, 160), TODAY, {"rsi_overbought": 101}) for s in symbols if s != "GOLD"]
        return r

    con = storage.ops()
    assert service.record_changes(report(BUY), con) == []                      # baseline: silent
    assert service.record_changes(report(BUY), con) == []                      # unchanged
    changes = service.record_changes(report(SELL), con)
    assert [(c.symbol, prev, c.label) for c, prev in changes] == [("GOLD", BUY, SELL)]
    new = service.record_changes(report(SELL, ("GOLD", "NVDA")), con)           # new potential BUY after baseline
    assert [(c.symbol, prev) for c, prev in new] == [("NVDA", None)]


def test_renderers_produce_all_sections(project, capsys):
    r = service.Report(generated_at="2026-10-23T01:00:00+00:00", today="2026-10-23", evidence=EVIDENCE)
    r.gold = gold_calls.gold_call(series(100, 160), "src", "MYR/oz", 0.04, EVIDENCE, TODAY)
    r.watchlist = [stock_call("AAPL", series(100, 160), TODAY)]
    r.potential = rank_potential([stock_call("NVDA", series(100, 200), TODAY, {"rsi_overbought": 101})])
    md = render.render_markdown(r)
    assert "## Gold" in md and "AAPL" in md and "NVDA" in md and "Not financial advice" in md
    html = render.render_html(r)
    assert html.startswith("<!doctype html>") and "NVDA" in html and "prefers-color-scheme" in html
    tg = render.render_telegram(r, [(r.potential[0], None)])
    assert "What changed" in tg and "NVDA" in tg and len(tg) < 4096
    render.render_terminal(r)
    assert "YOUR STOCKS" in capsys.readouterr().out


def test_html_escapes_user_text(project):
    r = service.Report(generated_at="x", today="2026-10-23", gold_error="<script>alert(1)</script>")
    assert "<script>alert" not in render.render_html(r)


def test_replay_needs_history_and_reports_trades():
    assert replay(series(100, 160, start="2025-06-01"), 0.04) is None
    days = pd.bdate_range("2019-01-01", "2026-10-21")
    saw = pd.Series(100 + 40 * np.sin(np.arange(len(days)) / 90.0) + np.arange(len(days)) * 0.02, days)
    h = replay(saw, 0.04)
    assert h["months"] >= 30 and h["one_way_cost"] == pytest.approx(0.02)
    assert h["rules"]["buy_hold"]["trades"] == 1 and h["rules"]["sma10"]["trades"] >= 2


def test_gold_call_prints_replay_line():
    s = series(100, 160, start="2019-01-01")
    call = gold_calls.gold_call(s, "src", "MYR/oz", 0.04, EVIDENCE, TODAY, history=replay(s, 0.04))
    assert any(c.startswith("Replay on this price history") for c in call.cautions)
