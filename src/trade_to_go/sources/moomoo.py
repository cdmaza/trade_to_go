"""Moomoo OpenAPI quotes through a running OpenD gateway (`uv sync --extra broker`).

Historical K-lines are quota-limited (base tier: 100 distinct stocks per rolling 30 days),
so use Moomoo for index ETFs and the short-term universe, not for broad backfills.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from trade_to_go.sources.base import RawPayload


class MoomooSource:
    name = "moomoo"

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or os.environ.get("MOOMOO_OPEND_HOST", "127.0.0.1")
        self.port = int(port or os.environ.get("MOOMOO_OPEND_PORT", 11111))

    def fetch_daily(self, symbol: str, start: str, end: str | None = None) -> RawPayload:
        from moomoo import AuType, KLType, OpenQuoteContext, RET_OK

        code = symbol if "." in symbol else f"US.{symbol.upper()}"
        ctx = OpenQuoteContext(host=self.host, port=self.port)
        try:
            frames, page_key = [], None
            while True:
                ret, data, page_key = ctx.request_history_kline(
                    code, start=start, end=end, ktype=KLType.K_DAY, autype=AuType.QFQ,
                    max_count=1000, page_req_key=page_key)
                if ret != RET_OK:
                    raise RuntimeError(f"moomoo kline error for {code}: {data}")
                frames.append(data)
                if page_key is None:
                    break
        finally:
            ctx.close()
        fetched_at = datetime.now(timezone.utc)
        payload = pd.concat(frames, ignore_index=True).to_json(orient="records").encode()
        name = f"{code}__{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        return RawPayload(name, payload, f"opend://{code}/K_DAY/QFQ", fetched_at)

    @staticmethod
    def parse(paths) -> pd.DataFrame:
        latest = {}
        for path in sorted(paths, key=lambda p: p.stem.split("__")[1]):
            latest[path.stem.split("__")[0]] = path
        frames = []
        for code, path in latest.items():
            df = pd.read_json(path)
            frames.append(pd.DataFrame({
                "date": pd.to_datetime(df["time_key"]).dt.normalize(),
                "symbol": code.split(".", 1)[1], "close": df["close"].astype(float),
                "adj_close": df["close"].astype(float),  # QFQ = forward-adjusted
                "volume": df["volume"].astype(float), "source": "moomoo",
            }))
        cols = ["date", "symbol", "close", "adj_close", "volume", "source"]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
