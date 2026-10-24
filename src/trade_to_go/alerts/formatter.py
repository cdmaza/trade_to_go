"""Telegram HTML for an alert: signal, price, invalidation level and backtest hit rate."""

from __future__ import annotations

from html import escape

from trade_to_go.signals.base import Signal

ARROWS = {"long": "🟢", "flat": "⚪", "short": "🔴"}


def format_alert(signal: Signal, prev_state: str | None) -> str:
    change = f"{escape(prev_state)} → {escape(signal.state)}" if prev_state else escape(signal.state)
    lines = [
        f"{ARROWS.get(signal.state, '🔔')} <b>{escape(signal.name)}</b> · {escape(signal.instrument)}",
        f"State: <b>{change}</b>",
        f"Price: {signal.price:,.2f}",
        "Invalidated at: " + (f"{signal.invalidation:,.2f}" if signal.invalidation is not None else "macro regime flip"),
    ]
    if signal.hit_rate:
        hits = " · ".join(f"{h}d {rate:.0%}" for h, rate in sorted(signal.hit_rate.items()) if rate == rate)
        lines.append(f"Backtest hit rate: {hits}")
    if signal.backtest_id:
        lines.append(f"<i>backtest {escape(signal.backtest_id)} · data as of {signal.as_of.isoformat()}</i>")
    return "\n".join(lines)
