"""Coverage manifest: one row per company x field, with status.

Failure mode #1 in the plan doc is SILENT PARTIAL FAILURE. This is the answer
to it. Chart coverage by sector on our own dashboard and say out loud that
missing data is sectoral, not random -- facility-based sources are structurally
empty for financials, software and services.

    python -m pipeline.manifest            # summary to stdout
    python -m pipeline.manifest --csv      # full grid to data/manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import defaultdict

from .common.entities import sectors, tickers
from .common.fields import FIELDS, VALIDATION_ONLY
from .common.paths import DB_PATH, MANIFEST_PATH


def grid(db_path=DB_PATH) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    have = defaultdict(list)
    for r in conn.execute("SELECT ticker, field, source, status, fiscal_year FROM observations"):
        have[(r["ticker"], r["field"])].append(dict(r))
    conn.close()

    sec = sectors()
    rows = []
    for t in tickers():
        for name in FIELDS:
            if name in VALIDATION_ONLY:
                continue
            recs = have.get((t, name), [])
            best = "missing"
            for pref in ("structural", "quote_verified", "imputed", "not_disclosed", "quote_failed"):
                if any(r["status"] == pref for r in recs):
                    best = pref
                    break
            rows.append({
                "ticker": t, "sector": sec.get(t, "?"), "field": name,
                "pillar": FIELDS[name].pillar, "status": best,
                "n_sources": len({r["source"] for r in recs}),
            })
    return rows


def summarise(rows: list[dict]) -> None:
    by_field = defaultdict(lambda: defaultdict(int))
    by_sector = defaultdict(lambda: defaultdict(int))
    for r in rows:
        by_field[r["field"]][r["status"]] += 1
        by_sector[r["sector"]][r["status"]] += 1

    print(f"\n{'field':<36} {'have':>6} {'imputed':>8} {'n/d':>6} {'missing':>8}")
    print("-" * 68)
    for f in sorted(by_field, key=lambda k: -(by_field[k]['structural'] + by_field[k]['quote_verified'])):
        s = by_field[f]
        have = s["structural"] + s["quote_verified"]
        print(f"{f:<36} {have:>6} {s['imputed']:>8} {s['not_disclosed']:>6} {s['missing']:>8}")

    print(f"\n{'sector':<28} {'coverage':>9}")
    print("-" * 40)
    for sec in sorted(by_sector):
        s = by_sector[sec]
        total = sum(s.values()) or 1
        have = s["structural"] + s["quote_verified"]
        print(f"{sec:<28} {have / total:>8.1%}")
    print("\nCoverage is sectoral, not random. Facility-based sources are "
          "structurally empty for financials, software and services -- that is a\n"
          "property of the world, not a bug in the pipeline. Say it in the pitch.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true", help=f"write {MANIFEST_PATH}")
    args = ap.parse_args()
    rows = grid()
    summarise(rows)
    if args.csv:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST_PATH.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {MANIFEST_PATH} ({len(rows)} rows)")
