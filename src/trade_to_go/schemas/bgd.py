import pandas as pd
import pandera.pandas as pa

UTC = pd.DatetimeTZDtype("ns", "UTC")

BGD_QUOTES = pa.DataFrameSchema(
    {
        "quoted_at": pa.Column(UTC),                      # Bursa's own timestamp
        "fetched_at": pa.Column(UTC, unique=True),        # when we received it
        "code": pa.Column(str),
        "buy_price": pa.Column(float, pa.Check.gt(0)),    # Bursa buys from you (MYR/g)
        "sell_price": pa.Column(float, pa.Check.gt(0)),   # Bursa sells to you (MYR/g)
        "spread": pa.Column(float, pa.Check.ge(0)),
        "source_file": pa.Column(str),
    },
    strict=True,
    coerce=True,
)
