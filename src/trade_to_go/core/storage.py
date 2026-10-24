"""Storage for the three data layers plus operational state.

raw/      immutable bytes exactly as fetched, with a manifest line per file
staging/  typed, deduplicated, schema-validated Parquet (rebuildable from raw)
curated/  joined, point-in-time Parquet used by features, backtests and alerts
warehouse.duckdb  views over staging/curated plus analysis tables
ops.sqlite        operational state only (alerts, runs, dedupe, paper orders)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pandera.pandas as pa

from trade_to_go.core.config import get_settings

LAYERS = ("staging", "curated")

OPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job         TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,          -- running | ok | error
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS signal_state (
    signal      TEXT NOT NULL,
    instrument  TEXT NOT NULL,
    state       TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    PRIMARY KEY (signal, instrument)
);

CREATE TABLE IF NOT EXISTS alert_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    signal        TEXT NOT NULL,
    instrument    TEXT NOT NULL,
    prev_state    TEXT,
    state         TEXT NOT NULL,
    price         REAL NOT NULL,
    invalidation  REAL NOT NULL,
    hit_rate      REAL,
    backtest_id   TEXT,
    ret_5d        REAL, bench_5d  REAL,
    ret_20d       REAL, bench_20d REAL,
    ret_60d       REAL, bench_60d REAL
);

CREATE TABLE IF NOT EXISTS sent_dedupe (
    key      TEXT PRIMARY KEY,
    sent_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS call_state (
    symbol      TEXT PRIMARY KEY,
    label       TEXT NOT NULL,          -- BUY | HOLD | SELL | N/A (last call shown by `ttg call`)
    as_of       TEXT NOT NULL,
    changed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    signal      TEXT NOT NULL,
    instrument  TEXT NOT NULL,
    side        TEXT NOT NULL,
    qty         REAL NOT NULL,
    price       REAL,
    broker_id   TEXT,
    status      TEXT NOT NULL
);
"""


def write_raw(source: str, name: str, payload: bytes, *, url: str, fetched_at: datetime) -> Path:
    """Land one fetched payload. Raw files are never overwritten."""
    folder = get_settings().raw_dir / source / f"ingest_date={fetched_at.date().isoformat()}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    if path.exists():
        raise FileExistsError(f"Raw file already exists and is immutable: {path}")
    path.write_bytes(payload)

    entry = {
        "file": name,
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "fetched_at": fetched_at.isoformat(),
    }
    with open(folder / "_manifest.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return path


def raw_files(source: str, pattern: str = "*") -> list[Path]:
    root = get_settings().raw_dir / source
    return sorted(p for p in root.glob(f"ingest_date=*/{pattern}") if p.name != "_manifest.jsonl")


def table_path(layer: str, dataset: str) -> Path:
    if layer not in LAYERS:
        raise ValueError(f"layer must be one of {LAYERS}, got {layer!r}")
    return get_settings().data_dir / layer / dataset / f"{dataset}.parquet"


def write_table(df: pd.DataFrame, layer: str, dataset: str, schema: pa.DataFrameSchema | None = None) -> Path:
    """Validate (if a schema is given) and replace a staging/curated dataset."""
    if schema is not None:
        df = schema.validate(df, lazy=True)
    path = table_path(layer, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return path


def read_table(layer: str, dataset: str) -> pd.DataFrame:
    return pd.read_parquet(table_path(layer, dataset))


def warehouse() -> duckdb.DuckDBPyConnection:
    """DuckDB connection with a view per dataset, named <layer>_<dataset>."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(settings.warehouse_path))
    for layer in LAYERS:
        for folder in sorted((settings.data_dir / layer).glob("*/")):
            files = list(folder.glob("*.parquet"))
            if files:
                glob = (folder / "*.parquet").as_posix()
                con.execute(f"CREATE OR REPLACE VIEW {layer}_{folder.name} AS SELECT * FROM read_parquet('{glob}')")
    return con


def ops() -> sqlite3.Connection:
    path = get_settings().ops_db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(OPS_SCHEMA)
    return con


@contextmanager
def track_run(job: str) -> Iterator[None]:
    """Record a job in run_log as running, then ok or error."""
    con = ops()
    try:
        with con:
            run_id = con.execute(
                "INSERT INTO run_log (job, started_at, status) VALUES (?, ?, 'running')",
                (job, _now()),
            ).lastrowid
        try:
            yield
        except BaseException as exc:
            with con:
                con.execute("UPDATE run_log SET finished_at = ?, status = 'error', detail = ? WHERE id = ?",
                            (_now(), repr(exc), run_id))
            raise
        with con:
            con.execute("UPDATE run_log SET finished_at = ?, status = 'ok' WHERE id = ?", (_now(), run_id))
    finally:
        con.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
