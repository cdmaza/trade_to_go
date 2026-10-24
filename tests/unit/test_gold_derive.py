import numpy as np
import pandas as pd
import pytest

from trade_to_go.pipelines.gold import TROY_OZ_GRAMS, derive_gold_myr
from trade_to_go.reconcile.gold_myr import tracking_stats

# Mon 2026-03-02 .. Fri 2026-03-06. London is closed on Wed, KL is closed on Thu.
GOLD = pd.DataFrame({
    "date": pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-05", "2026-03-06"]),
    "gold_usd_pm": [100.0, 110.0, 130.0, 140.0],
})
FX = pd.DataFrame({
    "date": pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-06"]),
    "usdmyr_mid": [4.0, 4.1, 4.2, 4.4],
})


def test_kl_noon_uses_previous_london_fix():
    out = derive_gold_myr(GOLD, FX, "kl_noon").set_index("date")
    # Mon has no earlier fix -> dropped. Tue uses Mon fix, Wed uses Tue fix, Fri uses Thu fix.
    assert list(out.index.day) == [3, 4, 6]
    assert out["gold_usd_oz"].tolist() == [100.0, 110.0, 130.0]
    assert out.loc["2026-03-06", "gold_myr_oz"] == pytest.approx(130.0 * 4.4)
    assert out.loc["2026-03-06", "available_at"] == pd.Timestamp("2026-03-06 04:00", tz="UTC")  # 12:00 MYT


def test_same_day_uses_same_day_fix_and_last_known_fx():
    out = derive_gold_myr(GOLD, FX, "same_day").set_index("date")
    assert list(out.index.day) == [2, 3, 5, 6]
    # Thu: KL closed, so Wed's noon rate is the latest known.
    assert out.loc["2026-03-05", "usdmyr"] == 4.2
    assert out.loc["2026-03-05", "gold_myr_g"] == pytest.approx(130.0 * 4.2 / TROY_OZ_GRAMS)
    assert out.loc["2026-03-02", "available_at"] == pd.Timestamp("2026-03-02 15:00", tz="UTC")  # GMT in March


def test_start_filter_and_bad_convention():
    assert derive_gold_myr(GOLD, FX, "same_day", start="2026-03-05")["date"].min() == pd.Timestamp("2026-03-05")
    with pytest.raises(ValueError):
        derive_gold_myr(GOLD, FX, "tomorrow")


def test_tracking_stats_constant_premium_has_zero_te():
    idx = pd.bdate_range("2025-01-01", periods=300)
    derived = pd.Series(np.exp(np.cumsum(np.random.default_rng(0).normal(0, 0.01, len(idx)))) * 100, idx)
    stats = tracking_stats(derived, derived * 1.02)

    assert stats["mean_premium"] == pytest.approx(0.02)
    assert stats["te_daily_ann"] == pytest.approx(0, abs=1e-12)
    assert stats["te_monthly_ann"] == pytest.approx(0, abs=1e-12)
    assert stats["daily_corr"] == pytest.approx(1)


def test_tracking_stats_detects_noise():
    idx = pd.bdate_range("2025-01-01", periods=300)
    rng = np.random.default_rng(1)
    derived = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))) * 100, idx)
    noisy = derived * np.exp(rng.normal(0, 0.005, len(idx)))
    stats = tracking_stats(derived, noisy)
    assert stats["te_daily_ann"] > 0.05
    assert stats["daily_corr"] < 1
