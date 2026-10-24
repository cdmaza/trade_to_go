"""Trading-day calendars.

XKLS is Bursa Malaysia, XNYS is the NYSE. LBMA auctions follow London business
days; XLON (London Stock Exchange) is used as the closest available proxy.
"""

from __future__ import annotations

from functools import cache

import exchange_calendars as xcals
import pandas as pd

BURSA = "XKLS"
NYSE = "XNYS"
LONDON = "XLON"


@cache
def get_calendar(code: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(code)


def sessions(code: str, start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    return get_calendar(code).sessions_in_range(start, end)


def is_session(code: str, date: str | pd.Timestamp) -> bool:
    return get_calendar(code).is_session(pd.Timestamp(date).normalize())
