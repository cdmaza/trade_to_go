import pandera.pandas as pa

EQUITY_PRICES_DAILY = pa.DataFrameSchema(
    {
        "date": pa.Column("datetime64[ns]"),
        "symbol": pa.Column(str),
        "close": pa.Column(float, pa.Check.gt(0)),
        "adj_close": pa.Column(float, pa.Check.gt(0)),
        "volume": pa.Column(float, pa.Check.ge(0)),
        "source": pa.Column(str, pa.Check.isin(["tiingo", "moomoo"])),
    },
    unique=["date", "symbol"],
    strict=True, coerce=True,
)

FUNDAMENTALS_FACTS = pa.DataFrameSchema(
    {
        "cik": pa.Column(int),
        "field": pa.Column(str),
        "concept": pa.Column(str),
        "unit": pa.Column(str),
        "start": pa.Column("datetime64[ns]", nullable=True),
        "end": pa.Column("datetime64[ns]"),
        "val": pa.Column(float),
        "fy": pa.Column(float, nullable=True),
        "fp": pa.Column(str, nullable=True),
        "form": pa.Column(str, nullable=True),
        "filed": pa.Column("datetime64[ns]"),
        "accn": pa.Column(str, nullable=True),
    },
    strict=True, coerce=True,
)
