"""S03 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S03/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database

Full-text search gives hit/no-hit per phrase across a whole filing, not a
count within it or the surrounding sentence -- see SOURCE.md and
common/fields.py for why that makes this a cruder, unweighted cousin of
S02's position-weighted risk_hitword_density, not a replacement for it.

Per ticker: one call to sec_client's shared submissions cache (free if S01/
S02/S04/S05 already warmed it -- same CIK, same cache, "SEC" source) to find
the most recent 10-K, then one EFTS query per hitword, scoped with
startdt=enddt=that filing's date so a hit can only come from THIS filing,
never an older one that happens to share the phrase.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from ...common import cache
from ...common.sec_client import get_client
from ...common.entities import tickers, ticker_to_cik

SOURCE = "S03"
ENDPOINT = "https://efts.sec.gov/LATEST/search-index?q=%22phrase%22&forms=10-K  (JSON behind sec.gov/edgar/search)"

#: A fixed, documented set of Item 1A risk-factor phrases. Not exhaustive,
#: not weighted -- see SOURCE.md for why this is a floor, not the real
#: metric (that's S02, which has the actual text).
HITWORDS = [
    "material weakness",
    "going concern",
    "goodwill impairment",
    "cybersecurity incident",
    "data breach",
    "product recall",
    "supply chain disruption",
    "regulatory investigation",
    "class action",
    "labor shortage",
    "geopolitical conflict",
    "interest rate volatility",
]


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None) -> dict:
    """Fetch raw material for `ticker_list` (default: the whole universe).

    Returns a small dict of counts for the run log.
    """
    ticker_list = ticker_list or tickers(limit)
    client = get_client()
    cik_map = ticker_to_cik()

    counts = {"fetched": 0, "cached": 0, "no_cik": 0, "no_10k": 0}

    for ticker in ticker_list:
        if cache.has_raw(SOURCE, ticker, ".json"):
            counts["cached"] += 1
            continue

        cik = cik_map.get(ticker)
        if not cik:
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticker": ticker, "cik": None, "filing": None,
                "skipped_reason": "no CIK for this ticker in the universe",
                "hits": None,
            }
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_cik"] += 1
            continue

        filings = client.filing_index(cik, form="10-K", limit=1)
        if not filings:
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticker": ticker, "cik": cik, "filing": None,
                "skipped_reason": "no 10-K on file for this CIK",
                "hits": None,
            }
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_10k"] += 1
            continue

        filing = filings[0]
        hits = {}
        for word in HITWORDS:
            url = (
                "https://efts.sec.gov/LATEST/search-index"
                f'?q=%22{word.replace(" ", "+")}%22&forms=10-K&ciks={cik}'
                f'&startdt={filing["filing_date"]}&enddt={filing["filing_date"]}'
            )
            try:
                body = client.session.get_json(url, key=f"{ticker}-{word}", suffix=".json")
                hits[word] = body.get("hits", {}).get("total", {}).get("value", 0)
            except RuntimeError:
                # EFTS returns a persistent 500 for some queries (seen live,
                # not just a transient blip PoliteSession's own retries
                # already absorbed). One bad hitword must not cost the
                # other 11, or the ticker, or the other 499 companies --
                # record it as unknown, not a false zero.
                hits[word] = None

        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ticker": ticker, "cik": cik, "filing": filing,
            "hits": hits,
        }
        cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
        counts["fetched"] += 1

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="S03 pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
