"""S01 — SEC XBRL company facts. Network in, raw JSON to the L1 cache.

NO PARSING HERE. One companyfacts document per company, cached forever by CIK.
A second run makes zero network calls, which is what lets extract.py run at
hour 20 with the wifi off.

    export SEC_USER_AGENT="ETH Hackathon Team you@example.com"
    python -m pipeline.sources.s01_sec_xbrl.pull --limit 10   # smoke first
    python -m pipeline.sources.s01_sec_xbrl.pull              # all 500, ~2 min
"""

from __future__ import annotations

import argparse

from ...common import cache
from ...common.entities import tickers, ticker_to_cik
from ...common.sec_client import get_client

SOURCE = "S01"
ENDPOINT = "https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json"


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None,
         verbose: bool = True) -> dict:
    ticker_list = ticker_list or tickers(limit)
    cik_of = ticker_to_cik()
    client = get_client()

    stats = {"requested": len(ticker_list), "cached": 0, "fetched": 0, "failed": {}}
    for i, t in enumerate(ticker_list, 1):
        cik = cik_of.get(t)
        if not cik:
            stats["failed"][t] = "no CIK in the frozen universe"
            continue
        if cache.has_raw("SEC", f"facts-{cik}", ".json"):
            stats["cached"] += 1
            continue
        try:
            client.company_facts(cik)
            stats["fetched"] += 1
        except Exception as e:                      # noqa: BLE001 - one bad
            stats["failed"][t] = str(e)[:120]       # company must not stop 500
        if verbose and i % 50 == 0:
            print(f"  {i}/{len(ticker_list)}  fetched={stats['fetched']} "
                  f"cached={stats['cached']} failed={len(stats['failed'])}")

    if verbose:
        print(f"[S01] {stats['fetched']} fetched, {stats['cached']} already cached, "
              f"{len(stats['failed'])} failed")
        for t, why in list(stats["failed"].items())[:5]:
            print(f"    {t}: {why}")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="S01 pull SEC XBRL company facts")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    pull(a.tickers.split(",") if a.tickers else None, limit=a.limit)


if __name__ == "__main__":
    main()
