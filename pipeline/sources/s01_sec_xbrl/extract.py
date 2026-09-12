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
#: How many fiscal years to emit per company.
#: 3 was too few: a June or September year-end filer (MSFT, PG, CSCO, INTU...)
#: has FY2024-26 as its latest three, so pinning the analysis to FY2023 — the
#: only year with EPA-measured emissions — silently dropped 26 companies that
#: do have a 2023. 5 also gives trajectory work something to fit.
YEARS = 5
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


ASC606 = "RevenueFromContractWithCustomerExcludingAssessedTax"


def _reconcile_revenue(doc: dict, res: dict) -> dict:
    """Guard for the one case where `Revenues` is not the top line.

    `Revenues` is preferred because contract revenue is a component of it. But a
    handful of filers tag `Revenues` for a segment or a sub-total, leaving it
    SMALLER than the contract-revenue figure. Total revenue can never be less
    than revenue from contracts with customers, so when that happens the
    ordering is wrong for this filer and the larger figure is taken.

    Both values stay in the cache; only the pick changes, and `extracted_by`
    records which concept won.
    """
    asc = _facts_for_tag(doc, ASC606)
    for fy, (tag, fact) in list(res.items()):
        alt = asc.get(fy)
        if tag != ASC606 and alt and alt["val"] > fact["val"]:
            res[fy] = (ASC606, alt)
    return res


def _resolve(doc: dict, chain: list[str]) -> dict[int, tuple[str, dict]]:
    """{fiscal_year: (winning_tag, fact)} — resolved PER YEAR, not once.

    Resolving once per company is subtly wrong and cost us NEE: its `Revenues`
    tag stops in 2012, so a chain that locks onto the first tag with *any* data
    returns nothing for 2023-2025 while a later tag in the chain has them all.
    ASC 606 changed revenue tagging in 2018, so most companies have exactly this
    shape — an old concept and a new one, each covering different years.

    Earlier entries in the chain still win when both cover the same year.
    """
    out: dict[int, tuple[str, dict]] = {}
    for tag in chain:
        for fy, fact in _facts_for_tag(doc, tag).items():
            out.setdefault(fy, (tag, fact))
    return out


def _first_hit(doc: dict, chain: list[str]) -> tuple[str | None, dict[int, dict]]:
    """Back-compat shim for the derived legs. Prefer _resolve for new code."""
    res = _resolve(doc, chain)
    if not res:
        return None, {}
    tag = max((t for t, _ in res.values()),
              key=lambda t: sum(1 for tt, _ in res.values() if tt == t))
    return tag, {fy: f for fy, (t, f) in res.items()}


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)
    cik_of = ticker_to_cik()
    missing_raw: list[str] = []
    no_annual: list[str] = []

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
            chosen: dict[str, dict[int, tuple[str, dict]]] = {}

            for field, chain in TAG_CHAINS.items():
                res = _resolve(doc, chain)
                if field == "revenue_usd":
                    res = _reconcile_revenue(doc, res)
                if res:
                    chosen[field] = res
                    years_seen |= set(res)

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

            if not years:
                # No annual 10-K facts at all -- a recent spin-off or a fresh
                # registration. The company must still appear in the data with
                # every field not_disclosed: a constituent that silently drops
                # out of the universe is failure mode #1, and the manifest
                # would show a coverage gap with no explanation.
                fy0 = date.today().year - 1
                for field in EMITS:
                    w.write(Observation(
                        ticker=t, field=field, value=None, unit=None,
                        fiscal_year=fy0, period_end=None, quote=None, source=SOURCE,
                        source_url=url, source_section=None,
                        extracted_by="xbrl:no_annual_filing", status=Status.NOT_DISCLOSED))
                no_annual.append(t)
                continue

            for fy in years:
                for field in TAG_CHAINS:
                    if field not in EMITS:
                        continue
                    unit = "count" if field == "shares_outstanding" else "usd"
                    hit = chosen.get(field, {}).get(fy)
                    emit(field, fy, hit[1]["val"], hit[0], unit) if hit else absent(field, fy)

                # --- derived: both legs required -------------------------
                # A partial FCF is worse than none: the affordability ratio
                # divides by it, so a half-number becomes a confident wrong answer.
                ocf = _resolve(doc, DERIVED["free_cash_flow_usd"]["operating_cash_flow"])
                capex = _resolve(doc, DERIVED["free_cash_flow_usd"]["minus_capex"])
                if fy in ocf and fy in capex:
                    emit("free_cash_flow_usd", fy,
                         ocf[fy][1]["val"] - capex[fy][1]["val"],
                         f"{ocf[fy][0]}-{capex[fy][0]}")
                else:
                    absent("free_cash_flow_usd", fy)

                ebit = _resolve(doc, DERIVED["ebitda_usd"]["ebit"])
                da = _resolve(doc, DERIVED["ebitda_usd"]["plus_dep_amort"])
                if fy in ebit and fy in da:
                    emit("ebitda_usd", fy, ebit[fy][1]["val"] + da[fy][1]["val"],
                         f"{ebit[fy][0]}+{da[fy][0]}")
                else:
                    absent("ebitda_usd", fy)

        out = w.summary()

    if no_annual:
        out += (f"\n  {len(no_annual)} companies have XBRL but no 10-K "
                f"(spin-off or new registration), recorded as not_disclosed: "
                f"{', '.join(no_annual)}")
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
