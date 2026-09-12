"""S09 — SBTi export to Observations. NO NETWORK.

Structural: a spreadsheet cell is a machine-readable fact, not a prose claim.

Two things this deliberately does NOT do:

  * It does not invent a counterfactual target for companies SBTi has never
    heard of. A company with no entry is written `not_disclosed`. The
    sector-median counterfactual is a separate imputation pass writing
    source='imputed', so that "what SBTi says" and "what we assumed" never
    share a row. Nulls reward silence, but so does quietly modelling over them.
  * It does not treat a COMMITMENT as a TARGET. SBTi lists companies that have
    merely committed to set a target alongside those whose targets are
    validated; conflating them is the easiest way to flatter a company here.
"""

from __future__ import annotations

import argparse
import csv
import io
from datetime import date

from ...common import cache
from ...common.entities import normalise_name, tickers, universe
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from . import parse
from .pull import ENDPOINT

SOURCE = "S09"
US = ("united states", "usa", "u.s.", "us")


def _rows() -> list[dict]:
    for suffix in (".xlsx", ".csv", ".xls"):
        raw = cache.get_raw(SOURCE, "sbti_export", suffix)
        if raw is None:
            continue
        if suffix == ".csv":
            return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))))
        import pandas as pd
        df = pd.read_excel(io.BytesIO(raw))
        return df.to_dict("records")
    return []


def _index() -> dict[str, str]:
    return {normalise_name(r["company"]): r["ticker"] for r in universe()}


