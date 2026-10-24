"""Today's gold call: BUY / HOLD / SELL from four trend checks, with the evidence status next to it.

Price series (first that exists):
  1. curated GOLD_MYR  (LBMA PM x BNM noon rate, MYR per gram, from 2008)  after `ttg import lbma`
  2. Kijang Emas mid   (BNM, MYR per ounce, from 2020-07)                  loaded daily, no key needed

The four checks are SMA10 and 12-month momentum, each read two ways (official = last completed
month-end, live = today's price as this month's close). The rules are the backtested ones; the call
is a trend reading, not a validated edge. `evidence` says what the pre-registered backtest decided.
"""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from trade_to_go.calls import indicators as ind
from trade_to_go.calls.models import BUY, HOLD, NA, SELL, Call
from trade_to_go.core.config import get_settings
from trade_to_go.core.storage import read_table, table_path

GRAMS_PER_OZ = 31.1035


def load_gold_series() -> tuple[pd.Series, str, str]:
    """(daily price series, source label, unit)."""
    if table_path("curated", "gold_myr_daily").exists():
        df = read_table("curated", "gold_myr_daily")
        return df.set_index("date")["gold_myr_g"].sort_index(), "LBMA PM x BNM noon rate", "MYR/g"
    k = read_table("staging", "kijang_daily")
    return k.set_index("date")["kijang_mid_oz"].sort_index(), "BNM Kijang Emas (mid)", "MYR/oz"


def kijang_spread() -> float | None:
    """Latest Kijang Emas (sell - buy) / mid: the cost of buying and selling straight back."""
    if not table_path("staging", "kijang_daily").exists():
        return None
    row = read_table("staging", "kijang_daily").sort_values("date").iloc[-1]
    return float((row["kijang_sell_oz"] - row["kijang_buy_oz"]) / row["kijang_mid_oz"])


def evidence() -> dict:
    """What the latest gold backtest decided (non-provisional report preferred)."""
    folder = get_settings().reports_dir
    final = sorted(folder.glob("gold_backtest_2*.json"))
    provisional = sorted(folder.glob("gold_backtest_provisional_*.json"))
    path = (final or provisional or [None])[-1]
    if path is None:
        return {"answer": "none", "why": "No gold backtest has been run yet.", "provisional": True, "report": None}
    data = json.loads(path.read_text())
    decision = data.get("decision", {})
    return {"answer": decision.get("answer", "undecided"), "why": decision.get("why", ""),
            "provisional": bool(data.get("provisional")), "report": path.stem}


def _pct(x: float | None, signed: bool = True) -> str:
    return "n/a" if x is None else f"{x:+.1%}" if signed else f"{x:.1%}"


def _history_line(h: dict) -> str:
    r = h["rules"]
    beat = [n for n in ("sma10", "tsmom12") if r[n]["cagr"] > r["buy_hold"]["cagr"]]
    verdict = ("a timing rule did better than holding (in-sample, so not proof)" if beat
               else "neither timing rule beat simply holding")
    return (f"Replay on this price history ({h['start'][:7]} to {h['end'][:7]}, {h['one_way_cost']:.1%} cost each way): "
            f"holding {r['buy_hold']['cagr']:.1%} a year, 10-month-average rule {r['sma10']['cagr']:.1%} "
            f"({r['sma10']['trades']} trades), 12-month-momentum rule {r['tsmom12']['cagr']:.1%} "
            f"({r['tsmom12']['trades']} trades): {verdict}.")


