"""Bursa Gold Dinar (BGD) price stream (ported from the legacy src/extract/get_gold.py).

Reads one message from the BGD websocket and closes. The stream is undocumented;
check Bursa's website terms before polling more often than the systemd timer does.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import websocket

from trade_to_go.core.config import get_settings
from trade_to_go.core.http import DEFAULT_USER_AGENT
from trade_to_go.sources.base import RawPayload

FILE_TIME_FORMAT = "%Y%m%dT%H%M%S%fZ"
MYT = ZoneInfo("Asia/Kuala_Lumpur")


class BgdSource:
    name = "bgd"

    def __init__(self, url: str, origin: str, timeout_s: float = 15):
        self.url = url
        self.origin = origin
        self.timeout_s = timeout_s

    @classmethod
    def from_settings(cls) -> BgdSource:
        cfg = get_settings().sources["bgd"]
        return cls(cfg["url"], cfg["origin"], cfg.get("timeout_s", 15))

    def fetch(self) -> list[RawPayload]:
        ws = websocket.create_connection(
            self.url,
            origin=self.origin,
            header=[f"User-Agent: {DEFAULT_USER_AGENT}"],
            timeout=self.timeout_s,
        )
        try:
            message = ws.recv()
        finally:
            ws.close()

        fetched_at = datetime.now(timezone.utc)
        payload = message.encode("utf-8") if isinstance(message, str) else message
        name = f"{fetched_at.strftime(FILE_TIME_FORMAT)}.json"
        return [RawPayload(name=name, payload=payload, url=self.url, fetched_at=fetched_at)]

    @staticmethod
    def parse(paths: list[Path]) -> pd.DataFrame:
        """One row per message. Prices are MYR per gram from Bursa's side:
        buy_price is what Bursa pays you, sell_price is what you pay Bursa.
        """
        rows = []
        for path in paths:
            data = json.loads(path.read_bytes())
            buy = data.get("bursaBuyPrice")
            sell = data.get("bursaSellPrice")
            rows.append({
                "quoted_at": _parse_bursa_time(data.get("bursaTime")),
                "fetched_at": datetime.strptime(path.stem, FILE_TIME_FORMAT).replace(tzinfo=timezone.utc),
                "code": data.get("bursaCode"),
                "buy_price": buy,
                "sell_price": sell,
                # Missing prices stay missing (NaN) so validation fails instead of storing 0.
                "spread": None if buy is None or sell is None else sell - buy,
                "source_file": path.name,
            })
        columns = ["quoted_at", "fetched_at", "code", "buy_price", "sell_price", "spread", "source_file"]
        return pd.DataFrame(rows, columns=columns)


def _parse_bursa_time(value: str | None) -> datetime | None:
    """'Wed Oct 21 21:41:01 MYT 2026' -> aware UTC datetime."""
    if not value:
        return None
    local = datetime.strptime(value.replace(" MYT ", " "), "%a %b %d %H:%M:%S %Y")
    return local.replace(tzinfo=MYT).astimezone(timezone.utc)
