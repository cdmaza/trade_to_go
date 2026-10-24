"""Probabilistic and Deflated Sharpe Ratio (Bailey and Lopez de Prado, 2014).

All Sharpe ratios here are per period (not annualised), as in the paper.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import pandas as pd

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def probabilistic_sharpe(returns: pd.Series, sr_benchmark: float = 0.0) -> float:
    """P(true SR > sr_benchmark) given the sample SR, its length, skew and kurtosis."""
    r = returns.dropna()
    t = len(r)
    if t < 3 or r.std(ddof=1) == 0:
        return float("nan")
    sr = r.mean() / r.std(ddof=1)
    skew = float(r.skew())
    kurt = float(r.kurt()) + 3  # pandas gives excess kurtosis
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    return _N.cdf((sr - sr_benchmark) * math.sqrt(t - 1) / math.sqrt(denom))


def expected_max_sharpe(trial_srs: list[float]) -> float:
    """Expected maximum per-period SR among N independent trials with zero true SR."""
    srs = np.asarray([s for s in trial_srs if np.isfinite(s)])
    n = len(srs)
    if n < 2:
        return 0.0
    sd = srs.std(ddof=1)
    return float(sd * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n) + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n * math.e))))


def deflated_sharpe(returns: pd.Series, trial_srs: list[float]) -> float:
    """PSR against the SR you would expect from the best of the trials by luck alone."""
    return probabilistic_sharpe(returns, expected_max_sharpe(trial_srs))
