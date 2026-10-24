"""Paper trading in the Moomoo simulator (TrdEnv.SIMULATE) via OpenD. Every order is
logged to ops.sqlite paper_orders, so the short-term setup's live record can be scored
before it is ever allowed to alert.

Never switch trd_env to REAL here; real trading is out of scope for this project.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

from trade_to_go.core.storage import ops


class MoomooPaperBroker:
    def __init__(self, host: str | None = None, port: int | None = None, con: sqlite3.Connection | None = None):
        self.host = host or os.environ.get("MOOMOO_OPEND_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("MOOMOO_OPEND_PORT", 11111))
        self.con = con

    def place(self, signal: str, symbol: str, side: str, qty: float, limit_price: float) -> str:
        from moomoo import OpenSecTradeContext, OrderType, RET_OK, TrdEnv, TrdMarket, TrdSide

        code = symbol if "." in symbol else f"US.{symbol.upper()}"
        ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host=self.host, port=self.port)
        try:
            ret, data = ctx.place_order(
                price=limit_price, qty=qty, code=code,
                trd_side=TrdSide.BUY if side == "buy" else TrdSide.SELL,
                order_type=OrderType.NORMAL, trd_env=TrdEnv.SIMULATE,
            )
        finally:
            ctx.close()
        status = "submitted" if ret == RET_OK else f"rejected: {data}"
        broker_id = str(data["order_id"].iloc[0]) if ret == RET_OK else None
        self._log(signal, symbol, side, qty, limit_price, broker_id, status)
        if ret != RET_OK:
            raise RuntimeError(f"moomoo simulator rejected order: {data}")
        return broker_id

    def _log(self, signal, symbol, side, qty, price, broker_id, status) -> None:
        con = self.con or ops()
        with con:
            con.execute(
                "INSERT INTO paper_orders (created_at, signal, instrument, side, qty, price, broker_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), signal, symbol, side, qty, price,
                 broker_id, status),
            )
        if self.con is None:
            con.close()
