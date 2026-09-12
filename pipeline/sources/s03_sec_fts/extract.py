"""S03 — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

risk_hitword_density here is (# hitwords with >=1 hit) / (# hitwords
checked) for the single most recent 10-K -- unweighted, no position
information, no negation handling (a hitword inside "we do not expect a
going concern issue" counts the same as a genuine warning). This is
declared honestly in SOURCE.md as a floor, not the real signal; S02's
version of this field reads the actual text and should be preferred
wherever both exist.
"""

from __future__ import annotations

import argparse
import json

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from .pull import HITWORDS

SOURCE = "S03"


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raw = cache.get_raw(SOURCE, ticker, ".json")
            if raw is None:
                continue

            payload = json.loads(raw)
            filing = payload.get("filing")
            hits = payload.get("hits")

            if filing is None or hits is None:
                # No CIK, or no 10-K on file. A real finding for a source
                # that is supposed to cover 500/500 -- not a silent skip.
                w.write(Observation(
                    ticker=ticker, field="risk_hitword_density", value=None, unit=None,
                    fiscal_year=0, period_end=None, quote=None,
                    source=SOURCE, source_url="https://www.sec.gov/edgar/search/",
                    source_section="efts full-text search",
                    extracted_by="rule:sec_fts_hitword_count",
                    status=Status.NOT_DISCLOSED,
                ))
                continue

            # A word whose query hit a persistent EFTS 500 is recorded as
            # None (unknown), not 0 (checked, absent) -- density is over
            # the words actually resolved, not silently deflated by ones
            # we couldn't check.
            resolved = {w: v for w, v in hits.items() if v is not None}
            if not resolved:
                w.write(Observation(
                    ticker=ticker, field="risk_hitword_density", value=None, unit=None,
                    fiscal_year=0, period_end=None, quote=None,
                    source=SOURCE, source_url="https://www.sec.gov/edgar/search/",
                    source_section="efts full-text search",
                    extracted_by="rule:sec_fts_hitword_count",
                    status=Status.NOT_DISCLOSED,
                ))
                continue

            report_date = filing.get("report_date") or filing.get("filing_date")
            fiscal_year = int(report_date[:4])
            density = sum(1 for v in resolved.values() if v > 0) / len(resolved)
            partial = len(resolved) < len(HITWORDS)

            acc = filing["accession"]
            source_url = (
                f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                f"&CIK={filing['cik']}&type=10-K"
            )
            w.write(Observation(
                ticker=ticker, field="risk_hitword_density", value=density, unit="index",
                fiscal_year=fiscal_year, period_end=filing.get("report_date"), quote=None,
                source=SOURCE, source_url=source_url,
                source_section=f"efts full-text search:{acc}"
                               + (f" ({len(resolved)}/{len(HITWORDS)} words resolved)" if partial else ""),
                extracted_by="rule:sec_fts_hitword_count" + ("_partial" if partial else ""),
                status=Status.STRUCTURAL,
            ))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S03 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
