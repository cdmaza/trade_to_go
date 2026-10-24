"""Golden-file tests: parse real captured BGD messages. If Bursa changes the
message format, these fail before bad rows reach staging.
"""

import json

import pandas as pd
import pandera.pandas as pa
import pytest

from trade_to_go.schemas.bgd import BGD_QUOTES
from trade_to_go.sources.bgd import BgdSource
from tests.conftest import GOLDEN

SAMPLE = GOLDEN / "bgd" / "20261021T134101105499Z.json"


def test_parse_golden_message():
    df = BGD_QUOTES.validate(BgdSource.parse([SAMPLE]))
    row = df.iloc[0]

    assert row["code"] == "A02"
    assert row["buy_price"] == pytest.approx(541.61)
    assert row["sell_price"] == pytest.approx(561.52)
    assert row["spread"] == pytest.approx(19.91)
    # 21:41:01 MYT == 13:41:01 UTC
    assert row["quoted_at"] == pd.Timestamp("2026-10-21 13:41:01", tz="UTC")
    assert row["fetched_at"] == pd.Timestamp("2026-10-21 13:41:01.105499", tz="UTC")


def test_missing_price_fails_validation(tmp_path):
    data = json.loads(SAMPLE.read_text())
    del data["bursaSellPrice"]
    broken = tmp_path / SAMPLE.name
    broken.write_text(json.dumps(data))

    with pytest.raises(pa.errors.SchemaError):
        BGD_QUOTES.validate(BgdSource.parse([broken]))
