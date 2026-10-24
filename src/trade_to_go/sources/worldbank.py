"""World Bank Commodity Price Data (the Pink Sheet), monthly gold.

The gold series is a MONTHLY AVERAGE of daily prices: LBMA PM until May 2025, spot
average from June 2025. Averages smooth returns and inflate Sharpe ratios, so this is
a cross-check for the daily series, never a backtest input.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings
from trade_to_go.core.http import Session
from trade_to_go.sources.base import RawPayload

LINK = re.compile(r"https://thedocs\.worldbank\.org/[^\"']*CMO-Historical-Data-Monthly\.xlsx")


class WorldBankSource:
    name = "worldbank"

    def __init__(self, page_url: str, sheet: str = "Monthly Prices", column: str = "Gold"):
        self.page_url = page_url
        self.sheet = sheet
        self.column = column
        self.http = Session(max_requests_per_s=1)

    @classmethod
    def from_settings(cls) -> WorldBankSource:
        cfg = get_settings().sources["worldbank"]
        return cls(cfg["page_url"], cfg.get("sheet", "Monthly Prices"), cfg.get("column", "Gold"))

    def fetch(self) -> list[RawPayload]:
        # The workbook URL changes with each release; read it from the official page.
        page = self.http.get(self.page_url)
        page.raise_for_status()
        match = LINK.search(page.text)
        if not match:
            raise RuntimeError(f"No CMO-Historical-Data-Monthly.xlsx link on {self.page_url}")
        response = self.http.get(match.group(0))
        response.raise_for_status()
        fetched_at = datetime.now(timezone.utc)
        name = f"cmo_monthly__{fetched_at.strftime('%Y%m%dT%H%M%SZ')}.xlsx"
        return [RawPayload(name=name, payload=response.content, url=match.group(0), fetched_at=fetched_at)]

    def parse(self, paths: list[Path]) -> pd.DataFrame:
        if not paths:
            return pd.DataFrame(columns=["month", "gold_usd_avg"])
        sheet = pd.read_excel(io.BytesIO(sorted(paths)[-1].read_bytes()), sheet_name=self.sheet, header=None)
        header_row = next(i for i in range(15) if any(str(c).strip() == self.column for c in sheet.iloc[i]))
        col = [str(c).strip() for c in sheet.iloc[header_row]].index(self.column)
        body = sheet.iloc[header_row + 2:, [0, col]]
        body.columns = ["period", "gold_usd_avg"]
        body = body[body["period"].astype(str).str.match(r"^\d{4}M\d{2}$")]
        return pd.DataFrame({
            "month": pd.PeriodIndex(body["period"].astype(str).str.replace("M", "-"), freq="M").to_timestamp(),
            "gold_usd_avg": pd.to_numeric(body["gold_usd_avg"], errors="coerce"),
        }).dropna().reset_index(drop=True)
