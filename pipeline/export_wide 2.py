"""One row per company, one column per field. The eyeball view.

The observations table is deliberately long and thin (one row per claim, so
that a measured and a reported value of the same number can coexist). That
shape is right for the framework and wrong for a human scanning for holes, so
this pivots it.

    python -m pipeline.export_wide                 # data/wide.csv
    python -m pipeline.export_wide --status        # + data/wide_status.csv
    python -m pipeline.export_wide --year 2024     # pin the fiscal year

Where two sources report the same field, the same precedence as the dashboard
applies: measured beats reported beats modelled (see SOURCE_PRIORITY). A blank
cell means no value of any status; `not_disclosed` shows in the status file.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import defaultdict

from .common.entities import universe
from .common.fields import FIELDS, VALIDATION_ONLY
from .common.paths import DATA, DB_PATH
from .export_matrix import _rank

TRUSTED = ("structural", "quote_verified", "imputed")
META = ["ticker", "company", "sector", "sub_industry"]


def collect(db_path=DB_PATH, year: int | None = None, fallback: bool = False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT ticker, field, source, fiscal_year, value_num, value_text, unit, "
        "status FROM observations").fetchall()
    if year and not fallback:
        # Strict: constrain ANNUAL FLOWS to the pinned year. Snapshots and
        # timeless attributes pass through — they have no period to mismatch,
        # and dropping them would lose market cap and every target field.
        keep = []
        for r in rows:
            spec = FIELDS.get(r["field"])
            if spec is None or spec.timeless or spec.snapshot:
                keep.append(r)
            elif r["fiscal_year"] == int(year):
                keep.append(r)
        rows = keep
    conn.close()

    best: dict[tuple[str, str], dict] = {}
    for r in rows:
        k = (r["ticker"], r["field"])
        cand = dict(r)
        cur = best.get(k)
        # Prefer: a trusted value over a blank; then source precedence; then
        # the most recent fiscal year.
        def score(x):
            # With --fallback, an exact hit on the pinned year outranks a newer
            # one, so a flow only drops to another year when the pinned year has
            # nothing. The year it actually came from is then written out
            # per cell, because an unlabelled fallback is just a mixed column.
            exact = 1 if (year and x["fiscal_year"] == int(year)) else 0
            return (x["status"] in TRUSTED, exact, -_rank(x["source"]),
                    x["fiscal_year"])
        if cur is None or score(cand) > score(cur):
            best[k] = cand
    return best


PILLAR_NAMES = {
    "P1": "Environmental & Resource Efficiency",
    "P2": "Transition & Structural Risk",
    "P3": "Governance & Capital Stewardship",
    "X":  "Cross-cutting (identity, market, validation)",
}


def _write(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def export_by_pillar(db_path=DB_PATH, year: int | None = None,
                     all_fields: bool = False) -> list:
    """One CSV per pillar. Same rows, only that pillar's columns.

    The meta columns (ticker, company, sector, sub_industry) repeat in every
    file on purpose -- a pillar file you cannot join or read on its own is not
    much use to whoever is scoring that pillar.
    """
    best = collect(db_path, year)
    meta = {r["ticker"]: r for r in universe()}
    written = []

    for pillar, label in PILLAR_NAMES.items():
        cols = [f for f in FIELDS if FIELDS[f].pillar == pillar]
        present = cols if all_fields else [
            c for c in cols if any((t, c) in best for t in meta)]
        if not present:
            print(f"  {pillar}  no data yet — skipped "
                  f"({len(cols)} fields defined, none pulled)")
            continue

        rows, filled = [], 0
        for t, m in sorted(meta.items()):
            row = [t, m.get("company", ""), m.get("sector", ""), m.get("sub_industry", "")]
            for f in present:
                rec = best.get((t, f))
                if rec and rec["status"] in TRUSTED:
                    row.append(rec["value_num"] if rec["value_num"] is not None
                               else rec["value_text"])
                    filled += 1
                else:
                    row.append("")
            rows.append(row)

        tag = f"_FY{year}" if year else ""
        path = _write(DATA / f"wide{tag}_{pillar}.csv", META + present, rows)
        empty = [c for c in cols if c not in present]
        print(f"  {pillar}  {path.name:<14} {len(present):>2} of {len(cols):>2} fields, "
              f"{filled / (len(meta) * len(present)):>4.0%} filled   {label}")
        if empty:
            print(f"        still empty: {', '.join(empty)}")
        written.append(path)
    return written


def year_spread(best, meta) -> dict:
    """Which fiscal years the chosen cells actually came from."""
    from collections import Counter
    c = Counter(r["fiscal_year"] for (t, f), r in best.items()
                if r["fiscal_year"] and r["status"] in TRUSTED)
    return dict(c.most_common())


def export(db_path=DB_PATH, year: int | None = None, with_status: bool = False,
           fallback: bool = False):
    best = collect(db_path, year, fallback)
    meta = {r["ticker"]: r for r in universe()}
    # VALIDATION_ONLY fields are the external ESG ratings we are trying to
    # BEAT. They must never sit in a table someone might build a score from,
    # so they go to their own file and nowhere near the scoring columns.
    fields = [f for f in FIELDS if f not in VALIDATION_ONLY]
    present = [f for f in fields if any((t, f) in best for t in meta)]

    tag = f"_FY{year}" if year else ""
    if year and fallback:
        tag += "_fallback"
    # Only FLOW fields get a year column: snapshots are true as of a date, not
    # for a period, so they are not part of the alignment question.
    flows = [f for f in present
             if not (FIELDS[f].snapshot or FIELDS[f].timeless)]
    header = list(META)
    for f in present:
        header.append(f)
        if f in flows:
            header.append(f"{f}_fy")
    if year and fallback:
        header.append("flows_all_target_year")

    out = DATA / f"wide{tag}.csv"
    n_vals = 0
    off = 0
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for t, m in sorted(meta.items()):
            row = [t, m.get("company", ""), m.get("sector", ""), m.get("sub_industry", "")]
            aligned = True
            for f in present:
                rec = best.get((t, f))
                ok = rec and rec["status"] in TRUSTED
                if ok:
                    row.append(rec["value_num"] if rec["value_num"] is not None
                               else rec["value_text"])
                    n_vals += 1
                else:
                    row.append("")
                if f in flows:
                    fy = rec["fiscal_year"] if ok else ""
                    row.append(fy)
                    if ok and year and fy != int(year):
                        aligned = False
                        off += 1
            if year and fallback:
                row.append(aligned)
            w.writerow(row)
    print(f"wrote {out}  —  {len(meta)} companies x {len(present)} fields, "
          f"{n_vals} values ({n_vals / (len(meta) * len(present)):.0%} filled)")
    if year and fallback:
        print(f"  every flow column is followed by <field>_fy holding the year it "
              f"actually came from.\n  {off} flow cells fell back off FY{year}; "
              f"`flows_all_target_year` is False for those rows.")

    # A fiscal year per cell, always. Without it a mixed-year table looks
    # identical to an aligned one, and nothing downstream can tell them apart.
    yp = DATA / f"wide{tag}_year.csv"
    with yp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(META + present)
        for t, m in sorted(meta.items()):
            row = [t, m.get("company", ""), m.get("sector", ""), m.get("sub_industry", "")]
            for f in present:
                rec = best.get((t, f))
                row.append(rec["fiscal_year"] if rec and rec["status"] in TRUSTED else "")
            w.writerow(row)
    print(f"wrote {yp}  —  the fiscal year behind every cell")

    if year is None:
        spread = year_spread(best, meta)
        real = {y: n for y, n in spread.items() if y}
        if len(real) > 1:
            top = sorted(real.items(), key=lambda kv: -kv[1])[:5]
            print("\n  ** MIXED FISCAL YEARS **  cells come from: "
                  + ", ".join(f"FY{y}={n}" for y, n in top))
            print("  Companies with June/September year-ends sit a full year ahead of\n"
                  "  calendar filers, so a ranking across this column compares different\n"
                  "  periods. Pin a year for anything you rank or divide:\n"
                  "      python -m pipeline.export_wide --year 2025")

    vfields = [f for f in VALIDATION_ONLY if any((t, f) in best for t in meta)]
    if vfields:
        vp = DATA / "validation_external_ratings.csv"
        with vp.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(META + vfields)
            for t, m in sorted(meta.items()):
                row = [t, m.get("company", ""), m.get("sector", ""),
                       m.get("sub_industry", "")]
                for f in vfields:
                    rec = best.get((t, f))
                    row.append((rec["value_num"] if rec["value_num"] is not None
                                else rec["value_text"])
                               if rec and rec["status"] in TRUSTED else "")
                w.writerow(row)
        print(f"wrote {vp}  —  VALIDATION ONLY. Never an input to a score; "
              f"this is the benchmark we compare against.")

    if with_status:
        sp = DATA / f"wide{tag}_status.csv"
        with sp.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(META + present)
            for t, m in sorted(meta.items()):
                row = [t, m.get("company", ""), m.get("sector", ""), m.get("sub_industry", "")]
                for f in present:
                    rec = best.get((t, f))
                    row.append(rec["status"] if rec else "missing")
                w.writerow(row)
        print(f"wrote {sp}  —  same shape, statuses instead of values")

    # what is in the file, and what is not
    print(f"\n{'field':<30} {'filled':>7}  {'unit':<16} pillar")
    print("-" * 68)
    for f in present:
        n = sum(1 for t in meta if best.get((t, f), {}).get("status") in TRUSTED)
        print(f"  {f:<28} {n:>5}/{len(meta)}  {str(FIELDS[f].unit or '—'):<16} {FIELDS[f].pillar}")
    absent = [f for f in fields if f not in present]
    if absent:
        print(f"\nnot yet pulled ({len(absent)}): {', '.join(absent)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="pivot observations to one row per company")
    ap.add_argument("--year", type=int, help="pin a fiscal year; default is latest per company")
    ap.add_argument("--status", action="store_true", help="also write wide_status.csv")
    ap.add_argument("--by-pillar", action="store_true",
                    help="also write wide_P1/P2/P3/X.csv, one per pillar")
    ap.add_argument("--all-fields", action="store_true",
                    help="with --by-pillar, keep columns that have no data yet")
    ap.add_argument("--fallback", action="store_true",
                    help="with --year: prefer that year, fall back to the latest "
                         "available and label which is which")
    ap.add_argument("--db", default=str(DB_PATH))
    a = ap.parse_args()
    export(a.db, a.year, a.status, a.fallback)
    if a.by_pillar:
        print("\nper-pillar files")
        export_by_pillar(a.db, a.year, a.all_fields)


if __name__ == "__main__":
    main()
