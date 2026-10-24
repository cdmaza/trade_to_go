"""Stock calls: your watchlist (always shown) and a short list of potential buys from a candidate pool.

Price-only and rule-based, so it needs nothing but daily prices. BUY needs an uptrend on both
the month-end and live readings, positive 12-1 momentum and a price that is not stretched;
SELL means a downtrend on both readings. Everything else is HOLD (wait / do not chase).
Candidates are ranked by momentum; names that also pass the quality/value/momentum screen
(`ttg screen us`, needs EDGAR data) get a bonus and a tag.

This is a trend/momentum filter. It does not know about earnings, valuation or news, and the
candidate pool is today's survivors, so it says nothing about how the filter would have done
historically (see doc/survivorship.md).
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from trade_to_go.calls import indicators as ind
from trade_to_go.calls.models import BUY, HOLD, NA, SELL, Call


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:+.1%}"


def stock_call(symbol: str, daily: pd.Series, today: date | None = None, cfg: dict | None = None) -> Call:
    cfg = cfg or {}
    overbought = cfg.get("rsi_overbought", 75)
    stale_days = cfg.get("stale_days", 4)
    today = today or date.today()
    daily = daily.dropna().sort_index()
    tv = ind.trend_view(daily, today)
    price, as_of = tv["price"], tv["as_of"]
    if tv["months"] < ind.MIN_MONTHS or tv["sma_official"] is None or tv["sma_live"] is None:
        return Call("stock", symbol, NA, price, "USD", as_of.isoformat(),
                    "Not enough price history for the trend rules (needs 13 completed months).")

    mom = ind.momentum_12_1(daily)
    rsi_v = ind.rsi(daily)
    metrics = {"mom_12_1": mom, "ret_1m": ind.return_over(daily, 1), "ret_3m": ind.return_over(daily, 3),
               "ret_12m": ind.return_over(daily, 12), "rsi14": rsi_v,
               "drawdown_52w": ind.drawdown_from_high(daily), "vol_60d": ind.annual_vol(daily)}
    flip = tv["sma_level"]
    levels = {"sma10_flip": flip}

    up = tv["sma_official"] == "long" and tv["sma_live"] == "long"
    down = tv["sma_official"] == "flat" and tv["sma_live"] == "flat"
    stretched = rsi_v is not None and rsi_v >= overbought
    if up and mom is not None and mom > 0 and not stretched:
        label = BUY
        summary = "Uptrend with positive momentum. Reasonable to buy or add."
    elif down:
        label = SELL
        summary = "Downtrend. Avoid new buying; if you hold it, consider selling or a tight stop."
    elif up and stretched:
        label = HOLD
        summary = "Uptrend but stretched. Hold; wait for a pullback instead of chasing."
    elif up:
        label = HOLD
        summary = "Uptrend but 12-1 momentum is not positive. Hold; no new buying yet."
    else:
        label = HOLD
        summary = "Trend is turning (month-end and live readings disagree). Hold; wait for it to settle."

    reasons = [
        f"10-month average check: month-end {_word(tv['sma_official'])}, live {_word(tv['sma_live'])}.",
        f"12-1 momentum {_pct(mom)}; 1 month {_pct(metrics['ret_1m'])}, 3 months {_pct(metrics['ret_3m'])}, "
        f"12 months {_pct(metrics['ret_12m'])}.",
    ]
    if flip:
        gap = price / flip - 1
        reasons.append(f"Price is {abs(gap):.1%} {'above' if gap >= 0 else 'below'} the 10-month-average flip "
                       f"level ({flip:,.2f}); {'below it the trend turns down' if gap >= 0 else 'above it the trend turns up'}.")
    cautions = []
    if stretched:
        cautions.append(f"Stretched: RSI {rsi_v:.0f}.")
    dd = metrics["drawdown_52w"]
    if dd is not None and dd <= -0.20:
        cautions.append(f"Down {abs(dd):.0%} from its 52-week high.")
    age = (today - as_of).days
    if age > stale_days:
        cautions.append(f"Last price is {age} days old: run `ttg call --refresh`.")
    return Call("stock", symbol, label, price, "USD", as_of.isoformat(), summary, reasons, cautions, metrics, levels)


def _word(state: str | None) -> str:
    return {"long": "up", "flat": "down"}.get(state or "", "n/a")


def rank_potential(calls: list[Call], screen_picks: set[str] | None = None, max_n: int = 5) -> list[Call]:
    """Top `max_n` BUY calls by momentum rank; screen-pick bonus applied and tagged."""
    screen_picks = screen_picks or set()
    buys = [c for c in calls if c.label == BUY]
    if not buys:
        return []
    mom = ind.pct_rank({c.symbol: c.metrics.get("mom_12_1") for c in buys})
    r3 = ind.pct_rank({c.symbol: c.metrics.get("ret_3m") for c in buys})
    vol = ind.pct_rank({c.symbol: c.metrics.get("vol_60d") for c in buys})
    for c in buys:
        c.score = 0.5 * mom[c.symbol] + 0.3 * r3[c.symbol] + 0.1 * (1 - vol[c.symbol])
        if c.symbol in screen_picks:
            c.score += 0.1
            c.tags.append("also a quality/value/momentum screen pick")
    return sorted(buys, key=lambda c: c.score, reverse=True)[:max_n]


def build_stock_section(prices: pd.DataFrame, watchlist: list[str], candidates: list[str],
                        screen_picks: set[str] | None = None, today: date | None = None,
                        cfg: dict | None = None) -> dict:
    """{"watchlist": [Call], "potential": [Call], "missing": [symbols with no prices]}."""
    cfg = cfg or {}
    series = {sym: g.set_index("date")["adj_close"] for sym, g in prices.groupby("symbol")} if len(prices) else {}

    def call_for(sym: str) -> Call | None:
        s = series.get(sym)
        return None if s is None or s.dropna().empty else stock_call(sym, s, today, cfg)

    watch = [c for c in (call_for(s) for s in watchlist) if c]
    pool = [c for s in dict.fromkeys(candidates) if s not in set(watchlist) and (c := call_for(s))]
    potential = rank_potential(pool, screen_picks, cfg.get("max_potential", 5))
    missing = [s for s in dict.fromkeys([*watchlist, *candidates]) if s not in series]
    return {"watchlist": watch, "potential": potential, "missing": missing,
            "pool_size": len(pool), "pool_buys": sum(c.label == BUY for c in pool)}
