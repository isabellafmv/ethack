"""DB -> one JSON blob for the browser. Ship it once, score client-side.

What this file must NOT do: compute percentiles, weights or composite scores.
Those are what the sliders move, and percentiles are sector-relative so they go
stale on every filter change. Python round-trips are the only real source of
slider latency; the maths itself is ~10ms in JS.

So we ship harmonised VALUES plus per-observation confidence, and the browser
does percentile + weighted sum per tick. It also means the demo works with the
wifi off, which is the point of rehearsing that way.

Two payloads, not one:
  matrix.json  values, units, fiscal years, source ids, status, confidence,
               url index. No verbatim quotes. Loads on boot; budget 900 KB.
  quotes.json  {ticker: {field: quote}}. Loads lazily on first point click --
               the quote is the demo, but it is not needed to draw a point.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .common.entities import sectors, universe
from .common.fields import FIELDS, VALIDATION_ONLY
from .common.paths import DB_PATH, MATRIX_PATH

#: Bump when the payload SHAPE changes (new/renamed top-level keys, a field
#: record's keys change meaning). The frontend asserts this on boot so a shape
#: drift fails loudly instead of silently misreading old keys.
PAYLOAD_SCHEMA_VERSION = 1

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


#: The analysis year the dashboard scores on. Annual FLOWS prefer this year,
#: falling back per-field to the highest-priority source's most recent year
#: when this year has nothing trustworthy -- see _select_key. GHGRP emissions
#: (Scope 1) cap out at fiscal_year 2023, so they land there automatically
#: under this same fallback rule, without a special case: no ranking compares
#: a June year-end's FY2026 against a calendar filer's FY2025, but a 2025
#: revenue figure is still compared against a 2023 emissions figure, because
#: that is genuinely the newest real number each field has.
#:
#: MUST match `python -m pipeline.export_wide --year <ANALYSIS_YEAR>
#: --fallback` (data/wide_FY2025_fallback.csv) field-for-field, fiscal-year-
#: for-fiscal-year -- that CSV is what score_calculation's Python pillar
#: scores are actually computed from, and web/scripts/verify-scoring-parity.ts
#: diffs THIS payload's computeScores() output against those Python scores.
#: If the two ever select a different year for the same field, no amount of
#: fixing web/src/scoring's formulas will make the numbers agree, because
#: they will be scoring genuinely different inputs.
ANALYSIS_YEAR = 2025


def _select_key(rec: dict, year: int | None) -> tuple:
    """Sorts ascending = best first, so the `best` loop below can keep
    replacing on `<`. Mirrors export_wide.py's collect()/score() ordering
    exactly (translated to this module's min-wins convention): an exact hit
    on `year` outranks a newer or higher-priority-source row from any other
    year; ties break on source precedence, then on most recent fiscal year.
    Applied uniformly to every field, snapshot/timeless included -- export_
    wide.py's own fallback scoring does the same, and special-casing them
    here would silently pick a different row than that CSV does for the
    same field.
    """
    exact = 0 if (year and rec["fy"] == year) else 1
    return (exact, _rank(rec["src"]), -rec["fy"])


def export(db_path=DB_PATH, out=MATRIX_PATH, quotes_out=None,
           year: int = ANALYSIS_YEAR) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM observations WHERE status IN "
        "('structural','quote_verified','imputed') ORDER BY fiscal_year DESC"
    ).fetchall()
    conn.close()
    # No upfront year filter: every trustworthy row stays in play, and
    # _select_key below picks the single best one per (ticker, field) --
    # an exact hit on `year` wins when one exists, otherwise the best
    # available row from whatever year actually has one. A hard pre-filter
    # (this module's old behavior) would just have to duplicate this same
    # fallback rule a second time to recover the rows it dropped.

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
            # The quote IS the demo — click a number, see the sentence. But a
            # full SBTi target paragraph can run to 1.5 kB; one sentence is
            # enough to show and keeps the payload inside the offline budget.
            "q": (r["quote"][:240] + "…") if r["quote"] and len(r["quote"]) > 240
                 else r["quote"],
            "url": intern(r["source_url"]),
        }
        cur = best.get(k)
        if cur is None or _select_key(rec, year) < _select_key(cur, year):
            if cur is not None and cur["src"] != rec["src"]:
                alts[k].append(cur)
            best[k] = rec
        elif rec["src"] != cur["src"]:
            # An alternative means ANOTHER SOURCE for the same number — that is
            # the say-do comparison. A different fiscal year of the same source
            # is not an alternative, it is history, and carrying it here both
            # bloated the payload and invited mixed-year ranking.
            alts[k].append(rec)

    sec = sectors()
    meta = {r["ticker"]: r for r in universe()}
    companies = []
    quotes: dict[str, dict[str, str]] = {}
    for t in sorted({k[0] for k in best}):
        vals = {f: best[(t, f)] for (tk, f) in best if tk == t}
        n = len(vals)
        # Quotes are the click-through demo but not needed to render a point,
        # so they ship in a separate lazy-loaded payload -- see quotes_out
        # below. `fields` on the boot payload never carries `q`.
        t_quotes = {f: rec["q"] for f, rec in vals.items() if rec.get("q")}
        if t_quotes:
            quotes[t] = t_quotes
        matrix_fields = {f: {k: v for k, v in rec.items() if k != "q"}
                          for f, rec in vals.items()}
        companies.append({
            "ticker": t,
            "name": meta.get(t, {}).get("company", t),
            "sector": sec.get(t, "Unknown"),
            "sub_industry": meta.get(t, {}).get("sub_industry", ""),
            "fields": matrix_fields,
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

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "generated_at": generated_at,
        "analysis_year": year,
        "schema": {f: {"unit": s.unit, "pillar": s.pillar, "dtype": s.dtype.__name__,
                       "description": s.description}
                   for f, s in FIELDS.items() if f not in VALIDATION_ONLY},
        "source_priority": SOURCE_PRIORITY,
        # index -> url; `url` on each record is a position in this list
        "urls": [u for u, _ in sorted(urls.items(), key=lambda kv: kv[1])],
        "companies": companies,
    }
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"wrote {out} -- {len(companies)} companies, {kb:.0f} KB")
    if kb > 900:
        print("  WARNING: over the 900 KB boot budget. Trim fields shipped in "
              "matrix.json -- quotes already live in the lazy quotes.json.")

    quotes_payload = {
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "generated_at": generated_at,
        "quotes": quotes,
    }
    quotes_out = Path(quotes_out) if quotes_out else out.parent / "quotes.json"
    quotes_out.parent.mkdir(parents=True, exist_ok=True)
    quotes_out.write_text(json.dumps(quotes_payload, separators=(",", ":")), encoding="utf-8")
    qkb = quotes_out.stat().st_size / 1024
    print(f"wrote {quotes_out} -- {qkb:.0f} KB")

    return payload


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(MATRIX_PATH))
    ap.add_argument("--quotes-out", default=None,
                     help="default: quotes.json next to --out")
    a = ap.parse_args()
    export(a.db, Path(a.out), Path(a.quotes_out) if a.quotes_out else None)