def gold_call(daily: pd.Series, source: str, unit: str, spread: float | None, ev: dict,
              today: date | None = None, cfg: dict | None = None, history: dict | None = None) -> Call:
    cfg = cfg or {}
    stale_days = cfg.get("stale_days", 4)
    overbought = cfg.get("rsi_overbought", 75)
    today = today or date.today()
    daily = daily.dropna().sort_index()
    tv = ind.trend_view(daily, today)
    price = tv["price"]
    as_of = tv["as_of"]
    states = [tv["sma_official"], tv["tsmom_official"], tv["sma_live"], tv["tsmom_live"]]

    if tv["months"] < ind.MIN_MONTHS or any(s is None for s in states):
        return Call("gold", "GOLD", NA, price, unit, as_of.isoformat(),
                    "Not enough history for the trend rules (needs 13 completed months).")

    longs = sum(s == "long" for s in states)
    label = BUY if longs >= 3 else HOLD if longs == 2 else SELL
    rsi_v = ind.rsi(daily)
    metrics = {"ret_1m": ind.return_over(daily, 1), "ret_3m": ind.return_over(daily, 3),
               "ret_12m": ind.return_over(daily, 12), "rsi14": rsi_v,
               "drawdown_52w": ind.drawdown_from_high(daily), "vol_60d": ind.annual_vol(daily),
               "checks_long": float(longs)}
    levels = {"sma10_flip": tv["sma_level"], "tsmom12_flip": tv["tsmom_level"]}

    def word(s: str) -> str:
        return "up" if s == "long" else "down"

    reasons = [
        f"{longs} of 4 trend checks say up.",
        f"Month-end rules (last completed month): 10-month average {word(tv['sma_official'])}, "
        f"12-month momentum {word(tv['tsmom_official'])}.",
        f"Live reading (today's price as this month's close): 10-month average {word(tv['sma_live'])}, "
        f"12-month momentum {word(tv['tsmom_live'])}.",
    ]
    if tv["sma_level"]:
        gap = price / tv["sma_level"] - 1
        reasons.append(f"Price is {abs(gap):.1%} {'above' if gap >= 0 else 'below'} the level where the 10-month "
                       f"average check flips ({tv['sma_level']:,.0f} {unit}).")
    reasons.append(f"Return: 1 month {_pct(metrics['ret_1m'])}, 3 months {_pct(metrics['ret_3m'])}, "
                   f"12 months {_pct(metrics['ret_12m'])}.")

    cautions = []
    if (tv["sma_official"] == "long") != (tv["sma_live"] == "long") or \
            (tv["tsmom_official"] == "long") != (tv["tsmom_live"] == "long"):
        cautions.append("Live and month-end readings disagree: the trend is changing, so the call may flip at the "
                        "next month-end.")
    if rsi_v is not None and rsi_v >= overbought:
        cautions.append(f"Price looks stretched (RSI {rsi_v:.0f}): buy in 2-3 tranches instead of all at once.")
    if spread:
        cautions.append(f"Buying and selling straight back costs about {spread:.1%} (Kijang Emas spread), so "
                        "trading in and out on every flip loses more than it gains; this suits months-long holds.")
    if tv["months"] < 24:
        cautions.append(f"Only {tv['months']} months of history ({source}). Import LBMA history "
                        "(`ttg import lbma`) for a 2008+ series.")
    age = (today - as_of).days
    if age > stale_days:
        cautions.append(f"Last price is {age} days old: run `ttg call --refresh`.")
    if history:
        cautions.append(_history_line(history))
    ev_line = {"undecided": "not decided yet", "dca": "plain monthly DCA beat every timing rule",
               "none": "no backtest run yet"}.get(ev["answer"], ev["answer"])
    cautions.append(f"Evidence: backtest verdict is '{ev_line}'"
                    + (" (provisional data)" if ev.get("provisional") else "")
                    + ". Treat this as a trend reading, not a proven edge; the default plan stays monthly DCA.")

    summary = {
        BUY: "Trend is up. Keep buying on your DCA schedule; adding extra is reasonable.",
        HOLD: "Trend is mixed. Keep what you hold and continue only the regular DCA; no extra buying.",
        SELL: "Trend is down. Pause new buying and consider trimming what you do not need long-term.",
    }[label]
    return Call("gold", "GOLD", label, price, unit, as_of.isoformat(), summary, reasons, cautions, metrics, levels,
                tags=[source])
