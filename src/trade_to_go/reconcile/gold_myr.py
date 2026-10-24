"""Reconcile the derived MYR gold series (LBMA PM x BNM USD/MYR) against
Kijang Emas, Bursa Gold Dinar and the World Bank monthly average.

Tracking error (TE) is the annualised standard deviation of the difference in log
returns. The level premium (target / derived - 1) is reported, not tested: retail
products carry a structural premium; what matters is that they move together.
Pass thresholds live in config/settings.yaml (reconcile:) and were fixed before the
first run.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from trade_to_go.core.config import get_settings
from trade_to_go.core.storage import read_table, table_path
from trade_to_go.pipelines.gold import TROY_OZ_GRAMS, derive_gold_myr

WB_METHOD_CHANGE = pd.Timestamp("2025-06-01")  # World Bank switched from LBMA PM average to spot average


def tracking_stats(derived: pd.Series, target: pd.Series) -> dict:
    df = pd.concat({"derived": derived, "target": target}, axis=1).dropna()
    df = df[(df > 0).all(axis=1)]
    if len(df) < 3:
        return {"n_days": len(df)}
    premium = df["target"] / df["derived"] - 1
    daily = np.log(df).diff().dropna()
    monthly = np.log(df.resample("ME").last()).diff().dropna()
    return {
        "n_days": int(len(df)),
        "start": df.index[0].date().isoformat(),
        "end": df.index[-1].date().isoformat(),
        "mean_premium": float(premium.mean()),
        "std_premium": float(premium.std()),
        "daily_corr": float(daily["derived"].corr(daily["target"])),
        "te_daily_ann": float((daily["target"] - daily["derived"]).std() * np.sqrt(252)),
        "n_months": int(len(monthly)),
        "te_monthly_ann": float((monthly["target"] - monthly["derived"]).std() * np.sqrt(12))
        if len(monthly) > 2 else None,
    }


def _judge(stats: dict, limits: dict, min_days: int = 20) -> str:
    if stats.get("n_days", 0) < limits.get("min_days", min_days) or stats.get("te_monthly_ann") is None:
        return "insufficient"
    ok = stats["te_monthly_ann"] <= limits["max_monthly_te"] and stats["daily_corr"] >= limits["min_daily_corr"]
    return "pass" if ok else "fail"


def _has(dataset: str) -> bool:
    return table_path("staging", dataset).exists()


def run() -> dict:
    settings = get_settings()
    limits = settings.reconcile
    primary = settings.gold.get("convention", "kl_noon")
    start = settings.gold.get("start")
    checks: list[dict] = []

    fx = read_table("staging", "usdmyr_daily") if _has("usdmyr_daily") else None
    kijang = read_table("staging", "kijang_daily").set_index("date")["kijang_mid_oz"] if _has("kijang_daily") else None

    if _has("gold_usd_daily") and fx is not None:
        gold = read_table("staging", "gold_usd_daily")
        for convention in ("kl_noon", "same_day"):
            derived = derive_gold_myr(gold, fx, convention, start).set_index("date")
            if kijang is not None:
                stats = tracking_stats(derived["gold_myr_oz"], kijang)
                status = _judge(stats, limits["kijang"])
                checks.append({"name": f"kijang ({convention})", "primary": convention == primary,
                               "status": status if convention == primary else f"info:{status}", **stats})
            if convention == primary and _has("bgd_quotes"):
                checks.append(_bgd_check(derived["gold_myr_g"], limits["bgd"]))

        if _has("gold_usd_monthly_avg"):
            checks.append(_worldbank_check(gold, limits["worldbank"]))
    else:
        checks.append({"name": "lbma", "status": "missing",
                       "note": "Import the LBMA portal file (`ttg import lbma <file>`) for the daily reconciliation."})

    if kijang is not None and fx is not None and _has("gold_usd_monthly_avg"):
        checks.append(_provisional_monthly(kijang, fx))

    report = _write_report(checks, primary)
    return {"report": str(report), "checks": checks}


def _bgd_check(derived_g: pd.Series, limits: dict) -> dict:
    bgd = read_table("staging", "bgd_quotes")
    bgd["date"] = bgd["quoted_at"].dt.tz_convert("Asia/Kuala_Lumpur").dt.tz_localize(None).dt.normalize()
    bgd["mid_g"] = (bgd["buy_price"] + bgd["sell_price"]) / 2
    target = bgd.sort_values("quoted_at").groupby("date")["mid_g"].last()
    stats = tracking_stats(derived_g, target)
    return {"name": "bgd", "primary": True, "status": _judge(stats, limits, limits.get("min_days", 60)), **stats}


def _worldbank_check(gold: pd.DataFrame, limits: dict) -> dict:
    wb = read_table("staging", "gold_usd_monthly_avg").set_index("month")["gold_usd_avg"]
    ours = gold.set_index("date")["gold_usd_pm"].resample("MS").mean()
    both = pd.concat({"ours": ours, "wb": wb}, axis=1).dropna()
    both = both[both.index < WB_METHOD_CHANGE]
    if both.empty:
        return {"name": "worldbank (lbma monthly mean)", "status": "insufficient", "n_months": 0}
    diff = both["ours"] / both["wb"] - 1
    worst = diff.abs().idxmax()
    return {
        "name": "worldbank (lbma monthly mean)",
        "status": "pass" if diff.abs().max() <= limits["max_abs_monthly_diff"] else "fail",
        "n_months": int(len(both)),
        "max_abs_diff": float(diff.abs().max()),
        "worst_month": worst.date().isoformat(),
        "mean_diff": float(diff.mean()),
    }


def _provisional_monthly(kijang: pd.Series, fx: pd.DataFrame) -> dict:
    """Monthly averages only: World Bank gold x monthly mean USD/MYR vs monthly mean Kijang."""
    wb = read_table("staging", "gold_usd_monthly_avg").set_index("month")["gold_usd_avg"]
    fx_m = fx.set_index("date")["usdmyr_mid"].resample("MS").mean()
    kj_m = kijang.resample("MS").mean()
    df = pd.concat({"derived": wb * fx_m, "target": kj_m}, axis=1).dropna()
    rets = np.log(df).diff().dropna()
    return {
        "name": "kijang vs worldbank (monthly avg)",
        "status": "info",
        "n_months": int(len(df)),
        "start": df.index[0].date().isoformat() if len(df) else None,
        "mean_premium": float((df["target"] / df["derived"] - 1).mean()) if len(df) else None,
        "monthly_corr": float(rets["derived"].corr(rets["target"])) if len(rets) > 2 else None,
        "te_monthly_ann": float((rets["target"] - rets["derived"]).std() * np.sqrt(12)) if len(rets) > 2 else None,
        "note": "Averages, not month-end prices; a sanity check only, not the pass/fail test.",
    }


def _write_report(checks: list[dict], primary: str) -> str:
    folder = get_settings().reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"reconciliation_{date.today().isoformat()}"
    stem.with_suffix(".json").write_text(json.dumps({"primary_convention": primary, "checks": checks}, indent=2))

    def fmt(v):
        if isinstance(v, float):
            return f"{v:.4%}" if abs(v) < 1 else f"{v:.4f}"
        return "" if v is None else str(v)

    keys = ["status", "n_days", "n_months", "start", "end", "mean_premium", "daily_corr", "monthly_corr",
            "te_daily_ann", "te_monthly_ann", "max_abs_diff", "worst_month"]
    lines = [f"# Gold MYR reconciliation, {date.today().isoformat()}", "",
             f"Derived series: LBMA Gold PM x BNM USD/MYR noon middle rate. Primary convention: `{primary}`.",
             f"Gram conversion: 1 troy oz = {TROY_OZ_GRAMS} g.", "",
             "| check | " + " | ".join(keys) + " |", "|---" * (len(keys) + 1) + "|"]
    for c in checks:
        lines.append(f"| {c['name']} | " + " | ".join(fmt(c.get(k)) for k in keys) + " |")
    notes = [f"- **{c['name']}**: {c['note']}" for c in checks if c.get("note")]
    if notes:
        lines += ["", *notes]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(stem.with_suffix(".md"))
