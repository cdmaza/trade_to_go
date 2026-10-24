"""The Signal contract shared by backtests, alerts and paper trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Signal:
    name: str                 # rule id, e.g. "gold_sma10"
    instrument: str
    as_of: date               # date of the data the signal was computed from
    state: str                # e.g. "long" | "flat"
    price: float              # price the state was evaluated at
    invalidation: float | None  # price level at which this state flips (None for macro-only rules)
    hit_rate: dict[int, float] | None  # backtest hit rate by horizon in trading days {5:, 20:, 60:}
    backtest_id: str | None   # backtest_trials row that produced hit_rate
