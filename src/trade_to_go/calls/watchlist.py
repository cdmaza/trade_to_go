"""The user's own stock list (config/watchlist.yaml), edited through `ttg watch`."""

from __future__ import annotations

import re

import yaml

from trade_to_go.core.config import get_settings, load_yaml

HEADER = """# Your own stocks. `ttg call` always shows these, whatever the call is (BUY, HOLD or SELL).
# Edit with: ttg watch add AAPL | ttg watch remove AAPL | ttg watch list
"""
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def load() -> list[str]:
    try:
        return [str(s).upper() for s in load_yaml("watchlist.yaml").get("symbols", []) or []]
    except FileNotFoundError:
        return []


def _save(symbols: list[str]) -> None:
    path = get_settings().root / "config" / "watchlist.yaml"
    body = yaml.safe_dump({"symbols": symbols}, default_flow_style=False, sort_keys=False)
    path.write_text(HEADER + body, encoding="utf-8")


def add(symbols: list[str]) -> list[str]:
    current = load()
    for raw in symbols:
        sym = raw.strip().upper()
        if not SYMBOL.match(sym):
            raise ValueError(f"{raw!r} is not a ticker symbol")
        if sym not in current:
            current.append(sym)
    _save(current)
    return current


def remove(symbols: list[str]) -> list[str]:
    drop = {s.strip().upper() for s in symbols}
    current = [s for s in load() if s not in drop]
    _save(current)
    return current
