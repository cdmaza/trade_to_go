"""How would the gold trend rules have done on real Kijang Emas prices (2020-07 on)?

The same replay `ttg call` prints under the gold reading, shown as a table. An evidence snapshot,
NOT the pre-registered decision (that needs LBMA daily data and `ttg backtest gold`). About five
years and a handful of trades: it can show a rule is not obviously broken, not that it works.

Run:  uv run python research/kijang_rules_check.py
"""

from __future__ import annotations

from trade_to_go.calls.gold import kijang_spread, load_gold_series
from trade_to_go.calls.replay import replay


def main() -> None:
    daily, source, unit = load_gold_series()
    spread = kijang_spread()
    h = replay(daily, spread)
    if h is None:
        print("Not enough history for a replay.")
        return
    print(f"{source} ({unit}), {h['start'][:7]} to {h['end'][:7]} ({h['months']} months), "
          f"one-way cost {h['one_way_cost']:.2%}\n")
    print(f"{'rule':<20}{'CAGR':>8}{'max DD':>9}{'Sharpe':>8}{'trades':>8}{'in gold':>9}{'DCA IRR':>9}")
    for name, r in h["rules"].items():
        print(f"{name:<20}{r['cagr']:>8.1%}{r['max_dd']:>9.1%}{r['sharpe']:>8.2f}{r['trades']:>8}"
              f"{r['time_in_gold']:>9.0%}{r['dca_irr']:>9.1%}")


if __name__ == "__main__":
    main()
