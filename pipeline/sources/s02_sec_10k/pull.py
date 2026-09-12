"""S02 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S02/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database

SCOPE NOTE: this only fetches the primary 10-K document, for
risk_hitword_density and risk_first_factor_topic (both rule-based, no
agent). energy_cost_usd, clean_capex_usd, green_revenue_share_pct and
target_year need judgment-based prose extraction (the register's own
wording: "classification is OURS, not the company's") -- that is
agent-based extraction, a materially different and larger task, not
attempted here. See SOURCE.md.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from ...common import cache
from ...common.sec_client import get_client
from ...common.entities import tickers, ticker_to_cik

SOURCE = "S02"
ENDPOINT = "https://www.sec.gov/cgi-bin/browse-edgar  /  https://data.sec.gov/submissions/CIK##########.json"


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
            payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "ticker": ticker, "cik": None, "filing": None, "html": None,
                       "skipped_reason": "no CIK for this ticker"}
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_cik"] += 1
            continue

        filings = client.filing_index(cik, form="10-K", limit=1)
        if not filings:
            payload = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "ticker": ticker, "cik": cik, "filing": None, "html": None,
                       "skipped_reason": "no 10-K on file for this CIK"}
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_10k"] += 1
            continue

        filing = filings[0]
        html = client.document(filing).decode("utf-8", errors="replace")
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ticker": ticker, "cik": cik, "filing": filing, "html": html,
        }
        cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
        counts["fetched"] += 1

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="S02 pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
