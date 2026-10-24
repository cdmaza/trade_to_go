"""Tiingo end-of-day prices (free tier: personal use, limited symbols per month; check the
current limits on tiingo.com). Needs TIINGO_API_KEY in .env.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings, require_env
from trade_to_go.core.http import Session
from trade_to_go.sources.base import RawPayload


class TiingoSource:
    name = "tiingo"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.http = Session(max_requests_per_s=1)

    @classmethod
    def from_settings(cls) -> TiingoSource:
        return cls(get_settings().sources["tiingo"]["base_url"])

    def fetch(self, symbol: str, start: str = "1990-01-01") -> RawPayload:
        (token,) = require_env("TIINGO_API_KEY")
        url = f"{self.base_url}/tiingo/daily/{symbol.lower()}/prices"
        response = self.http.get(url, params={"startDate": start, "token": token})
        response.raise_for_status()
        fetched_at = datetime.now(timezone.utc)
        name = f"{symbol.upper()}__{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
        return RawPayload(name, response.content, url, fetched_at)  # token kept out of the stored URL

    @staticmethod
    def parse(paths: list[Path]) -> pd.DataFrame:
        latest: dict[str, Path] = {}
        for path in sorted(paths, key=lambda p: p.stem.split("__")[1]):
            latest[path.stem.split("__")[0]] = path
        frames = []
        for symbol, path in latest.items():
            df = pd.DataFrame(json.loads(path.read_bytes()))
            if df.empty:
                continue
            frames.append(pd.DataFrame({
                "date": pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize(),
                "symbol": symbol, "close": df["close"].astype(float), "adj_close": df["adjClose"].astype(float),
                "volume": df["volume"].astype(float), "source": "tiingo",
            }))
        cols = ["date", "symbol", "close", "adj_close", "volume", "source"]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
