"""S05 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S05/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database

Per ticker: find the most recent 10-K (shared submissions cache -- free if
S01/S02/S03/S04 already warmed it), locate the exhibit typed EX-21.x in that
filing's own document table (NOT filename guessing -- see
common/sec_client.py's filing_documents(), added for this), fetch it, cache
the raw HTML alongside the registrant name from the same submissions call.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from ...common import cache
from ...common.sec_client import get_client
from ...common.entities import tickers, ticker_to_cik

SOURCE = "S05"


def _find_ex21(docs: list[dict]) -> dict | None:
    for d in docs:
        if d.get("type", "").upper().startswith("EX-21"):
            return d
    return None


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None) -> dict:
    """Fetch raw material for `ticker_list` (default: the whole universe).

    Returns a small dict of counts for the run log.
    """
    ticker_list = ticker_list or tickers(limit)
    client = get_client()
    cik_map = ticker_to_cik()

    counts = {"fetched": 0, "cached": 0, "no_cik": 0, "no_10k": 0, "no_ex21": 0}

    for ticker in ticker_list:
        if cache.has_raw(SOURCE, ticker, ".json"):
            counts["cached"] += 1
            continue

        cik = cik_map.get(ticker)
        if not cik:
            payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "ticker": ticker, "cik": None, "legal_name": None,
                       "filing": None, "ex21_html": None,
                       "skipped_reason": "no CIK for this ticker"}
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_cik"] += 1
            continue

        sub = client.submissions(cik)
        legal_name = sub.get("name")

        filings = client.filing_index(cik, form="10-K", limit=1)
        if not filings:
            payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "ticker": ticker, "cik": cik, "legal_name": legal_name,
                       "filing": None, "ex21_html": None,
                       "skipped_reason": "no 10-K on file for this CIK"}
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_10k"] += 1
            continue

        filing = filings[0]
        docs = client.filing_documents(filing)
        ex21 = _find_ex21(docs)

        if ex21 is None:
            payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "ticker": ticker, "cik": cik, "legal_name": legal_name,
                       "filing": filing, "ex21_html": None,
                       "skipped_reason": "no EX-21.x exhibit in the most recent 10-K"}
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_ex21"] += 1
            continue

        html = client.document(filing, doc=ex21["document"]).decode("utf-8", errors="replace")
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ticker": ticker, "cik": cik, "legal_name": legal_name,
            "filing": filing, "ex21_html": html,
        }
        cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
        counts["fetched"] += 1

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="S05 pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
