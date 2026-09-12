"""S01 — cached companyfacts JSON to Observation records. NO NETWORK.

Everything here is `structural`: XBRL is a machine-readable fact with no
sentence to quote. `extracted_by` records WHICH tag in the fallback chain won,
because that choice is a judgement and someone will need to audit it.

A company that files but does not tag a concept is written as `not_disclosed`,
never skipped. Skipping is how a coverage gap becomes invisible.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date

from ...common import cache
from ...common.entities import tickers, ticker_to_cik
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status
from ...common.units import fiscal_year as align_fy

from .fields import EMITS
from .tags import TAG_CHAINS, DERIVED

SOURCE = "S01"
YEARS = 3                    # how many fiscal years back to emit
ANNUAL_MIN, ANNUAL_MAX = 340, 400   # days, to reject quarterly and 2-year facts
FORMS = {"10-K", "10-K/A"}


def _url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def _facts_for_tag(doc: dict, tag: str) -> dict[int, dict]:
    """{fiscal_year: fact} for one us-gaap tag, annual 10-K figures only.

    Later filings win on the same year: a restated figure is the one the company
    now stands behind, and it is what a reader checking the number would find.
    """
    node = doc.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return {}
    out: dict[int, dict] = {}
    for unit, entries in node.get("units", {}).items():
        if unit not in ("USD", "shares"):
            continue
        for e in entries:
            if e.get("form") not in FORMS or not e.get("end"):
                continue
            if e.get("start"):        # duration fact -- must be ~a year
                try:
                    days = (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days
                except ValueError:
                    continue
                if not ANNUAL_MIN <= days <= ANNUAL_MAX:
                    continue
            fy = align_fy(e["end"])
            prev = out.get(fy)
            if prev is None or (e.get("filed", ""), e.get("accn", "")) > (
                    prev.get("filed", ""), prev.get("accn", "")):
                out[fy] = e
    return out


def _first_hit(doc: dict, chain: list[str]) -> tuple[str | None, dict[int, dict]]:
    for tag in chain:
        got = _facts_for_tag(doc, tag)
        if got:
            return tag, got
    return None, {}


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)
    cik_of = ticker_to_cik()
    missing_raw: list[str] = []

    with ObservationWriter(SOURCE) as w:
        for t in ticker_list:
            cik = cik_of.get(t)
            raw = cache.get_raw("SEC", f"facts-{cik}", ".json") if cik else None
            if raw is None:
                missing_raw.append(t)
                continue
            doc = json.loads(raw)
            url = _url(cik)
            years_seen: set[int] = set()
            chosen: dict[str, tuple[str, dict[int, dict]]] = {}

            for field, chain in TAG_CHAINS.items():
                tag, facts = _first_hit(doc, chain)
                if tag:
                    chosen[field] = (tag, facts)
                    years_seen |= set(facts)

            years = sorted(years_seen, reverse=True)[:YEARS]

            def emit(field, fy, value, tag, unit="usd"):
                w.write(Observation(
                    ticker=t, field=field, value=float(value), unit=unit,
                    fiscal_year=fy, period_end=None, quote=None, source=SOURCE,
                    source_url=url, source_section=f"us-gaap:{tag}",
                    extracted_by=f"xbrl:{tag}", status=Status.STRUCTURAL,
                ))

            def absent(field, fy):
                w.write(Observation(
                    ticker=t, field=field, value=None, unit=None, fiscal_year=fy,
                    period_end=None, quote=None, source=SOURCE, source_url=url,
                    source_section=None, extracted_by="xbrl:none_of_chain",
                    status=Status.NOT_DISCLOSED,
                ))

            for fy in years:
                for field in TAG_CHAINS:
                    if field not in EMITS:
                        continue
                    unit = "count" if field == "shares_outstanding" else "usd"
                    tag, facts = chosen.get(field, (None, {}))
                    fact = facts.get(fy)
                    emit(field, fy, fact["val"], tag, unit) if fact else absent(field, fy)

                # --- derived: both legs required -------------------------
                # A partial FCF is worse than none: the affordability ratio
                # divides by it, so a half-number becomes a confident wrong answer.
                ocf_tag, ocf = _first_hit(doc, DERIVED["free_cash_flow_usd"]["operating_cash_flow"])
                capex_tag, capex = _first_hit(doc, DERIVED["free_cash_flow_usd"]["minus_capex"])
                if ocf.get(fy) and capex.get(fy):
                    emit("free_cash_flow_usd", fy,
                         ocf[fy]["val"] - capex[fy]["val"], f"{ocf_tag}-{capex_tag}")
                else:
                    absent("free_cash_flow_usd", fy)

                ebit_tag, ebit = _first_hit(doc, DERIVED["ebitda_usd"]["ebit"])
                da_tag, da = _first_hit(doc, DERIVED["ebitda_usd"]["plus_dep_amort"])
                if ebit.get(fy) and da.get(fy):
                    emit("ebitda_usd", fy, ebit[fy]["val"] + da[fy]["val"],
                         f"{ebit_tag}+{da_tag}")
                else:
                    absent("ebitda_usd", fy)

        out = w.summary()

    if missing_raw:
        out += (f"\n  {len(missing_raw)} companies have no cached filing -- "
                f"run pull.py first ({', '.join(missing_raw[:8])}"
                f"{'...' if len(missing_raw) > 8 else ''})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="S01 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None, limit=a.limit))


if __name__ == "__main__":
    main()
