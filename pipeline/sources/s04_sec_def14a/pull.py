"""S04 — DEF 14A proxy statements. Network in, HTML to the L1 cache.

Uses the SHARED SEC client (S01-S05 all go through one rate limiter and one
User-Agent). ~500 filings at 8 req/s plus document fetches: a few minutes.

    export SEC_USER_AGENT="ETH Hackathon Team you@example.com"
    python -m pipeline.sources.s04_sec_def14a.pull --limit 10   # smoke first
    python -m pipeline.sources.s04_sec_def14a.pull
"""

from __future__ import annotations

import argparse

from ...common import cache
from ...common.entities import tickers, ticker_to_cik
from ...common.sec_client import get_client

SOURCE = "S04"
FORM = "DEF 14A"


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None,
         verbose: bool = True) -> dict:
    ticker_list = ticker_list or tickers(limit)
    cik_of = ticker_to_cik()
    client = get_client()
    stats = {"requested": len(ticker_list), "cached": 0, "fetched": 0, "none": [], "failed": {}}

    for i, t in enumerate(ticker_list, 1):
        cik = cik_of.get(t)
        if not cik:
            stats["failed"][t] = "no CIK"
            continue
        if cache.has_raw(SOURCE, f"proxy-{t}", ".html"):
            stats["cached"] += 1
            continue
        try:
            filings = client.filing_index(cik, form=FORM, limit=1)
            if not filings:
                # No proxy on file is itself a finding, not an error.
                stats["none"].append(t)
                continue
            html = client.document(filings[0])
            cache.put_raw(SOURCE, f"proxy-{t}", html, ".html")
            cache.put_raw(SOURCE, f"meta-{t}", repr(filings[0]).encode(), ".txt")
            stats["fetched"] += 1
        except Exception as e:                      # noqa: BLE001
            stats["failed"][t] = str(e)[:110]
        if verbose and i % 50 == 0:
            print(f"  {i}/{len(ticker_list)}  fetched={stats['fetched']} "
                  f"cached={stats['cached']} none={len(stats['none'])} "
                  f"failed={len(stats['failed'])}")

    if verbose:
        print(f"[S04] {stats['fetched']} fetched, {stats['cached']} cached, "
              f"{len(stats['none'])} with no DEF 14A, {len(stats['failed'])} failed")
        for t, why in list(stats["failed"].items())[:5]:
            print(f"    {t}: {why}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="S04 pull DEF 14A proxies")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    pull(a.tickers.split(",") if a.tickers else None, limit=a.limit)


if __name__ == "__main__":
    main()
