"""LBMA Gold Price PM (USD per troy ounce), imported from a file you download yourself.

Since November 2025 the historical tables are only on the LBMA portal. Non-commercial
users get them by self-certifying; there is no public API to call. Download the gold
PM table (CSV or XLSX) from the portal and run:

    uv run ttg import lbma path/to/file.xlsx

The parser auto-detects the date column and the USD column (preferring one that says
"PM"). If detection picks the wrong column, set sources.lbma.date_column / price_column
in config/settings.yaml.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trade_to_go.sources.base import RawPayload


class LbmaSource:
    name = "lbma"

    def __init__(self, date_column: str | None = None, price_column: str | None = None):
        self.date_column = date_column
        self.price_column = price_column

    def read_file(self, path: Path) -> RawPayload:
        fetched_at = datetime.now(timezone.utc)
        name = f"{fetched_at.strftime('%Y%m%dT%H%M%SZ')}__{path.name}"
        return RawPayload(name=name, payload=path.read_bytes(), url=f"file:{path.name}", fetched_at=fetched_at)

    def parse(self, paths: list[Path]) -> pd.DataFrame:
        """Use the most recent imported file (each import is a full history)."""
        if not paths:
            return pd.DataFrame(columns=["date", "gold_usd_pm"])
        path = sorted(paths)[-1]
        table = _read_table(path)
        date_col = self.date_column or _find_date_column(table)
        price_col = self.price_column or _find_usd_column(table)
        df = pd.DataFrame({
            "date": pd.to_datetime(table[date_col], errors="coerce", dayfirst=_looks_dayfirst(table[date_col])),
            "gold_usd_pm": pd.to_numeric(table[price_col], errors="coerce"),
        })
        return df.dropna().sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def _read_table(path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        sheet = pd.read_excel(io.BytesIO(raw), header=None)
    else:
        sheet = pd.read_csv(io.BytesIO(raw), header=None, dtype=str)
    # The header row is the first row that names a date column.
    for i in range(min(len(sheet), 30)):
        cells = [str(c).strip().lower() for c in sheet.iloc[i]]
        if any(c == "date" or c.startswith("date") for c in cells):
            table = sheet.iloc[i + 1:].reset_index(drop=True)
            table.columns = [str(c).strip() for c in sheet.iloc[i]]
            return table
    raise ValueError(f"No header row with a 'Date' column found in {path.name}")


def _find_date_column(table: pd.DataFrame) -> str:
    return next(c for c in table.columns if c.lower().startswith("date"))


def _find_usd_column(table: pd.DataFrame) -> str:
    usd = [c for c in table.columns if "usd" in c.lower() or "$" in c]
    if not usd:
        raise ValueError(f"No USD column among {list(table.columns)}; set sources.lbma.price_column")
    pm = [c for c in usd if re.search(r"\bpm\b", c.lower())]
    return (pm or usd)[0]


def _looks_dayfirst(values: pd.Series) -> bool:
    sample = values.dropna().astype(str).head(50)
    return any(re.match(r"^(1[3-9]|2\d|3[01])[/-]", v) for v in sample)
