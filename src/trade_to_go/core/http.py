"""HTTP session with retries, an honest User-Agent and a per-session rate limit.

Every HTTP source goes through this so fair-access rules (e.g. SEC's 10 req/s)
are enforced in one place.
"""

from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from trade_to_go import __version__

DEFAULT_USER_AGENT = f"trade_to_go/{__version__}"


class Session(requests.Session):
    def __init__(self, *, max_requests_per_s: float | None = None, user_agent: str | None = None,
                 timeout_s: float = 30, retries: int = 3):
        super().__init__()
        self.headers["User-Agent"] = user_agent or DEFAULT_USER_AGENT
        self._min_interval = 1.0 / max_requests_per_s if max_requests_per_s else 0.0
        self._last_request = 0.0
        self._timeout = timeout_s
        retry = Retry(total=retries, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "HEAD"))
        self.mount("https://", HTTPAdapter(max_retries=retry))

    def request(self, method, url, **kwargs):
        wait = self._min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        kwargs.setdefault("timeout", self._timeout)
        try:
            return super().request(method, url, **kwargs)
        finally:
            self._last_request = time.monotonic()
