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
                 max_retries: int = 3):
        self.source = source
        self.limiter = RateLimiter(per_second)
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})

    def get(self, url: str, *, key: str | None = None, suffix: str = ".bin",
            use_cache: bool = True, **kw: Any) -> bytes:
        key = key or url
        if use_cache:
            hit = cache.get_raw(self.source, key, suffix)
            if hit is not None:
                return hit

        last: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                r = self.session.get(url, timeout=kw.pop("timeout", DEFAULT_TIMEOUT), **kw)
                if r.status_code == 429 or 500 <= r.status_code < 600:
                    time.sleep(2 ** attempt)
                    last = RuntimeError(f"HTTP {r.status_code} for {url}")
                    continue
                r.raise_for_status()
                cache.put_raw(self.source, key, r.content, suffix)
                return r.content
            except requests.RequestException as e:
                last = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"{self.source}: giving up on {url} after "
                           f"{self.max_retries} attempts") from last

    def get_text(self, url: str, **kw: Any) -> str:
        return self.get(url, **kw).decode("utf-8", errors="replace")

    def get_json(self, url: str, **kw: Any) -> Any:
        import json
        return json.loads(self.get(url, suffix=kw.pop("suffix", ".json"), **kw))
