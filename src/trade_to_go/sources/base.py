"""The contract every source implements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class RawPayload:
    name: str           # file name inside raw/<source>/ingest_date=YYYY-MM-DD/
    payload: bytes      # exactly as received
    url: str
    fetched_at: datetime  # timezone-aware, UTC


class Source(Protocol):
    name: str

    def fetch(self) -> list[RawPayload]:
        """Fetch from the provider. No cleaning, no business logic."""
        ...

    def parse(self, paths: list[Path]) -> pd.DataFrame:
        """Turn this source's raw files into typed rows for the staging layer."""
        ...
