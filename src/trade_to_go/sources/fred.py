"""FRED API (St. Louis Fed). Needs FRED_API_KEY in .env.

FRED's terms forbid scraping the website; use the API only. Series used:
DFII10 (10-year TIPS real yield, from 2003) and DTWEXBGS (broad trade-weighted dollar, from 2006).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings, require_env
from trade_to_go.core.http import Session
from trade_to_go.sources.base import RawPayload


class FredSource:
    name = "fred"

    def __init__(self, base_url: str, series: dict[str, str]):
        self.base_url = base_url.rstrip("/")
        self.series = series  # alias -> FRED series id
        self.http = Session(max_requests_per_s=2)

    @classmethod
    def from_settings(cls) -> FredSource:
        cfg = get_settings().sources["fred"]
        return cls(cfg["base_url"], cfg["series"])

    def fetch(self) -> list[RawPayload]:
        (api_key,) = require_env("FRED_API_KEY")
        payloads = []
        for series_id in self.series.values():
            url = f"{self.base_url}/series/observations"
            response = self.http.get(url, params={"series_id": series_id, "api_key": api_key, "file_type": "json"})
            response.raise_for_status()
            fetched_at = datetime.now(timezone.utc)
            name = f"{series_id}__{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json"
            # The URL is stored without the key.
            payloads.append(RawPayload(name=name, payload=response.content,
                                       url=f"{url}?series_id={series_id}", fetched_at=fetched_at))
        return payloads

    def parse(self, paths: list[Path]) -> pd.DataFrame:
        """Long format: one row per (date, series). FRED marks missing values with '.'."""
        latest: dict[str, Path] = {}
        for path in sorted(paths, key=lambda p: p.stem.split("__")[1]):
            latest[path.stem.split("__")[0]] = path
        aliases = {v: k for k, v in self.series.items()}
        frames = []
        for series_id, path in latest.items():
            obs = json.loads(path.read_bytes())["observations"]
            df = pd.DataFrame(obs, columns=["date", "value"])
            df["value"] = pd.to_numeric(df["value"].replace(".", None), errors="coerce")
            df["series"] = aliases.get(series_id, series_id)
            frames.append(df.dropna(subset=["value"]))
        if not frames:
            return pd.DataFrame(columns=["date", "series", "value"])
        out = pd.concat(frames, ignore_index=True)[["date", "series", "value"]]
        out["date"] = pd.to_datetime(out["date"])
        return out
