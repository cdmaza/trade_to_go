# research/

Notebooks for exploration. Rules:

- Read from `data/curated/` (or `data/staging/`) through `trade_to_go.core.storage`.
- Never write into `data/`. Anything worth keeping moves into `src/trade_to_go/` with a test.
- Every backtest configuration you try must go through `backtest.trials` so the
  deflated Sharpe ratio counts it.
