"""The LBMA portal file format is not known in advance, so the parser is tested
against the common layouts: a preamble, AM/PM columns, CSV or XLSX, day-first dates.
"""

import json

import pandas as pd
import pytest

from trade_to_go.sources.fred import FredSource
from trade_to_go.sources.lbma import LbmaSource

CSV = """LBMA Gold Price,,,
Source: LBMA portal,,,
Date,USD (AM),USD (PM),GBP (PM)
02/01/2008,840.75,846.75,427.5
03/01/2008,860.50,865.00,437.0
14/01/2008,895.0,,452.1
"""


def test_lbma_csv_prefers_usd_pm_and_dayfirst(tmp_path):
    path = tmp_path / "gold.csv"
    path.write_text(CSV)
    df = LbmaSource().parse([path])

    assert df["date"].tolist() == [pd.Timestamp("2008-01-02"), pd.Timestamp("2008-01-03")]  # blank PM dropped
    assert df["gold_usd_pm"].tolist() == [846.75, 865.00]


def test_lbma_xlsx_single_usd_column(tmp_path):
    path = tmp_path / "gold_pm.xlsx"
    pd.DataFrame({"Date": pd.to_datetime(["2024-05-01", "2024-05-02"]), "USD": [2300.5, 2310.0],
                  "EUR": [2100.0, 2110.0]}).to_excel(path, index=False)
    df = LbmaSource().parse([path])
    assert df["gold_usd_pm"].tolist() == [2300.5, 2310.0]


def test_lbma_explicit_columns_override(tmp_path):
    path = tmp_path / "gold.csv"
    path.write_text(CSV)
    df = LbmaSource(price_column="USD (AM)").parse([path])
    assert df["gold_usd_pm"].iloc[0] == 840.75


def test_lbma_without_date_header_fails(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        LbmaSource().parse([path])


def test_fred_parse_drops_missing_and_keeps_latest_fetch(tmp_path):
    def obs(values):
        return json.dumps({"observations": [{"date": d, "value": v} for d, v in values]})

    (tmp_path / "DFII10__20260101T000000Z.json").write_text(obs([("2026-01-01", "1.0")]))
    (tmp_path / "DFII10__20260201T000000Z.json").write_text(obs([("2026-01-01", "."), ("2026-01-02", "1.9")]))
    (tmp_path / "DTWEXBGS__20260201T000000Z.json").write_text(obs([("2026-01-02", "120.5")]))

    source = FredSource("https://example.test", {"real_yield_10y": "DFII10", "broad_dollar": "DTWEXBGS"})
    df = source.parse(sorted(tmp_path.glob("*.json"))).sort_values("series")

    assert df["series"].tolist() == ["broad_dollar", "real_yield_10y"]
    assert df["value"].tolist() == [120.5, 1.9]
