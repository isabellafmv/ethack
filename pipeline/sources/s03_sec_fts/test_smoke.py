"""Smoke test for S03: 10 tickers, end to end, cheap.

    python -m pipeline.sources.s03_sec_fts.test_smoke

Run this BEFORE the full 500. A source that fails on 10 fails on 500 slower.
"""

from __future__ import annotations

from ...common.entities import tickers
from .fields import EMITS, SOURCE


def main() -> int:
    sample = tickers(10)
    print(f"{SOURCE}: smoke on {len(sample)} tickers -> {', '.join(sample)}")
    print(f"declared fields: {', '.join(EMITS) or '(none)'}")

    from .pull import pull
    from .extract import extract

    pull(sample)
    print(extract(sample))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
