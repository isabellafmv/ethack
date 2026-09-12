"""DB -> one JSON blob for the browser. Ship it once, score client-side.

What this file must NOT do: compute percentiles, weights or composite scores.
Those are what the sliders move, and percentiles are sector-relative so they go
stale on every filter change. Python round-trips are the only real source of
slider latency; the maths itself is ~10ms in JS.

So we ship harmonised VALUES plus per-observation confidence, and the browser
does percentile + weighted sum per tick. It also means the demo works with the
wifi off, which is the point of rehearsing that way.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict

from .common.entities import sectors, universe
from .common.fields import FIELDS, VALIDATION_ONLY
from .common.paths import DB_PATH, MATRIX_PATH

#: When two sources report the same field, which one the map shows by default.
#: Measured beats reported beats modelled. The others stay in `alternatives`
#: so the say-do gap remains inspectable in the UI.
SOURCE_PRIORITY = ["S15", "S19", "S01", "S04", "S05", "S08", "S09",
                   "S10", "S02", "S03", "S06", "S07", "S11", "S12", "S13",
                   # Derived (a teammate's own matching): real data, but with a
                   # weaker provenance trail than our own extraction, so it
                   # fills gaps rather than overriding a primary pull.
                   "S15~team", "S09~team", "S01~team", "imputed"]


def _rank(src: str) -> int:
    return SOURCE_PRIORITY.index(src) if src in SOURCE_PRIORITY else len(SOURCE_PRIORITY)


def export(db_path=DB_PATH, out=MATRIX_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM observations WHERE status IN "
        "('structural','quote_verified','imputed') ORDER BY fiscal_year DESC"
    ).fetchall()
    conn.close()

    # Intern the repeated strings. source_url is the longest field on every
    # record and there are only a few hundred distinct values across 30k
    # records; storing an index instead keeps the payload inside the budget
    # that makes a wifi-off demo possible.
    urls: dict[str, int] = {}

    def intern(u: str) -> int:
        return urls.setdefault(u or "", len(urls))

    best: dict[tuple[str, str], dict] = {}
    alts: dict[tuple[str, str], list] = defaultdict(list)
    for r in rows:
        if r["field"] in VALIDATION_ONLY:
            continue
        k = (r["ticker"], r["field"])
        rec = {
            "v": r["value_num"] if r["value_num"] is not None else r["value_text"],
            "u": r["unit"], "fy": r["fiscal_year"], "src": r["source"],
            "st": r["status"], "c": r["confidence"],
            "q": r["quote"], "url": intern(r["source_url"]),
        }
        cur = best.get(k)
        if cur is None or (_rank(rec["src"]), -rec["fy"]) < (_rank(cur["src"]), -cur["fy"]):
            if cur is not None:
                alts[k].append(cur)
            best[k] = rec
        else:
            alts[k].append(rec)

    sec = sectors()
    meta = {r["ticker"]: r for r in universe()}
    companies = []
    for t in sorted({k[0] for k in best}):
        vals = {f: best[(t, f)] for (tk, f) in best if tk == t}
        n = len(vals)
        companies.append({
            "ticker": t,
            "name": meta.get(t, {}).get("company", t),
            "sector": sec.get(t, "Unknown"),
            "sub_industry": meta.get(t, {}).get("sub_industry", ""),
            "fields": vals,
            # Alternatives exist so a click can show "EPA says X, the company
            # says Y". Two is enough for that; the quote belongs to the chosen
            # value, and carrying it on every alternative doubled the payload.
            "alternatives": {f: [{k: v for k, v in a.items() if k != "q"}
                                 for a in alts[(t, f)][:2]]
                             for f in vals if alts.get((t, f))},
            # Opacity on the 3D map. A bright point in the good corner with a
            # low number here is claiming to be good without evidence.
            "confidence": round(sum(v["c"] for v in vals.values()) / n, 3) if n else 0.0,
        })

    payload = {
        "schema": {f: {"unit": s.unit, "pillar": s.pillar, "dtype": s.dtype.__name__,
                       "description": s.description}
                   for f, s in FIELDS.items() if f not in VALIDATION_ONLY},
        "source_priority": SOURCE_PRIORITY,
        # index -> url; `url` on each record is a position in this list
        "urls": [u for u, _ in sorted(urls.items(), key=lambda kv: kv[1])],
        "companies": companies,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"wrote {out} -- {len(companies)} companies, {kb:.0f} KB")
    if kb > 2000:
        print("  WARNING: over 2 MB. Trim fields or drop quotes from the payload "
              "and fetch them on click.")
    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(MATRIX_PATH))
    a = ap.parse_args()
    from pathlib import Path
    export(a.db, Path(a.out))
