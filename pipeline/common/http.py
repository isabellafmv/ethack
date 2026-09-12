"""Generic polite HTTP for non-SEC hosts. SEC goes through sec_client.py.

Everything here writes through the L1 raw cache, so a second call for the same
key costs nothing and works offline.
"""

from __future__ import annotations

import time
import threading
from typing import Any

import requests

from . import cache

DEFAULT_TIMEOUT = 30


class RateLimiter:
    """Thread-safe minimum interval between calls. Shared across a process so
    sixteen source packages running in parallel cannot collectively exceed the
    limit that one of them was written to respect."""

    def __init__(self, per_second: float):
        self.min_interval = 1.0 / per_second
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            self._last = time.monotonic()


class PoliteSession:
    def __init__(self, source: str, user_agent: str, per_second: float = 2.0,
                 max_retries: int = 3, browser_headers: bool = False):
        self.source = source
        self.limiter = RateLimiter(per_second)
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        if browser_headers:
            # Some sites serve the landing page to anything but refuse deeper
            # pages to a client that does not look like a browser.
            self.session.headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;"
                          "q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            })

    def get(self, url: str, *, key: str | None = None, suffix: str = ".bin",
            use_cache: bool = True, **kw: Any) -> bytes:
        key = key or url
        if use_cache:
            hit = cache.get_raw(self.source, key, suffix)
            if hit is not None:
                return hit

        last = "no attempt made"
        timeout = kw.pop("timeout", DEFAULT_TIMEOUT)
        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                r = self.session.get(url, timeout=timeout, **kw)
                if r.status_code in (403, 429) or 500 <= r.status_code < 600:
                    # Respect Retry-After when given; otherwise back off hard.
                    # A 403/429 means we are being throttled, and hammering it
                    # makes the block worse rather than better.
                    wait = float(r.headers.get("Retry-After") or 0) or 5 * (2 ** attempt)
                    last = f"HTTP {r.status_code}"
                    time.sleep(min(wait, 60))
                    continue
                r.raise_for_status()
                cache.put_raw(self.source, key, r.content, suffix)
                return r.content
            except requests.RequestException as e:
                last = f"{type(e).__name__}: {str(e)[:80]}"
                time.sleep(2 ** attempt)
        # Say WHAT went wrong. "giving up" with no status code told us nothing
        # and cost a whole discovery run to diagnose.
        raise RuntimeError(f"{self.source}: {last} after {self.max_retries} "
                           f"attempts on {url}")

    def get_text(self, url: str, **kw: Any) -> str:
        return self.get(url, **kw).decode("utf-8", errors="replace")

    def get_json(self, url: str, **kw: Any) -> Any:
        import json
        return json.loads(self.get(url, suffix=kw.pop("suffix", ".json"), **kw))
