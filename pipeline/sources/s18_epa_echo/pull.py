"""S18 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S18/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database

One call per ticker to echo_rest_services.get_facilities, filtered by
company name (p_fn/p_fntype=BEGINS). The response is a facility-set SUMMARY
(TotalPenalties, FEARows, InfFEARows, ...), not a list of facilities -- see
SOURCE.md for why that is enough for an IMPUTED-confidence number and not
enough for a STRUCTURAL one.

The API needs no key, but it does reject an over-broad query ("Rows Returned
would be N. Queryset Limit would be exceeded") for very short/generic names.
On that error we retry once with p_fntype=EXACT before giving up -- a real
government API returning noise is not a reason to guess at a fix mid-run.
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

SOURCE = "S18"
ENDPOINT = "https://echodata.epa.gov/echo/echo_rest_services.get_facilities"

#: EPA asks for a real UA with contact info, same convention as sec_client.py.
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "ETH Hackathon Team you@example.com"
)

_session: PoliteSession | None = None


def _get_session() -> PoliteSession:
    global _session
    if _session is None:
        _session = PoliteSession(SOURCE, USER_AGENT, per_second=2.0)
    return _session


def _company_name(ticker: str) -> str | None:
    for row in universe():
        if row["ticker"] == ticker:
            return row["company"]
    return None


def _query(session: PoliteSession, company: str, fntype: str) -> tuple[dict, str]:
    params = {"output": "JSON", "p_fn": company, "p_fntype": fntype}
    url = f"{ENDPOINT}?{urlencode(params)}"
    body = session.get_json(url, key=f"{company}:{fntype}", suffix=".json", use_cache=False)
    return body, url


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None) -> dict:
    """Fetch raw material for `ticker_list` (default: the whole universe).

    Returns a small dict of counts for the run log.
    """
    ticker_list = ticker_list or tickers(limit)
    session = _get_session()

    counts = {"fetched": 0, "cached": 0, "no_company_name": 0, "error": 0}

    for ticker in ticker_list:
        if cache.has_raw(SOURCE, ticker, ".json"):
            counts["cached"] += 1
            continue

        company = _company_name(ticker)
        if not company or len(company.strip()) < 4:
            # Too short/ambiguous to search safely (BEGINS on a 1-3 char name
            # matches almost anything). Record the skip so extract.py can
            # write not_disclosed instead of silently having no file.
            payload = {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "ticker": ticker,
                "company": company,
                "skipped_reason": "no usable company name for a facility-name search",
                "query_url": None,
                "result": None,
            }
            cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
            counts["no_company_name"] += 1
            continue

        body, url = _query(session, company, "BEGINS")
        if "Error" in body.get("Results", {}):
            # Over-broad query -- retry once, narrower.
            body, url = _query(session, company, "EXACT")

        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ticker": ticker,
            "company": company,
            "query_url": url,
            "result": body,
        }
        cache.put_raw(SOURCE, ticker, json.dumps(payload).encode(), ".json")
        if "Error" in body.get("Results", {}):
            counts["error"] += 1
        else:
            counts["fetched"] += 1

    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="S18 pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
