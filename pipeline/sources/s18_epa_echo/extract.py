"""S18 — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

Why everything here is status=IMPUTED, never STRUCTURAL: the cached payload
is a facility-name text match (echo_rest_services.get_facilities,
p_fn/p_fntype=BEGINS), not a verified company join like the CIK/ticker join
S01-S07 use. Confirmed against the live API: a company with only
owned-and-operated sites (Lockheed Martin) gets a plausible facility count;
a company with a franchised/branded retail footprint (Exxon Mobil, Chevron)
pulls in thousands of independently-owned stations that merely license the
brand. STRUCTURAL claims a fact is trustworthy at face value -- this data
is real EPA data through an unverified entity match, which is exactly what
IMPUTED (confidence 0.30) means. See SOURCE.md for the full writeup.

fiscal_year is the year the pull ran (payload["fetched_at"]), not a real
reporting period -- TotalPenalties from get_facilities is EPA's own
cumulative total since ~2000, not an annual figure. This is a real
granularity mismatch with S11 (Violation Tracker), which is per-case,
per-year; do not treat the two as directly comparable without accounting
for it.
"""

from __future__ import annotations

import argparse
import json

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

SOURCE = "S18"


def _parse_usd(s: str | None) -> float:
    """EPA renders totals as '$4,503,965' (or '$0'). Strip to a float."""
    if not s:
        return 0.0
    return float(s.replace("$", "").replace(",", "").strip() or 0.0)


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raw = cache.get_raw(SOURCE, ticker, ".json")
            if raw is None:
                # Never pulled (e.g. limited smoke run). Nothing to say yet --
                # unlike a company we searched and found nothing for, this is
                # a "we haven't looked" gap, not a "we looked" one, so we
                # write nothing rather than fabricate not_disclosed.
                continue

            payload = json.loads(raw)
            fiscal_year = int(payload["fetched_at"][:4])
            result = payload.get("result")

            if result is None or "Error" in result.get("Results", {}):
                # Either the company name was unusable for a safe search, or
                # ECHO rejected both the BEGINS and EXACT queries as too
                # broad. We looked and could not get a number -- that is a
                # real finding, not a silent skip.
                w.write(Observation(
                    ticker=ticker, field="penalty_total_usd", value=None, unit=None,
                    fiscal_year=fiscal_year, period_end=None, quote=None,
                    source=SOURCE, source_url=payload.get("query_url") or "https://echo.epa.gov/tools/web-services",
                    source_section="echo_rest_services.get_facilities",
                    extracted_by="rule:echo_facility_name_match",
                    status=Status.NOT_DISCLOSED,
                ))
                w.write(Observation(
                    ticker=ticker, field="penalty_count", value=None, unit=None,
                    fiscal_year=fiscal_year, period_end=None, quote=None,
                    source=SOURCE, source_url=payload.get("query_url") or "https://echo.epa.gov/tools/web-services",
                    source_section="echo_rest_services.get_facilities",
                    extracted_by="rule:echo_facility_name_match",
                    status=Status.NOT_DISCLOSED,
                ))
                continue

            r = result["Results"]
            penalty_total = _parse_usd(r.get("TotalPenalties"))
            penalty_count = int(r.get("FEARows") or 0) + int(r.get("InfFEARows") or 0)

            w.write(Observation(
                ticker=ticker, field="penalty_total_usd", value=penalty_total, unit="usd",
                fiscal_year=fiscal_year, period_end=None, quote=None,
                source=SOURCE, source_url=payload["query_url"],
                source_section="echo_rest_services.get_facilities:TotalPenalties",
                extracted_by="rule:echo_facility_name_match",
                status=Status.IMPUTED,
            ))
            w.write(Observation(
                ticker=ticker, field="penalty_count", value=penalty_count, unit="count",
                fiscal_year=fiscal_year, period_end=None, quote=None,
                source=SOURCE, source_url=payload["query_url"],
                source_section="echo_rest_services.get_facilities:FEARows+InfFEARows",
                extracted_by="rule:echo_facility_name_match",
                status=Status.IMPUTED,
            ))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S18 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
