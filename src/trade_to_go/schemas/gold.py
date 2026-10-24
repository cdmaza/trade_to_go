import pandas as pd
import pandera.pandas as pa

DATE = "datetime64[ns]"
UTC = pd.DatetimeTZDtype("ns", "UTC")
POSITIVE = pa.Check.gt(0)

USDMYR_DAILY = pa.DataFrameSchema(
    {
        "date": pa.Column(DATE, unique=True),
        "usdmyr_buy": pa.Column(float, POSITIVE),
        "usdmyr_sell": pa.Column(float, POSITIVE),
        "usdmyr_mid": pa.Column(float, POSITIVE),
    },
    checks=pa.Check(lambda df: df["usdmyr_sell"] >= df["usdmyr_buy"], error="sell < buy"),
    strict=True, coerce=True,
)

KIJANG_DAILY = pa.DataFrameSchema(
    {
        "date": pa.Column(DATE, unique=True),
        "kijang_buy_oz": pa.Column(float, POSITIVE),
        "kijang_sell_oz": pa.Column(float, POSITIVE),
        "kijang_mid_oz": pa.Column(float, POSITIVE),
    },
    checks=pa.Check(lambda df: df["kijang_sell_oz"] >= df["kijang_buy_oz"], error="sell < buy"),
    strict=True, coerce=True,
)

GOLD_USD_DAILY = pa.DataFrameSchema(
    {
        "date": pa.Column(DATE, unique=True),
        "gold_usd_pm": pa.Column(float, pa.Check.in_range(10, 100_000)),
    },
    strict=True, coerce=True,
)

GOLD_USD_MONTHLY_AVG = pa.DataFrameSchema(
    {
        "month": pa.Column(DATE, unique=True),
        "gold_usd_avg": pa.Column(float, pa.Check.in_range(10, 100_000)),
    },
    strict=True, coerce=True,
)

MACRO_DAILY = pa.DataFrameSchema(
    {
        "date": pa.Column(DATE),
        "series": pa.Column(str),
        "value": pa.Column(float),
    },
    unique=["date", "series"],
    strict=True, coerce=True,
)

GOLD_MYR_DAILY = pa.DataFrameSchema(
    {
        "date": pa.Column(DATE, unique=True),
        "gold_usd_oz": pa.Column(float, POSITIVE),
        "usdmyr": pa.Column(float, POSITIVE),
        "gold_myr_oz": pa.Column(float, POSITIVE),
        "gold_myr_g": pa.Column(float, POSITIVE),
        "convention": pa.Column(str, pa.Check.isin(["kl_noon", "same_day"])),
        "available_at": pa.Column(UTC),
    },
    strict=True, coerce=True,
)
