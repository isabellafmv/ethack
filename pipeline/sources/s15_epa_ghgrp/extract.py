"""S15 — GHGRP facility data to Observations. NO NETWORK.

EPA-MEASURED Scope 1: the only measured emissions in the whole framework, and
the verified tier of the three-tier verifiability axis. Status is `structural`.

The interpretation rule that must not be broken: **absence from GHGRP is not
zero emissions.** The programme covers US facilities above 25k tCO2e, so a
company with no facilities may be a bank, or may emit entirely abroad. Those
companies are written `not_disclosed`. Writing 0 would hand every software
company a perfect environmental score.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from collections import defaultdict

from ...common import cache
from ...common.entities import match_exact, normalise_name, tickers, universe
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from . import parse
from .pull import ENDPOINT
from .rollup import FacilityRow, rollup

SOURCE = "S15"


def _read_workbook(raw: bytes, engine: str | None = None) -> dict:
    """{sheet_name: DataFrame}, with the real header row found per sheet.

    EPA summary workbooks put three title rows above the header, so a naive
    read names every column 'Unnamed: N'. Renaming columns after the fact is
    worse: the padding cells are all NaN, which produces duplicate column names
    and pandas then silently drops columns. So the header row is located first
    and the sheet re-read with header=<that row>.
    """
    import pandas as pd
    probe = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None,
                          nrows=8, engine=engine)
    out = {}
    for name, head in probe.items():
        hdr = 0
        for i in range(len(head)):
            row = [str(v).strip().lower() for v in head.iloc[i].tolist()]
            if any(v in ("facility id", "ghgrp facility id") for v in row):
                hdr = i
                break
        out[name] = pd.read_excel(io.BytesIO(raw), sheet_name=name,
                                  header=hdr, engine=engine)
    return out


_YEAR_COL = re.compile(r"^(?P<y>\d{4})\s+Total reported direct emissions", re.I)


def _emissions_index() -> dict:
    """{(facility_id, year): tCO2e} from EPA's by-year workbook.

    The file is WIDE — one column per year, 2011..2023 — and split across six
    industry sheets (direct emitters, onshore oil & gas, pipelines, LDC, SF6).
    A parent can own facilities of several types, so every sheet is read and
    the year columns are melted into rows.
    """
    import zipfile
    raw = cache.get_raw(SOURCE, "emissions", ".zip")
    if raw is None:
        for sfx in (".xlsx", ".csv"):
            r = cache.get_raw(SOURCE, "emissions", sfx)
            if r is not None:
                raw = r
                break
        if raw is None:
            return {}
        books = {"": _read_workbook(raw)}
    else:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [i.filename for i in z.infolist() if i.filename.endswith(".xlsx")]
        # Prefer the by-year workbook: it carries every year in one file.
        pick = [n for n in names if "by_year" in n] or names[-1:]
        books = {n: _read_workbook(z.read(n)) for n in pick}

    out: dict = {}
    for sheets in books.values():
        for df in sheets.values():
            cols = {str(c): c for c in df.columns}
            fid_col = next((c for k, c in cols.items()
                            if k.strip().lower() in ("facility id", "ghgrp facility id")), None)
            if fid_col is None:
                continue
            year_cols = {int(_YEAR_COL.match(k).group("y")): c
                         for k, c in cols.items() if _YEAR_COL.match(k)}
            if not year_cols:
                continue
            for rec in df[[fid_col] + list(year_cols.values())].itertuples(index=False):
                fid = str(rec[0]).strip().replace(".0", "")
                if not fid or fid.lower() == "nan":
                    continue
                for (yr, _), val in zip(year_cols.items(), rec[1:]):
                    v = parse.number(val)
                    if v is not None:
                        out[(fid, yr)] = v
    return out


def _parent_rows() -> list[dict]:
    for suffix, engine in ((".xlsb", "pyxlsb"), (".xlsx", None), (".csv", None)):
        raw = cache.get_raw(SOURCE, "parent", suffix)
        if raw is None:
            continue
        if suffix == ".csv":
            return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))))
        rows = []
        # ONE SHEET PER YEAR (2010..2023). Reading only the first would discard
        # every year of history, which is the only trajectory data we have.
        for name, df in _read_workbook(raw, engine).items():
            recs = df.to_dict("records")
            for r in recs:
                r.setdefault("_sheet", name)
            rows.extend(recs)
        return rows
    return []


def _facility_rows() -> tuple[list[FacilityRow], str]:
    parents = _parent_rows()
    if not parents:
        return [], "no parent file cached -- run pull.py first"
    em = _emissions_index()
    if not em:
        return [], ("no facility emissions parsed. The parent file carries no "
                    "emissions column, so EPA's summary workbook is required: "
                    "check cache/raw/S15/ for the data_summary_spreadsheets zip.")

    pc = parse.detect(parents[0].keys())
    problem = parse.report(pc, ["facility_id", "parent_name"])
    if problem:
        return [], problem

    rows: list[FacilityRow] = []
    for r in parents:
        fid = str(r.get(pc["facility_id"]) or "").strip().replace(".0", "")
        pname = str(r.get(pc["parent_name"]) or "").strip()
        if not fid or not pname or pname.lower() == "nan":
            continue
        yr = parse.number(r.get(pc["year"])) if pc.get("year") else None
        if yr is None:
            yr = parse.number(r.get("_sheet"))
        own = parse.number(r.get(pc["ownership"])) if pc.get("ownership") else None
        state = (str(r.get(pc["state"])).strip() if pc.get("state") else None) or None
        years = [int(yr)] if yr else sorted({y for (f, y) in em if f == fid})
        for y in years:
            val = em.get((fid, y))
            if val is None:
                continue
            rows.append(FacilityRow(fid, y, normalise_name(pname), own, val, state))
    return rows, ""


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    rows, err = _facility_rows()
    if err:
        return f"[S15] {err}"

    agg = rollup(rows)
    wanted = set(ticker_list or tickers(limit))
    states = {r["ticker"]: (r.get("headquarters") or "") for r in universe()}

    # parent name -> ticker. Exact normalised match only; a fuzzy match without
    # a constraining context is how 'Delta' becomes an airline.
    matched: dict[str, dict[int, object]] = defaultdict(dict)
    unmatched: set[str] = set()
    for (pname, year), acc in agg.items():
        t = match_exact(pname)
        if t and t in wanted:
            matched[t][year] = acc
        else:
            unmatched.add(pname)

    with ObservationWriter(SOURCE) as w:
        for t in sorted(wanted):
            per_year = matched.get(t, {})
            if not per_year:
                # NOT ZERO. Below the 25k tCO2e threshold, or no US facilities.
                for f, u in (("scope1_tco2e", "tco2e"), ("ghg_facility_count", "count")):
                    w.write(Observation(
                        ticker=t, field=f, value=None, unit=None,
                        fiscal_year=max(y for (_, y) in agg) if agg else 2023,
                        period_end=None, quote=None, source=SOURCE,
                        source_url=ENDPOINT, source_section="no reporting facility",
                        extracted_by="rule:absent_from_ghgrp",
                        status=Status.NOT_DISCLOSED))
                continue

            for year, acc in sorted(per_year.items()):
                w.write(Observation(
                    ticker=t, field="scope1_tco2e", value=round(acc.scope1_tco2e, 1),
                    unit="tco2e", fiscal_year=year, period_end=None, quote=None,
                    source=SOURCE, source_url=ENDPOINT,
                    source_section="GHGRP facility rollup",
                    extracted_by="rule:ghgrp_ownership_weighted"
                                 + ("_partial" if acc.partial else ""),
                    status=Status.STRUCTURAL))
                w.write(Observation(
                    ticker=t, field="ghg_facility_count", value=len(acc.facilities),
                    unit="count", fiscal_year=year, period_end=None, quote=None,
                    source=SOURCE, source_url=ENDPOINT,
                    source_section="GHGRP facility rollup",
                    extracted_by="rule:ghgrp_facility_count",
                    status=Status.STRUCTURAL))

        out = w.summary()

    moved = [t for t, py in matched.items()
             if len({len(a.facilities) for a in py.values()}) > 1]
    return (f"{out}\n  matched {len(matched)}/{len(wanted)} constituents "
            f"(~69 expected — deep, not broad: these carry ~82% of index Scope 1)\n"
            f"  {len(unmatched)} GHGRP parents outside the S&P 500 (expected)\n"
            f"  {len(moved)} companies changed facility count YoY -> EXCLUDE from "
            f"trajectory scoring: {', '.join(sorted(moved)[:10])}")


def main() -> None:
    ap = argparse.ArgumentParser(description="S15 extract")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None, limit=a.limit))


if __name__ == "__main__":
    main()
