"""S07 — cached market snapshots to Observations. NO NETWORK.

Market cap is `structural` (a quoted price, not a claim) but it is a SNAPSHOT,
not a fiscal-year figure: period_end carries the date it was taken. Non-USD
raises rather than silently converting -- a foreign currency here means the
lookup matched the wrong listing.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from .pull import ENDPOINT

SOURCE = "S07"


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None,
            asof: str | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)
    stamp = asof or date.today().isoformat()
    missing = []

    with ObservationWriter(SOURCE) as w:
        for t in ticker_list:
            raw = cache.get_raw(SOURCE, f"{t}-{stamp}", ".json")
            if raw is None:
                missing.append(t)
                continue
            d = json.loads(raw)
            cur = (d.get("currency") or "USD").upper()
            fy = int(stamp[:4])

            def rec(field, value, unit):
                if value is None:
                    return Observation(
                        ticker=t, field=field, value=None, unit=None, fiscal_year=fy,
                        period_end=stamp, quote=None, source=SOURCE,
                        source_url=ENDPOINT, source_section="yfinance.get_info",
                        extracted_by="yfinance", status=Status.NOT_DISCLOSED)
                return Observation(
                    ticker=t, field=field, value=float(value), unit=unit,
                    fiscal_year=fy, period_end=stamp, quote=None, source=SOURCE,
                    source_url=ENDPOINT, source_section="yfinance.get_info",
                    extracted_by="yfinance", status=Status.STRUCTURAL)

            if cur != "USD":
                # Do not convert. A non-USD quote means the wrong listing matched.
                w.write(rec("market_cap_usd", None, None))
            else:
                w.write(rec("market_cap_usd", d.get("marketCap"), "usd"))
            w.write(rec("shares_outstanding", d.get("sharesOutstanding"), "count"))

        out = w.summary()
    if missing:
        out += f"\n  {len(missing)} tickers not in the cache for {stamp} -- run pull.py"
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="S07 extract")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    ap.add_argument("--asof", help="cache date to read, default today")
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None, limit=a.limit, asof=a.asof))


if __name__ == "__main__":
    main()
