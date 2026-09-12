"""Import a teammate's already-matched CSVs into the observations log.

These are real data, matched by hand or by someone else's script, and they are
worth having — but they are NOT our own extractions. So each lands under a
derived source id ("S15~team", not "S15"), which means:

  * it coexists with our own pull at the same primary key rather than
    overwriting it, so the two can be compared;
  * the `disagreements` view will show where the two matchings differ, which is
    a free audit of both;
  * the dashboard prefers our primary extraction and falls back to the derived
    one, so these fill gaps without silently displacing a verified number.

NOT imported: environmental_scores.csv. It holds exactly one distinct value per
GICS sector — the placeholder constants from score_calculation/, not measured
data. Loading it would put fake numbers behind a real-looking score.

    python -m pipeline.import_team
"""

from __future__ import annotations

import argparse
import csv

from .common.jsonl import ObservationWriter
from .common.paths import DATA
from .common.schema import Observation, Status

#: EPA's latest GHGRP reporting year. The teammate's file carries no year
#: column, so this is an assumption — recorded in extracted_by, not hidden.
GHGRP_YEAR = 2023
SBTI_YEAR = 2026

REJECTED = {
    "environmental_scores.csv":
        "one distinct value per sector — these are the placeholder sector "
        "constants from score_calculation/category_score_utils.py, not data",
}


def _num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if s.lower() in ("", "nan", "none", "na", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _rows(name):
    p = DATA / name
    if not p.exists():
        return None
    return list(csv.DictReader(p.open(encoding="utf-8")))


def _mk(source, file, ticker, field, value, unit, fy, section):
    if value is None:
        return Observation(ticker=ticker, field=field, value=None, unit=None,
                           fiscal_year=fy, period_end=None, quote=None,
                           source=source, source_url=f"file://data/{file}",
                           source_section=section, extracted_by=f"team:{file}",
                           status=Status.NOT_DISCLOSED)
    return Observation(ticker=ticker, field=field, value=value, unit=unit,
                       fiscal_year=fy, period_end=None, quote=None, source=source,
                       source_url=f"file://data/{file}", source_section=section,
                       extracted_by=f"team:{file}", status=Status.STRUCTURAL)


def import_ghgrp() -> str:
    f = "epa_ghgrp_company_matches.csv"
    rows = _rows(f)
    if rows is None:
        return f"  {f}: not present, skipped"
    with ObservationWriter("S15~team") as w:
        for r in rows:
            t = r["ticker"]
            em = _num(r.get("ghgrp_emissions_tco2e"))
            # No emissions means absent from GHGRP -- below the 25k threshold or
            # no US facilities. NOT zero. A facility count of 0 alongside a blank
            # emissions figure is the same statement, so it is not recorded as a
            # measured zero either.
            w.write(_mk("S15~team", f, t, "scope1_tco2e", em, "tco2e" if em else None,
                        GHGRP_YEAR, "ghgrp_emissions_tco2e"))
            fc = _num(r.get("ghgrp_facility_count"))
            w.write(_mk("S15~team", f, t, "ghg_facility_count",
                        int(fc) if em is not None and fc is not None else None,
                        "count" if em is not None and fc is not None else None,
                        GHGRP_YEAR, "ghgrp_facility_count"))
        return w.summary()


def import_sbti() -> str:
    f = "sbti_matches.csv"
    rows = _rows(f)
    if rows is None:
        return f"  {f}: not present, skipped"
    with ObservationWriter("S09~team") as w:
        for r in rows:
            t = r["ticker"]
            nt = (r.get("near_term_status") or "").strip().lower()
            nz_year = _num(r.get("net_zero_year"))
            validated = nt == "targets set"
            w.write(_mk("S09~team", f, t, "sbti_target_validated", validated, None,
                        SBTI_YEAR, "near_term_status"))
            kind = ("near-term" if validated else
                    "commitment" if nt in ("committed", "commitment removed") else
                    "net-zero" if nz_year else None)
            w.write(_mk("S09~team", f, t, "sbti_target_type", kind, None,
                        SBTI_YEAR, "near_term_status"))
            ty = _num(r.get("near_term_target_year")) or nz_year
            w.write(_mk("S09~team", f, t, "target_year",
                        int(ty) if ty else None, "year" if ty else None,
                        SBTI_YEAR, "near_term_target_year"))
        return w.summary()


def import_financials() -> str:
    f = "company_financials.csv"
    rows = _rows(f)
    if rows is None:
        return f"  {f}: not present, skipped"
    with ObservationWriter("S01~team") as w:
        for r in rows:
            t = r["ticker"]
            fy = _num(r.get("fiscal_year"))
            if not fy:
                continue        # no year = no primary key; nothing to compare to
            fy = int(fy)
            for field, col in (("revenue_usd", "revenue_usd"),
                               ("ebit_usd", "operating_income_usd"),
                               ("ebitda_usd", "ebitda_proxy_usd")):
                v = _num(r.get(col))
                w.write(_mk("S01~team", f, t, field, v, "usd" if v else None, fy, col))
        return w.summary()


def main() -> None:
    argparse.ArgumentParser(description="import teammate CSVs").parse_args()
    print("importing teammate files as DERIVED sources (origin~team)\n")
    for fn in (import_ghgrp, import_sbti, import_financials):
        print(fn())
    print("\nnot imported:")
    for name, why in REJECTED.items():
        print(f"  {name}\n    {why}")


if __name__ == "__main__":
    main()
