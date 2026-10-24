"""Load config/settings.yaml and secrets from .env into one Settings object."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

# src/trade_to_go/core/config.py -> project root
DEFAULT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    reports_dir: Path
    timezone: str
    sources: dict
    gold: dict
    reconcile: dict

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def curated_dir(self) -> Path:
        return self.data_dir / "curated"

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse.duckdb"

    @property
    def ops_db_path(self) -> Path:
        return self.data_dir / "ops.sqlite"


def get_settings() -> Settings:
    """Settings for the project root (TTG_ROOT overrides the default)."""
    return _load(Path(os.environ.get("TTG_ROOT") or DEFAULT_ROOT).resolve())


@lru_cache
def _load(root: Path) -> Settings:
    load_dotenv(root / ".env")
    raw = load_yaml("settings.yaml", root)

    def resolve(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else root / path

    return Settings(
        root=root,
        data_dir=resolve(raw.get("data_dir", "data")),
        reports_dir=resolve(raw.get("reports_dir", "reports")),
        timezone=raw.get("timezone", "Asia/Kuala_Lumpur"),
        sources=raw.get("sources", {}),
        gold=raw.get("gold", {}),
        reconcile=raw.get("reconcile", {}),
    )


def load_yaml(name: str, root: Path | None = None) -> dict:
    root = root or get_settings().root
    with open(root / "config" / name, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def require_env(*names: str) -> tuple[str, ...]:
    """Return the named environment variables, failing loudly if any is unset."""
    get_settings()  # make sure .env is loaded
    values = tuple(os.environ.get(name, "").strip() for name in names)
    missing = [name for name, value in zip(names, values) if not value]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    return values
