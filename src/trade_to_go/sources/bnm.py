"""Bank Negara Malaysia OpenAPI: USD/MYR exchange rates and Kijang Emas prices.

Docs: https://apikijangportal.bnm.gov.my/openapi
History found in the API: USD/MYR from 2008, Kijang Emas from mid-2020.
Raw files are one JSON response per (dataset, month, fetch time).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings
from trade_to_go.core.http import Session
from trade_to_go.sources.base import RawPayload

FETCH_STAMP = "%Y%m%dT%H%M%SZ"


class BnmSource:
    name = "bnm"

    def __init__(self, base_url: str, accept: str, fx_session: str = "1200", max_requests_per_s: float = 2):
        self.base_url = base_url.rstrip("/")
        self.fx_session = fx_session
        self.http = Session(max_requests_per_s=max_requests_per_s)
        self.http.headers["Accept"] = accept

    @classmethod
    def from_settings(cls) -> BnmSource:
        cfg = get_settings().sources["bnm"]
        return cls(cfg["base_url"], cfg["accept"], str(cfg.get("fx_session", "1200")),
                   cfg.get("max_requests_per_s", 2))

    def fetch_month(self, dataset: str, year: int, month: int) -> RawPayload:
        """dataset is "fx_usd" or "kijang"."""
        if dataset == "fx_usd":
            url = f"{self.base_url}/exchange-rate/USD/year/{year}/month/{month}?session={self.fx_session}&quote=rm"
        elif dataset == "kijang":
            url = f"{self.base_url}/kijang-emas/year/{year}/month/{month}"
        else:
            raise ValueError(f"unknown BNM dataset {dataset!r}")
        response = self.http.get(url)
        response.raise_for_status()
        fetched_at = datetime.now(timezone.utc)
        name = f"{dataset}_{year:04d}-{month:02d}__{fetched_at.strftime(FETCH_STAMP)}.json"
        return RawPayload(name=name, payload=response.content, url=url, fetched_at=fetched_at)

    @staticmethod
    def latest_per_month(paths: list[Path]) -> list[Path]:
        """Keep only the most recent fetch of each (dataset, month)."""
        latest: dict[str, Path] = {}
        for path in sorted(paths, key=lambda p: p.stem.split("__")[1]):
            latest[path.stem.split("__")[0]] = path
        return sorted(latest.values())

    @staticmethod
    def parse_fx(paths: list[Path]) -> pd.DataFrame:
        rows = []
        for path in BnmSource.latest_per_month(paths):
            data = json.loads(path.read_bytes())["data"]
            unit = data.get("unit", 1) or 1
            for r in data.get("rate", []):
                rows.append({
                    "date": r["date"],
                    "usdmyr_buy": _per_unit(r.get("buying_rate"), unit),
                    "usdmyr_sell": _per_unit(r.get("selling_rate"), unit),
                    "usdmyr_mid": _per_unit(r.get("middle_rate"), unit),
                })
        df = pd.DataFrame(rows, columns=["date", "usdmyr_buy", "usdmyr_sell", "usdmyr_mid"])
        df["date"] = pd.to_datetime(df["date"])
        return df

    @staticmethod
    def parse_kijang(paths: list[Path]) -> pd.DataFrame:
        """MYR per troy ounce for the 1 oz coin; buy = BNM buys from you, sell = BNM sells to you."""
        rows = []
        for path in BnmSource.latest_per_month(paths):
            data = json.loads(path.read_bytes())["data"]
            for r in data if isinstance(data, list) else [data]:
                rows.append({
                    "date": r["effective_date"],
                    "kijang_buy_oz": float(r["one_oz"]["buying"]),
                    "kijang_sell_oz": float(r["one_oz"]["selling"]),
                })
        df = pd.DataFrame(rows, columns=["date", "kijang_buy_oz", "kijang_sell_oz"])
        df["date"] = pd.to_datetime(df["date"])
        df["kijang_mid_oz"] = (df["kijang_buy_oz"] + df["kijang_sell_oz"]) / 2
        return df


def _per_unit(value, unit) -> float | None:
    return None if value is None else float(value) / unit
