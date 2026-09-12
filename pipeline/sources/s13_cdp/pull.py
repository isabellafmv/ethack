"""S13 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S13/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database
"""

from __future__ import annotations

import argparse

from ...common import cache
from ...common.entities import tickers

SOURCE = "S13"
ENDPOINT = "https://www.cdp.net/en/data"


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None) -> dict:
    """Fetch raw material for `ticker_list` (default: the whole universe).

    Returns a small dict of counts for the run log.
    """
    ticker_list = ticker_list or tickers(limit)
    raise NotImplementedError(
        "S13 is not cleanly pullable. See SOURCE.md. "
        "Useful bulk data is licence-gated. Free registration exposes some scores. Do NOT build a required indicator on this -- S10 (company sustainability PDFs) is the free substitute."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="S13 pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