def _pick(rows: list[dict], cell) -> dict:
    """Which row represents the company's target, when it has several.

    Preference, in order, and each half of it is a judgement worth defending:

      1. A VALIDATED target beats a commitment. Obvious.
      2. A NEAR-TERM target beats a net-zero one.

    (2) is the one that matters. Net-zero targets are typically 2050; near-term
    are typically 2030. Feeding a 2050 horizon into the affordability ratio
    divides the same abatement bill over 26 years instead of 5, so almost every
    company looks able to pay. The near-term target is also what the company is
    actually on the hook for this decade. Using it is the conservative choice
    and the honest one.

    The net-zero row is not lost -- it is still in the JSONL, and the near-term
    pick is recorded in `extracted_by`, so switching the rule later is a
    re-extract, not a re-pull.
    """
    def rank(r):
        validated = (parse.is_validated(cell(r, "action"), cell(r, "target_type"))
                     or parse.is_validated(cell(r, "nt_status"), None)
                     or parse.is_validated(cell(r, "nz_status"), None))
        near = parse.year(cell(r, "nt_year")) is not None
        return (validated, near)
    return max(rows, key=rank)


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None,
            vintage: int | None = None) -> str:
    rows = _rows()
    if not rows:
        return "[S09] nothing cached -- run pull.py first"

    cols = parse.detect(list(rows[0].keys()))
    if not cols.get("company"):
        return (f"[S09] could not find a company-name column in "
                f"{list(rows[0].keys())[:8]} -- update COLUMNS in parse.py")

    fy = vintage or date.today().year
    wanted = set(ticker_list or tickers(limit))
    by_name = _index()

    def cell(r, key):
        c = cols.get(key)
        if not c:
            return None
        v = r.get(c)
        return None if v is None or str(v).strip().lower() in ("", "nan", "none") else v

    # One company can appear several times (near-term and net-zero rows). Keep
    # them all and prefer a validated row over a commitment.
    hits: dict[str, list[dict]] = {}
    off_universe = 0
    for r in rows:
        country = str(cell(r, "country") or "").lower()
        if country and not any(u in country for u in US):
            continue                        # S&P 500 is US-listed; narrow first
        t = by_name.get(normalise_name(str(cell(r, "company") or "")))
        if not t or t not in wanted:
            off_universe += 1
            continue
        hits.setdefault(t, []).append(r)

    with ObservationWriter(SOURCE) as w:
        for t in sorted(wanted):
            rs = hits.get(t, [])

            def obs(field, value, unit, section, by):
                if value is None:
                    return Observation(
                        ticker=t, field=field, value=None, unit=None, fiscal_year=fy,
                        period_end=None, quote=None, source=SOURCE, source_url=ENDPOINT,
                        source_section=section, extracted_by=by,
                        status=Status.NOT_DISCLOSED)
                return Observation(
                    ticker=t, field=field, value=value, unit=unit, fiscal_year=fy,
                    period_end=None, quote=None, source=SOURCE, source_url=ENDPOINT,
                    source_section=section, extracted_by=by, status=Status.STRUCTURAL)

            if not rs:
                # Absent from SBTi entirely. That is a finding: no validated
                # target, publicly, as of this export.
                w.write(obs("sbti_target_validated", False, None,
                            "not listed", "rule:absent_from_sbti_export"))
                for f, u in (("sbti_target_type", None), ("target_year", "year"),
                             ("target_baseline_year", "year"),
                             ("target_reduction_pct", "pct"),
                             ("target_scope_coverage", None)):
                    w.write(obs(f, None, u, "not listed", "rule:absent_from_sbti_export"))
                continue

            best = _pick(rs, cell)
            action, ttype = cell(best, "action"), cell(best, "target_type")
            kind, tyear = parse.classify(
                cell(best, "nt_status"), cell(best, "nt_year"),
                cell(best, "nz_status"), cell(best, "nz_year"), action, ttype)
            validated = (parse.is_validated(action, ttype)
                         or parse.is_validated(cell(best, "nt_status"), None)
                         or parse.is_validated(cell(best, "nz_status"), None))

            w.write(obs("sbti_target_validated", bool(validated), None,
                        cols.get("nt_status") or cols.get("action"),
                        "rule:sbti_target_status"))
            w.write(obs("sbti_target_type", kind, None,
                        cols.get("nt_status") or cols.get("target_type"),
                        "rule:sbti_near_term_preferred"))
            lang_pre = cell(best, "language")
            parsed_pre = parse.parse_target_language(lang_pre) if lang_pre else None
            if tyear is None and parsed_pre and parsed_pre.get("target_year"):
                # The structured column is blank but SBTi's own sentence states
                # the year. Prefer the structured value where it exists; this
                # fallback at least arrives with a quote attached.
                w.write(Observation(
                    ticker=t, field="target_year", value=parsed_pre["target_year"],
                    unit="year", fiscal_year=fy, period_end=None,
                    quote=parsed_pre["quote"], source=SOURCE, source_url=ENDPOINT,
                    source_section=cols.get("language"),
                    extracted_by="rule:sbti_target_language",
                    status=Status.QUOTE_VERIFIED), source_text=str(lang_pre))
            else:
                w.write(obs("target_year", tyear, "year",
                            cols.get("nt_year") or cols.get("target_year"),
                            "rule:sbti_near_term_preferred"))
            # --- target wording: the only quote-verifiable path in this source
            # SBTi writes the target as a sentence. Parsing that instead of a
            # spreadsheet cell means the number arrives WITH the sentence it
            # came from, validated as a character-for-character substring.
            lang = cell(best, "language")
            parsed = parse.parse_target_language(lang) if lang else None
            src_text = str(lang) if lang else None

            def quoted(field, value, unit, by):
                if value is None:
                    return obs(field, None, unit, cols.get("language"), by)
                return Observation(
                    ticker=t, field=field, value=value, unit=unit, fiscal_year=fy,
                    period_end=None, quote=parsed["quote"], source=SOURCE,
                    source_url=ENDPOINT, source_section=cols.get("language"),
                    extracted_by=by, status=Status.QUOTE_VERIFIED)

            if parsed:
                w.write(quoted("target_reduction_pct", parsed["target_reduction_pct"],
                               "pct", "rule:sbti_target_language"), source_text=src_text)
                w.write(quoted("target_baseline_year", parsed["target_baseline_year"],
                               "year" if parsed["target_baseline_year"] else None,
                               "rule:sbti_target_language"), source_text=src_text)
                w.write(quoted("target_scope_coverage", parsed["target_scope_coverage"],
                               None, "rule:sbti_target_language"), source_text=src_text)
            else:
                sc = cell(best, "nt_scope") or cell(best, "scope")
                w.write(obs("target_reduction_pct",
                            parse.percent(cell(best, "reduction")), "pct",
                            cols.get("reduction"), "rule:sbti_reduction_pct"))
                w.write(obs("target_baseline_year", parse.year(cell(best, "base_year")),
                            "year", cols.get("base_year"), "rule:sbti_base_year"))
                w.write(obs("target_scope_coverage", str(sc) if sc else None, None,
                            cols.get("nt_scope") or cols.get("scope"), "rule:sbti_scope"))

        out = w.summary()

    return (f"{out}\n  matched {len(hits)}/{len(wanted)} constituents; "
            f"{off_universe} export rows outside the S&P 500 (expected — SBTi is global)\n"
            f"  columns used: "
            f"{ {k: v for k, v in cols.items() if v} }")


def main() -> None:
    ap = argparse.ArgumentParser(description="S09 extract")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    ap.add_argument("--vintage", type=int, help="year of the export, default this year")
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None,
                  limit=a.limit, vintage=a.vintage))


if __name__ == "__main__":
    main()
