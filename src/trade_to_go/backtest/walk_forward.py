"""Walk-forward selection: at the start of each test block, pick the candidate with the
best in-sample Sharpe on an expanding window, then hold it for the block. Only the
stitched out-of-sample positions are evaluated.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd


def walk_forward(candidates: dict[str, pd.Series], score: Callable[[pd.Series, pd.Index], float],
                 min_train: int = 60, test_len: int = 12) -> tuple[pd.Series, list[dict]]:
    """candidates: name -> target position series (same index).
    score(target, train_index) -> in-sample score (higher is better).
    Returns the stitched out-of-sample target and the per-block choices.
    """
    index = next(iter(candidates.values())).index
    oos = pd.Series(float("nan"), index=index)
    choices = []
    for start in range(min_train, len(index), test_len):
        train = index[:start]
        test = index[start:start + test_len]
        scores = {name: score(target, train) for name, target in candidates.items()}
        valid = {k: v for k, v in scores.items() if pd.notna(v)}
        if not valid:
            continue
        best = max(valid, key=valid.get)
        oos.loc[test] = candidates[best].loc[test]
        choices.append({"test_start": test[0].date().isoformat(), "chosen": best,
                        "in_sample_score": round(valid[best], 4)})
    return oos, choices
