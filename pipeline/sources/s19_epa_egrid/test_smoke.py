"""Smoke test for S19: 10 tickers, end to end, cheap.

    python -m pipeline.sources.s19_epa_egrid.test_smoke

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

    # S19 is one shared workbook, not a per-ticker fetch -- pull() takes no
    # ticker list, and extract()'s own `limit` (not a ticker filter) just
    # caps how many universe rows get written, for a cheap smoke run.
    pull()
    print(extract(limit=len(sample)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
