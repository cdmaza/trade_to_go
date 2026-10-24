"""SEC EDGAR XBRL company facts (data.sec.gov). Free; max 10 requests/s; requests must
carry a User-Agent naming you and a contact email (EDGAR_USER_AGENT in .env).

Every fact keeps its `filed` date: fundamentals are joined on filed <= as-of date, never
on the period end, to avoid look-ahead.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings, require_env
from trade_to_go.core.http import Session
from trade_to_go.sources.base import RawPayload

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# field -> candidate (taxonomy, concept), first match wins per filing
CONCEPTS: dict[str, list[tuple[str, str]]] = {
    "assets": [("us-gaap", "Assets")],
    "equity": [("us-gaap", "StockholdersEquity")],
    "gross_profit": [("us-gaap", "GrossProfit")],
    "revenue": [("us-gaap", "Revenues"), ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
                ("us-gaap", "SalesRevenueNet")],
    "net_income": [("us-gaap", "NetIncomeLoss")],
    "shares": [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")],
}
FLOW_FIELDS = {"gross_profit", "revenue", "net_income"}


class EdgarSource:
    name = "edgar"

    def __init__(self, base_url: str, max_requests_per_s: float = 10):
        (user_agent,) = require_env("EDGAR_USER_AGENT")
        self.base_url = base_url.rstrip("/")
        self.http = Session(max_requests_per_s=min(max_requests_per_s, 10), user_agent=user_agent)

    @classmethod
    def from_settings(cls) -> EdgarSource:
        cfg = get_settings().sources["edgar"]
        return cls(cfg["base_url"], cfg.get("max_requests_per_s", 10))

    def _get(self, url: str, name: str) -> RawPayload:
        response = self.http.get(url)
        response.raise_for_status()
        fetched_at = datetime.now(timezone.utc)
        return RawPayload(f"{name}__{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.json", response.content, url, fetched_at)

    def fetch_tickers(self) -> RawPayload:
        return self._get(TICKERS_URL, "company_tickers")

    def fetch_company_facts(self, cik: int) -> RawPayload:
        return self._get(f"{self.base_url}/api/xbrl/companyfacts/CIK{cik:010d}.json", f"companyfacts_{cik:010d}")

    @staticmethod
    def parse_tickers(path: Path) -> pd.DataFrame:
        data = json.loads(path.read_bytes())
        df = pd.DataFrame(data.values()).rename(columns={"cik_str": "cik", "title": "name"})
        return df[["cik", "ticker", "name"]]

    @staticmethod
    def parse_company_facts(paths: list[Path]) -> pd.DataFrame:
        """Long table of the CONCEPTS fields, one row per reported value."""
        rows = []
        for path in paths:
            data = json.loads(path.read_bytes())
            facts = data.get("facts", {})
            for field, candidates in CONCEPTS.items():
                for taxonomy, concept in candidates:
                    units = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
                    for unit, values in units.items():
                        for v in values:
                            rows.append({
                                "cik": int(data["cik"]), "field": field, "concept": concept, "unit": unit,
                                "start": v.get("start"), "end": v["end"], "val": float(v["val"]),
                                "fy": v.get("fy"), "fp": v.get("fp"), "form": v.get("form"),
                                "filed": v["filed"], "accn": v.get("accn"),
                            })
        cols = ["cik", "field", "concept", "unit", "start", "end", "val", "fy", "fp", "form", "filed", "accn"]
        df = pd.DataFrame(rows, columns=cols)
        for c in ("start", "end", "filed"):
            df[c] = pd.to_datetime(df[c])
        return df


def point_in_time(facts: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Latest known value per (cik, field) using only facts filed on or before `as_of`.
    Flow fields use annual (≈12-month) durations; stock fields use the latest instant.
    """
    known = facts[facts["filed"] <= as_of].copy()
    duration = (known["end"] - known["start"]).dt.days
    is_flow = known["field"].isin(FLOW_FIELDS)
    known = known[~is_flow | duration.between(350, 380)]
    # Prefer the first candidate concept per field.
    order = {(f, c): i for f, cands in CONCEPTS.items() for i, (_, c) in enumerate(cands)}
    known["rank"] = [order.get((f, c), 99) for f, c in zip(known["field"], known["concept"])]
    known = known.sort_values(["cik", "field", "end", "rank", "filed"], ascending=[True, True, True, False, True])
    latest = known.groupby(["cik", "field"]).tail(1)
    return latest.pivot(index="cik", columns="field", values="val")
