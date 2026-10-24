# Survivorship-bias limits of the US data

Read this before trusting any US equity backtest from this project.

| Data | Includes delisted companies? | Consequence |
|---|---|---|
| SEC EDGAR company facts | **Yes.** Every filer stays in EDGAR after delisting. | Fundamentals are not survivorship-biased, provided the universe is. |
| `company_tickers.json` (ticker → CIK) | **No.** Current tickers only; reused tickers point to today's company. | Building a universe from it keeps only survivors. Historical tickers need a CIK-based map. |
| Tiingo EOD (free) | Partial; coverage of delisted names is not guaranteed. | Missing price history for failures pushes backtest returns up. |
| Moomoo K-lines | Listed securities only, in practice. | Use only for ETFs and the live short-term universe. |
| Index membership | Not in any free source used here. | A screen run on *today's* S&P 500 over past years is survivorship-biased. |

## What the reports must say
- Any factor-screen backtest built on current constituents is labelled **"survivorship-biased:
  current constituents"**. Treat its returns as an upper bound, especially for value and small caps,
  where failures cluster.
- The ETF trend filter is not materially affected (the ETFs themselves survive; their indexes
  handle membership).
- The forward-scored alert log (from the day alerts start) is free of this bias. That is why
  success criterion 3 judges the live log, not the backtest.

## Partial mitigations, cheapest first
1. Rebuild historical S&P 500 membership from published change lists and run the screen only on
   members as of each rebalance date.
2. Keep delisted CIKs in the universe and treat missing prices after delisting as a -100% (fraud
   or bankruptcy) or last-price exit, and report both.
3. Buy point-in-time constituent and delisting-return data (e.g. CRSP via a university) if the
   screen is ever used with real money.
