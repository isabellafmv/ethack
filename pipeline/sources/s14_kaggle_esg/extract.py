"""S14 — ESG ratings CSV to Observations. VALIDATION ONLY. NO NETWORK.

Expect modest rank correlation against our own score. The three biggest
DISAGREEMENTS, each explained, are a better demo than any chart -- so the point
of loading this is to find them, not to agree with it.
"""

from __future__ import annotations

import argparse
import csv
import io

from ...common import cache
from ...common.entities import normalise_name, tickers, universe
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from .pull import ENDPOINT

SOURCE = "S14"
TICKER_KEYS = ("Symbol", "Ticker", "ticker", "symbol")
SCORE_KEYS = ("Total ESG Risk score", "Total ESG Risk Score", "totalEsg", "ESG Risk Score")
LEVEL_KEYS = ("ESG Risk Level", "Controversy Level", "controversyLevel")
NAME_KEYS = ("Name", "Company", "company", "Full Name")


def _get(row: dict, keys) -> str | None:
    for k in keys:
        if k in row and str(row[k]).strip() not in ("", "nan", "None"):
            return str(row[k]).strip()
    return None


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    raw = cache.get_raw(SOURCE, "esg_risk_ratings", ".csv")
    if raw is None:
        return "[S14] nothing cached -- run pull.py first"

    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))))
    wanted = set(ticker_list or tickers(limit))
    by_name = {normalise_name(r["company"]): r["ticker"] for r in universe()}

    matched, unmatched = {}, 0
    for r in rows:
        t = _get(r, TICKER_KEYS)
        if not t or t not in wanted:
            # Fall back to name matching, but only within our own universe.
            nm = _get(r, NAME_KEYS)
            t = by_name.get(normalise_name(nm)) if nm else None
            if not t or t not in wanted:
                unmatched += 1
                continue
        matched[t] = r

    with ObservationWriter(SOURCE) as w:
        for t in sorted(wanted):
            r = matched.get(t)
            def rec(field, value, unit):
                if value is None:
                    return Observation(
                        ticker=t, field=field, value=None, unit=None, fiscal_year=2024,
                        period_end=None, quote=None, source=SOURCE, source_url=ENDPOINT,
                        source_section="kaggle csv", extracted_by="rule:csv_column",
                        status=Status.NOT_DISCLOSED)
                return Observation(
                    ticker=t, field=field, value=value, unit=unit, fiscal_year=2024,
                    period_end=None, quote=None, source=SOURCE, source_url=ENDPOINT,
                    source_section="kaggle csv", extracted_by="rule:csv_column",
                    status=Status.STRUCTURAL)

            score = _get(r, SCORE_KEYS) if r else None
            try:
                score = float(score) if score is not None else None
            except ValueError:
                score = None
            w.write(rec("esg_risk_score_external", score, "index" if score is not None else None))
            w.write(rec("esg_controversy_level_external", _get(r, LEVEL_KEYS) if r else None, None))

        out = w.summary()
    return out + (f"\n  {len(matched)}/{len(wanted)} matched; "
                  f"{unmatched} CSV rows outside the universe (expected)")


def main() -> None:
    ap = argparse.ArgumentParser(description="S14 extract")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None, limit=a.limit))


if __name__ == "__main__":
    main()
