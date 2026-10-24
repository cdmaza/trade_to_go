"""Golden-file tests on real BNM OpenAPI responses captured 2026-10-21."""

import pytest

from tests.conftest import GOLDEN
from trade_to_go.schemas.gold import KIJANG_DAILY, USDMYR_DAILY
from trade_to_go.sources.bnm import BnmSource

FX = GOLDEN / "bnm" / "fx_usd_2008-01__20261021T000000Z.json"
KIJANG = GOLDEN / "bnm" / "kijang_2020-07__20261021T000000Z.json"


def test_parse_fx():
    df = USDMYR_DAILY.validate(BnmSource.parse_fx([FX]))
    assert len(df) == 20
    first = df.iloc[0]
    assert str(first["date"].date()) == "2008-01-02"
    assert first["usdmyr_mid"] == pytest.approx(3.309)
    assert first["usdmyr_buy"] < first["usdmyr_mid"] < first["usdmyr_sell"]


def test_parse_kijang():
    df = KIJANG_DAILY.validate(BnmSource.parse_kijang([KIJANG]))
    assert len(df) == 20
    first = df.iloc[0]
    assert str(first["date"].date()) == "2020-07-01"
    assert (first["kijang_buy_oz"], first["kijang_sell_oz"]) == (7780.0, 8099.0)
    assert first["kijang_mid_oz"] == 7939.5


def test_latest_fetch_wins(tmp_path):
    old = tmp_path / "fx_usd_2008-01__20200101T000000Z.json"
    old.write_text('{"data": {"unit": 1, "rate": [{"date": "2008-01-02", "buying_rate": 1, "selling_rate": 1, '
                   '"middle_rate": 1}]}}')
    new = tmp_path / FX.name
    new.write_bytes(FX.read_bytes())
    assert BnmSource.latest_per_month([new, old]) == [new]
