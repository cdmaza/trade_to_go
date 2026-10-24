import hashlib
import json
from datetime import datetime, timezone

import pandas as pd
import pandera.pandas as pa
import pytest

from trade_to_go.core import storage

FETCHED_AT = datetime(2026, 10, 21, 13, 41, tzinfo=timezone.utc)


def test_write_raw_lands_file_and_manifest(project):
    path = storage.write_raw("demo", "a.json", b'{"x": 1}', url="https://example.test", fetched_at=FETCHED_AT)

    assert path == project / "data/raw/demo/ingest_date=2026-10-21/a.json"
    entry = json.loads((path.parent / "_manifest.jsonl").read_text())
    assert entry["sha256"] == hashlib.sha256(b'{"x": 1}').hexdigest()
    assert storage.raw_files("demo") == [path]


def test_write_raw_is_immutable(project):
    storage.write_raw("demo", "a.json", b"1", url="u", fetched_at=FETCHED_AT)
    with pytest.raises(FileExistsError):
        storage.write_raw("demo", "a.json", b"2", url="u", fetched_at=FETCHED_AT)


def test_write_table_validates_before_writing(project):
    schema = pa.DataFrameSchema({"price": pa.Column(float, pa.Check.gt(0))})

    with pytest.raises(pa.errors.SchemaErrors):
        storage.write_table(pd.DataFrame({"price": [-1.0]}), "staging", "demo", schema)
    assert not storage.table_path("staging", "demo").exists()

    storage.write_table(pd.DataFrame({"price": [1.0]}), "staging", "demo", schema)
    assert storage.read_table("staging", "demo")["price"].tolist() == [1.0]


def test_warehouse_exposes_views(project):
    storage.write_table(pd.DataFrame({"price": [1.0, 2.0]}), "curated", "demo")
    con = storage.warehouse()
    assert con.execute("SELECT count(*) FROM curated_demo").fetchone()[0] == 2


def test_track_run_records_success_and_error(project):
    with storage.track_run("ok-job"):
        pass
    with pytest.raises(ValueError), storage.track_run("bad-job"):
        raise ValueError("boom")

    con = storage.ops()
    rows = {r["job"]: r for r in con.execute("SELECT * FROM run_log")}
    assert rows["ok-job"]["status"] == "ok"
    assert rows["bad-job"]["status"] == "error"
    assert "boom" in rows["bad-job"]["detail"]
