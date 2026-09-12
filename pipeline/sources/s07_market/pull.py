"""S07 — market cap and shares outstanding via yfinance. Cached on first pull.

yfinance is unofficial and breaks periodically, which is exactly why every
response is written to the L1 cache: the demo must not depend on Yahoo being up
at 9am. Market cap is a SNAPSHOT, so `period_end` carries the pull date.

    pip install yfinance        # or: conda install -c conda-forge yfinance
    python -m pipeline.sources.s07_market.pull
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from ...common import cache
from ...common.entities import tickers, universe

SOURCE = "S07"
ENDPOINT = "https://pypi.org/project/yfinance/"
BATCH = 40


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None,
         verbose: bool = True) -> dict:
    import yfinance as yf

    ticker_list = ticker_list or tickers(limit)
    yahoo = {r["ticker"]: r.get("ticker_yahoo") or r["ticker"] for r in universe()}
    stamp = date.today().isoformat()
    stats = {"requested": len(ticker_list), "cached": 0, "fetched": 0, "empty": []}

    todo = [t for t in ticker_list
            if not cache.has_raw(SOURCE, f"{t}-{stamp}", ".json")]
    stats["cached"] = len(ticker_list) - len(todo)

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        for t in chunk:
            try:
                info = yf.Ticker(yahoo[t]).get_info()
            except Exception as e:                  # noqa: BLE001
                stats["empty"].append(f"{t}: {str(e)[:60]}")
                continue
            if not info or not info.get("marketCap"):
                stats["empty"].append(t)
            cache.put_raw(SOURCE, f"{t}-{stamp}", json.dumps({
                "asof": stamp,
                "marketCap": info.get("marketCap"),
                "sharesOutstanding": info.get("sharesOutstanding"),
                "currency": info.get("currency"),
            }).encode(), ".json")
            stats["fetched"] += 1
        if verbose:
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}")

    if verbose:
        print(f"[S07] {stats['fetched']} fetched, {stats['cached']} cached, "
              f"{len(stats['empty'])} empty")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="S07 pull market data")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    pull(a.tickers.split(",") if a.tickers else None, limit=a.limit)


if __name__ == "__main__":
    main()
