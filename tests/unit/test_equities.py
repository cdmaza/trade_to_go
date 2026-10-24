"""Fixtures follow the documented EDGAR companyfacts and Tiingo EOD formats. Replace them
with real captured responses (tests/golden/) once EDGAR_USER_AGENT and TIINGO_API_KEY are set.
"""

import json

import numpy as np
import pandas as pd
import pytest

from trade_to_go.features.factors import factor_table
from trade_to_go.signals.factor_screen import composite, select
from trade_to_go.sources.edgar import EdgarSource, point_in_time
from trade_to_go.sources.tiingo import TiingoSource


def fact(end, val, filed, start=None, form="10-K", fp="FY"):
    d = {"end": end, "val": val, "filed": filed, "form": form, "fp": fp, "fy": int(end[:4]), "accn": "x"}
    if start:
        d["start"] = start
    return d


COMPANY = {
    "cik": 1, "entityName": "Example Co",
    "facts": {
        "us-gaap": {
            "Assets": {"units": {"USD": [fact("2022-12-31", 1000, "2023-02-20"),
                                         fact("2023-12-31", 1200, "2024-02-20")]}},
            "GrossProfit": {"units": {"USD": [
                fact("2023-12-31", 300, "2024-02-20", start="2023-01-01"),
                fact("2023-12-31", 90, "2024-02-20", start="2023-10-01", form="10-K", fp="Q4"),  # quarter: ignored
                fact("2023-12-31", 310, "2024-05-01", start="2023-01-01", form="10-K/A"),       # restatement
            ]}},
            "StockholdersEquity": {"units": {"USD": [fact("2023-12-31", 500, "2024-02-20")]}},
        },
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [fact("2024-01-31", 10, "2024-02-20")]}}},
    },
}


@pytest.fixture
def facts(tmp_path):
    path = tmp_path / "companyfacts_0000000001__20260101T000000Z.json"
    path.write_text(json.dumps(COMPANY))
    return EdgarSource.parse_company_facts([path])


def test_point_in_time_ignores_unfiled_values(facts):
    early = point_in_time(facts, pd.Timestamp("2023-06-30"))
    assert early.loc[1, "assets"] == 1000            # 2023 annual report not filed yet
    assert "gross_profit" not in early.columns or pd.isna(early.loc[1].get("gross_profit"))

    later = point_in_time(facts, pd.Timestamp("2024-03-01"))
    assert later.loc[1, "assets"] == 1200
    assert later.loc[1, "gross_profit"] == 300       # annual, not the quarter; restatement not yet filed

    after_restatement = point_in_time(facts, pd.Timestamp("2024-06-01"))
    assert after_restatement.loc[1, "gross_profit"] == 310


def test_tiingo_parse(tmp_path):
    rows = [{"date": "2024-01-02T00:00:00.000Z", "close": 470.0, "adjClose": 460.0, "volume": 1e6,
             "high": 0, "low": 0, "open": 0, "adjHigh": 0, "adjLow": 0, "adjOpen": 0, "adjVolume": 0,
             "divCash": 0.0, "splitFactor": 1.0}]
    path = tmp_path / "SPY__20260101T000000Z.json"
    path.write_text(json.dumps(rows))
    df = TiingoSource.parse([path])
    assert df.iloc[0][["symbol", "close", "adj_close"]].tolist() == ["SPY", 470.0, 460.0]
    assert df.iloc[0]["date"] == pd.Timestamp("2024-01-02")


def test_factor_table_and_screen():
    dates = pd.bdate_range("2023-01-02", "2024-03-01")
    prices = pd.concat([
        pd.DataFrame({"date": dates, "symbol": s, "close": p, "adj_close": p})
        for s, p in (("AAA", np.linspace(10, 20, len(dates))), ("BBB", np.linspace(20, 10, len(dates))),
                     ("CCC", np.linspace(10, 11, len(dates))))
    ])
    fundamentals = pd.DataFrame({
        "assets": [100, 100, 100], "gross_profit": [40, 10, 20], "equity": [50, 50, 50], "shares": [10, 10, 10],
    }, index=["AAA", "BBB", "CCC"])
    table = factor_table(fundamentals, prices, pd.Timestamp("2024-03-01"))

    assert table.loc["AAA", "quality"] == pytest.approx(0.4)
    assert table.loc["AAA", "mom_12_1"] > 0 > table.loc["BBB", "mom_12_1"]
    assert table.loc["BBB", "value"] > table.loc["AAA", "value"]       # cheaper after falling
    assert composite(table).index[0] == "AAA"
    assert select(table, 0.34) == ["AAA"]
