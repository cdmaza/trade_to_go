"""Excel export of the staging/curated datasets plus the latest reconciliation."""

from __future__ import annotations

import json
from datetime import date

import pandas as pd

from trade_to_go.core.config import get_settings
from trade_to_go.core.storage import read_table, table_path

SHEETS = [
    ("curated", "gold_myr_daily"),
    ("staging", "usdmyr_daily"),
    ("staging", "kijang_daily"),
    ("staging", "gold_usd_daily"),
    ("staging", "gold_usd_monthly_avg"),
    ("staging", "bgd_quotes"),
    ("staging", "macro_daily"),
]


def export_excel() -> str:
    settings = get_settings()
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / f"trade_to_go_{date.today().isoformat()}.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        recon = sorted(settings.reports_dir.glob("reconciliation_*.json"))
        if recon:
            checks = json.loads(recon[-1].read_text())["checks"]
            pd.DataFrame(checks).to_excel(writer, sheet_name="reconciliation", index=False)
        for layer, dataset in SHEETS:
            if table_path(layer, dataset).exists():
                _excel_safe(read_table(layer, dataset)).to_excel(writer, sheet_name=dataset[:31], index=False)
    return str(path)


def _excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Excel cannot store timezone-aware datetimes; write them as UTC wall time."""
    df = df.copy()
    for col in df.columns:
        if isinstance(df[col].dtype, pd.DatetimeTZDtype):
            df[col] = df[col].dt.tz_convert("UTC").dt.tz_localize(None)
    return df
