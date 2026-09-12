"""S06 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S06/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database

One call per ticker to GLEIF's lei-records search, filtered by legal name.
GLEIF's `filter[entity.legalName]` is NOT an exact match despite the name --
confirmed live: searching "Chevron" without a page size large enough missed
the real "3M COMPANY" / "ABBVIE INC." records entirely, buried among
unrelated same-word entities (pension trusts, foreign subsidiaries, look-
alike names). A generous page size pulls in the full realistic candidate
pool for a distinctive company name; picking the right one out of it is
extract.py's job, offline, via exact name normalisation -- not this file's.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode

from ...common import cache
from ...common.entities import tickers, universe
from ...common.http import PoliteSession

SOURCE = "S06"
ENDPOINT = "https://api.gleif.org/api/v1/lei-records"
PAGE_SIZE = 200

USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "ETH Hackathon Team you@example.com"
)

_session: PoliteSession | None = None


def _get_session() -> PoliteSession:
    global _session
    if _session is None:
        _session = PoliteSession(SOURCE, USER_AGENT, per_second=3.0)
    return _session


def _company_row(ticker: str) -> dict | None:
    for row in universe():
        if row["ticker"] == ticker:
            return row
    return None


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None) -> dict:
    """Fetch raw material for `ticker_list` (default: the whole universe).

    Returns a small dict of counts for the run log.
    """
    ticker_list = ticker_list or tickers(limit)
    session = _get_session()

    counts = {"fetched": 0, "cached": 0, "no_company_name": 0}

    for ticker in ticker_list:
        if cache.has_raw(SOURCE, ticker, ".json"):
            counts["cached"] += 1
            continue

        row = _company_row(ticker)
        company = (row or {}).get("company")
        if not company:
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticker": ticker,
                "company": company,
                "headquarters": (row or {}).get("headquarters"),
                "skipped_reason": "no company name in the universe row",
                "query_url": None,
                "result": None,
            }
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_company_name"] += 1
            continue

        params = {
            "filter[entity.legalName]": company,
            "page[size]": PAGE_SIZE,
        }
        url = f"{ENDPOINT}?{urlencode(params)}"
        body = session.get_json(url, key=ticker, suffix=".json", use_cache=False,
                                 headers={"Accept": "application/vnd.api+json"})

        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ticker": ticker,
            "company": company,
            "headquarters": (row or {}).get("headquarters"),
            "query_url": url,
            "result": body,
        }
        cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
        counts["fetched"] += 1

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="S06 pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
