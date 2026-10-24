"""Alert state machine: compare a fresh Signal with the stored state, and on a change
log it, dedupe it and send it. The first observation of a signal only initialises state.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

from trade_to_go.alerts.formatter import format_alert
from trade_to_go.core.storage import ops
from trade_to_go.signals.base import Signal

log = logging.getLogger(__name__)


def process(signal: Signal, send: Callable[[str], object] | None = None,
            con: sqlite3.Connection | None = None) -> int | None:
    """Returns the alert_log id when an alert fired, else None."""
    own = con is None
    con = con or ops()
    try:
        row = con.execute("SELECT state FROM signal_state WHERE signal = ? AND instrument = ?",
                          (signal.name, signal.instrument)).fetchone()
        prev = row["state"] if row else None
        if prev == signal.state:
            return None

        with con:
            con.execute(
                "INSERT INTO signal_state (signal, instrument, state, as_of) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (signal, instrument) DO UPDATE SET state = excluded.state, as_of = excluded.as_of",
                (signal.name, signal.instrument, signal.state, signal.as_of.isoformat()),
            )
        if prev is None:
            log.info("initialised %s/%s as %s (no alert on first observation)", signal.name, signal.instrument,
                     signal.state)
            return None

        key = f"{signal.name}|{signal.instrument}|{signal.state}|{signal.as_of.isoformat()}"
        if con.execute("SELECT 1 FROM sent_dedupe WHERE key = ?", (key,)).fetchone():
            return None

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with con:
            alert_id = con.execute(
                "INSERT INTO alert_log (created_at, signal, instrument, prev_state, state, price, invalidation, "
                "hit_rate, backtest_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now, signal.name, signal.instrument, prev, signal.state, signal.price, signal.invalidation,
                 (signal.hit_rate or {}).get(20), signal.backtest_id),
            ).lastrowid
        if send is not None:
            send(format_alert(signal, prev))
        with con:
            con.execute("INSERT INTO sent_dedupe (key, sent_at) VALUES (?, ?)", (key, now))
        return alert_id
    finally:
        if own:
            con.close()
