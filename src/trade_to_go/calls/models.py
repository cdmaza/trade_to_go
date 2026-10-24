"""The shape of a call, shared by the terminal, Markdown, HTML and Telegram renderers."""

from __future__ import annotations

from dataclasses import dataclass, field

BUY, HOLD, SELL, NA = "BUY", "HOLD", "SELL", "N/A"


@dataclass
class Call:
    kind: str                       # "gold" | "stock"
    symbol: str
    label: str                      # BUY | HOLD | SELL | N/A
    price: float | None
    currency: str
    as_of: str                      # ISO date of the last price
    summary: str                    # one line: what to do
    reasons: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    metrics: dict[str, float | None] = field(default_factory=dict)
    levels: dict[str, float | None] = field(default_factory=dict)   # price levels that change the call
    score: float | None = None      # ranking score among candidates (stocks only)
    tags: list[str] = field(default_factory=list)
