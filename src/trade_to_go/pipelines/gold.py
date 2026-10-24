"""Gold pipeline: sources -> staging -> curated/gold_myr_daily.

gold_myr = LBMA Gold PM (USD/oz) x BNM USD/MYR noon middle rate, from 2008.
Two timing conventions (see config/settings.yaml gold.convention):
  kl_noon   previous London fix x BNM noon rate of KL day d; known at 12:00 KL on d
  same_day  London fix of d x BNM noon rate of d; known at 15:00 London on d
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from trade_to_go.core.config import get_settings
from trade_to_go.core.storage import raw_files, read_table, table_path, write_raw, write_table
from trade_to_go.schemas.bgd import BGD_QUOTES
from trade_to_go.schemas.gold import (
    GOLD_MYR_DAILY,
    GOLD_USD_DAILY,
    GOLD_USD_MONTHLY_AVG,
    KIJANG_DAILY,
    MACRO_DAILY,
    USDMYR_DAILY,
)
from trade_to_go.sources.base import RawPayload
from trade_to_go.sources.bgd import BgdSource
from trade_to_go.sources.bnm import BnmSource
from trade_to_go.sources.fred import FredSource
from trade_to_go.sources.lbma import LbmaSource
from trade_to_go.sources.worldbank import WorldBankSource

TROY_OZ_GRAMS = 31.1034768
MAX_FILL = pd.Timedelta(days=7)  # longest gap bridged when aligning London and KL holidays


def _land(source_name: str, payloads: list[RawPayload]) -> list[Path]:
    return [write_raw(source_name, p.name, p.payload, url=p.url, fetched_at=p.fetched_at) for p in payloads]


# --- BGD -------------------------------------------------------------------

def ingest_bgd() -> list[Path]:
    return _land(BgdSource.name, BgdSource.from_settings().fetch())


def build_bgd_staging() -> Path:
    df = BgdSource.parse(raw_files(BgdSource.name, "*.json"))
    df = df.sort_values("fetched_at").drop_duplicates("fetched_at")
    return write_table(df, "staging", "bgd_quotes", BGD_QUOTES)


# --- BNM -------------------------------------------------------------------

def ingest_bnm(today: date | None = None) -> list[Path]:
    """Backfill missing months; always refetch the current and previous month."""
    today = today or date.today()
    cfg = get_settings().sources["bnm"]
    source = BnmSource.from_settings()
    have = {p.stem.split("__")[0] for p in raw_files(BnmSource.name, "*.json")}
    recent = {(today.year, today.month), _prev_month(today.year, today.month)}

    paths = []
    for dataset, start in (("fx_usd", cfg["fx_start"]), ("kijang", cfg["kijang_start"])):
        for year, month in _months(str(start), today):
            if f"{dataset}_{year:04d}-{month:02d}" in have and (year, month) not in recent:
                continue
            paths += _land(BnmSource.name, [source.fetch_month(dataset, year, month)])
    return paths


def build_bnm_staging() -> list[Path]:
    paths = raw_files(BnmSource.name, "*.json")
    fx = BnmSource.parse_fx([p for p in paths if p.name.startswith("fx_usd_")])
    fx["usdmyr_mid"] = fx["usdmyr_mid"].fillna((fx["usdmyr_buy"] + fx["usdmyr_sell"]) / 2)
    kijang = BnmSource.parse_kijang([p for p in paths if p.name.startswith("kijang_")])
    return [
        write_table(fx.sort_values("date"), "staging", "usdmyr_daily", USDMYR_DAILY),
        write_table(kijang.sort_values("date"), "staging", "kijang_daily", KIJANG_DAILY),
    ]


# --- LBMA (manual import) --------------------------------------------------

def _lbma_source() -> LbmaSource:
    cfg = get_settings().sources.get("lbma", {})
    return LbmaSource(cfg.get("date_column"), cfg.get("price_column"))


def import_lbma(file: Path) -> list[Path]:
    return _land(LbmaSource.name, [_lbma_source().read_file(Path(file))])


def build_lbma_staging() -> Path:
    df = _lbma_source().parse(raw_files(LbmaSource.name))
    return write_table(df, "staging", "gold_usd_daily", GOLD_USD_DAILY)


# --- World Bank, FRED --------------------------------------------------------

def ingest_worldbank() -> list[Path]:
    return _land(WorldBankSource.name, WorldBankSource.from_settings().fetch())


def build_worldbank_staging() -> Path:
    df = WorldBankSource.from_settings().parse(raw_files(WorldBankSource.name, "*.xlsx"))
    return write_table(df, "staging", "gold_usd_monthly_avg", GOLD_USD_MONTHLY_AVG)


def ingest_fred() -> list[Path]:
    return _land(FredSource.name, FredSource.from_settings().fetch())


def build_fred_staging() -> Path:
    df = FredSource.from_settings().parse(raw_files(FredSource.name, "*.json"))
    return write_table(df, "staging", "macro_daily", MACRO_DAILY)


# --- Curated ----------------------------------------------------------------

def derive_gold_myr(gold: pd.DataFrame, fx: pd.DataFrame, convention: str, start: str | None = None) -> pd.DataFrame:
    """Combine LBMA PM (date, gold_usd_pm) with BNM noon FX (date, usdmyr_mid)."""
    g = gold.set_index("date")["gold_usd_pm"].sort_index()
    r = fx.set_index("date")["usdmyr_mid"].sort_index()

    if convention == "kl_noon":
        idx = r.index
        gold_usd = g.reindex(idx - pd.Timedelta(days=1), method="ffill", tolerance=MAX_FILL).to_numpy()
        usdmyr = r.to_numpy()
        available_at = (idx + pd.Timedelta(hours=12)).tz_localize("Asia/Kuala_Lumpur").tz_convert("UTC")
    elif convention == "same_day":
        idx = g.index
        gold_usd = g.to_numpy()
        usdmyr = r.reindex(idx, method="ffill", tolerance=MAX_FILL).to_numpy()
        available_at = (idx + pd.Timedelta(hours=15)).tz_localize("Europe/London").tz_convert("UTC")
    else:
        raise ValueError(f"unknown convention {convention!r}")

    out = pd.DataFrame({
        "date": idx,
        "gold_usd_oz": gold_usd,
        "usdmyr": usdmyr,
        "available_at": available_at,
    })
    out["gold_myr_oz"] = out["gold_usd_oz"] * out["usdmyr"]
    out["gold_myr_g"] = out["gold_myr_oz"] / TROY_OZ_GRAMS
    out["convention"] = convention
    out = out.dropna()
    if start:
        out = out[out["date"] >= pd.Timestamp(start)]
    columns = ["date", "gold_usd_oz", "usdmyr", "gold_myr_oz", "gold_myr_g", "convention", "available_at"]
    return out[columns].reset_index(drop=True)


def build_gold_curated() -> Path:
    if not table_path("staging", "gold_usd_daily").exists():
        raise FileNotFoundError("No LBMA data yet: download the gold PM table from the LBMA portal "
                                "and run `ttg import lbma <file>`")
    cfg = get_settings().gold
    df = derive_gold_myr(read_table("staging", "gold_usd_daily"), read_table("staging", "usdmyr_daily"),
                         cfg.get("convention", "kl_noon"), cfg.get("start"))
    return write_table(df, "curated", "gold_myr_daily", GOLD_MYR_DAILY)


# --- helpers ----------------------------------------------------------------

def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _months(start: str, today: date) -> list[tuple[int, int]]:
    year, month = (int(x) for x in start.split("-")[:2])
    out = []
    while (year, month) <= (today.year, today.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out
