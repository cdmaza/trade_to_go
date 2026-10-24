"""Gold (MYR) study: Faber 10-month SMA, MOP 12-month TSMOM, a real-yield/dollar regime
filter, buy-and-hold and monthly DCA, all after BGD spread costs.

Writes reports/gold_backtest_<date>.{md,json} and returns the decision: either a rule
that passes every condition in settings.yaml backtest.decision, or "DCA".
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from trade_to_go.backtest import trials
from trade_to_go.backtest.costs import bgd_one_way_cost
from trade_to_go.backtest.deflated_sharpe import deflated_sharpe
from trade_to_go.backtest.engine import money_weighted_return, simulate
from trade_to_go.backtest.metrics import cagr, max_drawdown, sharpe, sharpe_per_period, state_change_hit_rates
from trade_to_go.backtest.walk_forward import walk_forward
from trade_to_go.core.config import get_settings, load_yaml
from trade_to_go.core.storage import read_table, table_path
from trade_to_go.features.macro import monthly_asof
from trade_to_go.features.trend import month_end
from trade_to_go.pipelines.gold import TROY_OZ_GRAMS
from trade_to_go.signals import gold_rules


def load_inputs(provisional: bool = False) -> dict:
    """Month-end signal prices, execution prices and (if available) daily prices and macro."""
    if not provisional:
        if not table_path("curated", "gold_myr_daily").exists():
            raise FileNotFoundError("curated/gold_myr_daily missing: import LBMA and run `ttg build gold`, "
                                    "or use --provisional")
        g = read_table("curated", "gold_myr_daily").set_index("date")["gold_myr_g"].sort_index()
        monthly = month_end(g)
        # Execute on the first price after the month-end the signal was computed on.
        exec_prices = g.shift(-1).reindex(monthly.index).dropna()
        monthly = monthly.loc[exec_prices.index]
        daily, basis = g, "LBMA PM x BNM USD/MYR, daily (kl_noon)"
    else:
        wb = read_table("staging", "gold_usd_monthly_avg").set_index("month")["gold_usd_avg"]
        fx = read_table("staging", "usdmyr_daily").set_index("date")["usdmyr_mid"].resample("MS").mean()
        m = (wb * fx).dropna() / TROY_OZ_GRAMS
        m.index = m.index + pd.offsets.MonthEnd(0)
        monthly = exec_prices = m[m.index >= pd.Timestamp(get_settings().gold.get("start", "2008-01-01"))]
        daily, basis = None, "PROVISIONAL: World Bank monthly AVERAGE x mean BNM USD/MYR (biased; not for decisions)"

    macro = {}
    if table_path("staging", "macro_daily").exists():
        md = read_table("staging", "macro_daily")
        for alias, lag in (("real_yield_10y", 0), ("broad_dollar", 7)):
            s = md[md["series"] == alias].set_index("date")["value"]
            if not s.empty:
                macro[alias] = monthly_asof(s, monthly.index, lag)
    return {"monthly": monthly, "exec": exec_prices, "daily": daily, "macro": macro, "basis": basis,
            "provisional": provisional}


def build_targets(monthly: pd.Series, macro: dict, variants: dict) -> tuple[dict, dict]:
    headline = {
        "buy_hold": pd.Series(1.0, index=monthly.index),
        "dca": pd.Series(1.0, index=monthly.index),
        "sma10": gold_rules.sma_filter(monthly, 10),
        "tsmom12": gold_rules.tsmom(monthly, 12),
    }
    if {"real_yield_10y", "broad_dollar"} <= macro.keys():
        ry, usd = macro["real_yield_10y"], macro["broad_dollar"]
        headline["regime"] = gold_rules.regime(ry, usd)
        headline["sma10_regime"] = gold_rules.sma_with_regime(monthly, ry, usd, 10)
    extra = {}
    for n in variants.get("sma_months", []):
        extra[f"sma{n}"] = gold_rules.sma_filter(monthly, n)
    for n in variants.get("tsmom_months", []):
        extra[f"tsmom{n}"] = gold_rules.tsmom(monthly, n)
    return headline, extra


def run(provisional: bool = False) -> dict:
    cfg = load_yaml("settings.yaml")["backtest"]
    rf = cfg.get("cash_rate_annual", 0.0)
    inputs = load_inputs(provisional)
    one_way, cost_source = bgd_one_way_cost()
    headline, extra = build_targets(inputs["monthly"], inputs["macro"], cfg.get("variants", {}))
    candidates = {**extra, **{k: v for k, v in headline.items() if k not in ("buy_hold", "dca")}}

    # Common window: every rule has a valid signal from the first month on.
    first_valid = max(s.first_valid_index() for s in {**headline, **extra}.values())
    exec_prices = inputs["exec"].loc[first_valid:]
    family = "gold_myr_provisional" if provisional else "gold_myr_daily"
    dhash = trials.data_hash(exec_prices)

    def lump(target: pd.Series) -> pd.Series:
        return simulate(exec_prices, target, one_way_cost=one_way, initial=1.0, cash_rate_annual=rf).twr

    # Register every trial first so the deflated Sharpe sees the full search.
    for name, target in candidates.items():
        r = lump(target.loc[first_valid:])
        trials.record(family, name, {"one_way_cost": round(one_way, 6)}, dhash, r,
                      {"sr_period": sharpe_per_period(r, rf), "sharpe": sharpe(r, rf), "cagr": cagr(r),
                       "max_dd": max_drawdown(r)})
    srs = trials.family_srs(family)

    rows = {}
    for name, target in headline.items():
        target = target.loc[first_valid:]
        lump_sim = simulate(exec_prices, target, one_way_cost=one_way, initial=1.0, cash_rate_annual=rf)
        dca_sim = simulate(exec_prices, target, one_way_cost=one_way, contribution=1.0, cash_rate_annual=rf)
        r = lump_sim.twr
        row = {
            "cagr": cagr(r), "max_dd": max_drawdown(r), "sharpe": sharpe(r, rf),
            "deflated_sharpe": deflated_sharpe(r, srs) if name not in ("buy_hold", "dca") else None,
            "trades": lump_sim.trades, "time_in_gold": float(target.mean()),
            "dca_terminal": dca_sim.terminal_net, "dca_irr": money_weighted_return(dca_sim.flows, dca_sim.terminal_net),
            "dca_costs": dca_sim.costs_paid,
        }
        if name == "buy_hold":  # lump sum only; its contribution-mode numbers would just repeat DCA
            row.update(dca_terminal=None, dca_irr=None, dca_costs=None)
        if inputs["daily"] is not None and name not in ("buy_hold", "dca"):
            changes = target.diff().fillna(0) != 0
            dates = inputs["daily"].index[inputs["daily"].index.searchsorted(target.index[changes], side="right")
                                          .clip(max=len(inputs["daily"]) - 1)]
            row["hit_rate"] = state_change_hit_rates(inputs["daily"], pd.Series(target[changes].to_numpy(), dates))
        rows[name] = row

    # Walk-forward over all candidates (expanding window, 12-month test blocks).
    def score(target: pd.Series, train_index: pd.Index) -> float:
        r = simulate(exec_prices.loc[train_index], target.loc[train_index], one_way_cost=one_way,
                     initial=1.0, cash_rate_annual=rf).twr
        return sharpe(r, rf) if len(r) > 12 else float("nan")

    wf_target, wf_choices = walk_forward({k: v.loc[first_valid:] for k, v in candidates.items()}, score)
    wf_window = wf_target.dropna().index
    wf = {}
    if len(wf_window):
        for name, target in (("walk_forward", wf_target), ("dca", headline["dca"].loc[first_valid:])):
            sim = simulate(exec_prices.loc[wf_window], target.loc[wf_window], one_way_cost=one_way,
                           contribution=1.0, cash_rate_annual=rf)
            lump_r = simulate(exec_prices.loc[wf_window], target.loc[wf_window], one_way_cost=one_way,
                              initial=1.0, cash_rate_annual=rf).twr
            wf[name] = {"terminal": sim.terminal_net, "irr": money_weighted_return(sim.flows, sim.terminal_net),
                        "sharpe": sharpe(lump_r, rf), "max_dd": max_drawdown(lump_r)}

    decision = _decide(rows, wf, cfg["decision"], provisional)
    result = {
        "basis": inputs["basis"], "provisional": provisional,
        "window": [exec_prices.index[0].date().isoformat(), exec_prices.index[-1].date().isoformat()],
        "months": len(exec_prices), "one_way_cost": one_way, "cost_source": cost_source,
        "cash_rate_annual": rf, "n_trials": len(srs), "rules": rows, "walk_forward": wf,
        "walk_forward_choices": wf_choices, "decision": decision,
    }
    result["report"] = _write_report(result)
    return result


def _decide(rows: dict, wf: dict, rules: dict, provisional: bool) -> dict:
    if provisional:
        return {"answer": "undecided", "why": "Provisional data (monthly averages). Import LBMA daily data first."}
    dca, bh = rows["dca"], rows["buy_hold"]
    passed = []
    for name, row in rows.items():
        if name in ("buy_hold", "dca"):
            continue
        reasons = []
        if rules.get("beat_dca_terminal_wealth") and not row["dca_terminal"] > dca["dca_terminal"]:
            reasons.append("terminal wealth <= DCA")
        if rules.get("beat_buy_hold_sharpe") and not row["sharpe"] > bh["sharpe"]:
            reasons.append("Sharpe <= buy-and-hold")
        if (row["deflated_sharpe"] or 0) < rules.get("min_deflated_sharpe", 0.95):
            reasons.append(f"deflated Sharpe {row['deflated_sharpe']:.2f} < {rules['min_deflated_sharpe']}")
        if rules.get("walk_forward_must_beat_dca") and wf and not wf["walk_forward"]["terminal"] > wf["dca"]["terminal"]:
            reasons.append("walk-forward does not beat DCA")
        row["fails"] = reasons
        if not reasons:
            passed.append(name)
    if not passed:
        return {"answer": "DCA", "why": "No timing rule beat monthly DCA after costs on every condition."}
    best = max(passed, key=lambda n: rows[n]["dca_terminal"])
    return {"answer": best, "why": f"Passed every decision condition; highest DCA terminal wealth among {passed}."}


def _write_report(result: dict) -> str:
    folder = get_settings().reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    tag = "gold_backtest_provisional" if result["provisional"] else "gold_backtest"
    stem = folder / f"{tag}_{date.today().isoformat()}"
    stem.with_suffix(".json").write_text(json.dumps(result, indent=2, default=str))

    def pct(v):
        return "" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.2%}"

    lines = [
        f"# Gold (MYR) backtest, {date.today().isoformat()}", "",
        f"- Data: {result['basis']}",
        f"- Window: {result['window'][0]} to {result['window'][1]} ({result['months']} months)",
        f"- Cost: {result['one_way_cost']:.3%} one way ({result['cost_source']}); cash earns "
        f"{result['cash_rate_annual']:.1%}",
        f"- Trials registered in this family: {result['n_trials']}", "",
        "| rule | CAGR | max DD | Sharpe | deflated Sharpe | trades | time in gold | DCA terminal (per 1/month) "
        "| DCA IRR | hit 5d / 20d / 60d |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in result["rules"].items():
        hits = r.get("hit_rate")
        hit = " / ".join(pct(hits[h]) for h in (5, 20, 60)) if hits else ""
        dsr = "" if r["deflated_sharpe"] is None else f"{r['deflated_sharpe']:.2f}"
        terminal = "" if r["dca_terminal"] is None else f"{r['dca_terminal']:.1f}"
        lines.append(f"| {name} | {pct(r['cagr'])} | {pct(r['max_dd'])} | {r['sharpe']:.2f} | {dsr} | {r['trades']} "
                     f"| {pct(r['time_in_gold'])} | {terminal} | {pct(r['dca_irr'])} | {hit} |")
    if result["walk_forward"]:
        lines += ["", "## Walk-forward (out of sample, expanding window, 12-month blocks)", "",
                  "| | terminal | IRR | Sharpe | max DD |", "|---|---|---|---|---|"]
        for name, w in result["walk_forward"].items():
            lines.append(f"| {name} | {w['terminal']:.1f} | {pct(w['irr'])} | {w['sharpe']:.2f} | {pct(w['max_dd'])} |")
    fails = [f"- {n}: {', '.join(r['fails'])}" for n, r in result["rules"].items() if r.get("fails")]
    lines += ["", "## Decision", "", f"**{result['decision']['answer']}**: {result['decision']['why']}"]
    if fails:
        lines += ["", *fails]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(stem.with_suffix(".md"))
