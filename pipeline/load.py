"""JSONL -> SQLite. The ONLY writer to the database.

    rm data/scores.db && python -m pipeline.load

must always work. If it ever does not, the database has become load-bearing
and someone has written to it out of band. Find that and delete it.

The table is flat and deliberately unnormalised. `source` is in the primary key
because that is what lets an EPA-measured, a company-reported and a modelled
value of the same number sit side by side -- which is the say-do comparison,
expressed at the storage layer.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

from .common.jsonl import all_runs, read_jsonl
from .common.paths import DB_PATH, ensure_dirs
from .common.schema import CONFIDENCE, Status

DDL = """
CREATE TABLE IF NOT EXISTS observations (
    ticker          TEXT    NOT NULL,
    field           TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    fiscal_year     INTEGER NOT NULL,
    value_num       REAL,
    value_text      TEXT,
    unit            TEXT,
    period_end      TEXT,
    quote           TEXT,
    source_url      TEXT    NOT NULL,
    source_section  TEXT,
    extracted_by    TEXT,
    status          TEXT    NOT NULL,
    confidence      REAL    NOT NULL,
    retrieved_at    TEXT,
    run             TEXT,
    schema_version  TEXT,
    PRIMARY KEY (ticker, field, source, fiscal_year)
);
CREATE INDEX IF NOT EXISTS ix_obs_field  ON observations(field);
CREATE INDEX IF NOT EXISTS ix_obs_ticker ON observations(ticker);
CREATE INDEX IF NOT EXISTS ix_obs_status ON observations(status);

-- Every field where two sources disagree about the same company-year.
-- This view IS the product. Keep it working.
CREATE VIEW IF NOT EXISTS disagreements AS
SELECT a.ticker, a.field, a.fiscal_year,
       a.source AS source_a, a.value_num AS value_a, a.status AS status_a,
       b.source AS source_b, b.value_num AS value_b, b.status AS status_b,
       CASE WHEN a.value_num IS NOT NULL AND b.value_num IS NOT NULL
                 AND a.value_num <> 0
            THEN (b.value_num - a.value_num) / ABS(a.value_num)
       END AS relative_gap
FROM observations a
JOIN observations b
  ON a.ticker = b.ticker AND a.field = b.field
 AND a.fiscal_year = b.fiscal_year AND a.source < b.source
WHERE a.value_num IS NOT NULL AND b.value_num IS NOT NULL;

-- Per-company evidence weight -> point opacity on the 3D map.
CREATE VIEW IF NOT EXISTS company_confidence AS
SELECT ticker,
       COUNT(*)                                            AS observations,
       SUM(CASE WHEN status IN ('quote_verified','structural') THEN 1 ELSE 0 END) AS verified,
       SUM(CASE WHEN status = 'imputed'       THEN 1 ELSE 0 END) AS imputed,
       SUM(CASE WHEN status = 'not_disclosed' THEN 1 ELSE 0 END) AS not_disclosed,
       AVG(confidence)                                     AS mean_confidence
FROM observations GROUP BY ticker;
"""


def _split_value(v):
    """Numbers and booleans go to value_num, strings to value_text. Booleans
    become 1.0/0.0 so the four governance booleans average cleanly."""
    if v is None:
        return None, None
    if isinstance(v, bool):
        return float(v), None
    if isinstance(v, (int, float)):
        return float(v), None
    return None, str(v)


def build(db_path=DB_PATH, verbose: bool = True, base=None) -> dict:
    ensure_dirs()
    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)

    files = all_runs(base=base)
    stats = {"files": len(files), "rows_read": 0, "rows_written": 0, "bad": 0, "by_source": {}}

    for path in files:              # sorted oldest-first: later runs win
        n = 0
        for rec in read_jsonl(path):
            stats["rows_read"] += 1
            try:
                num, text = _split_value(rec.get("value"))
                status = rec["status"]
                conn.execute(
                    "INSERT OR REPLACE INTO observations "
                    "(ticker, field, source, fiscal_year, value_num, value_text, unit, "
                    " period_end, quote, source_url, source_section, extracted_by, "
                    " status, confidence, retrieved_at, run, schema_version) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rec["ticker"], rec["field"], rec["source"], int(rec["fiscal_year"]),
                     num, text, rec.get("unit"), rec.get("period_end"), rec.get("quote"),
                     rec.get("source_url", ""), rec.get("source_section"),
                     rec.get("extracted_by"), status,
                     CONFIDENCE.get(Status(status), 0.0), rec.get("retrieved_at"),
                     rec.get("run"), rec.get("schema_version")),
                )
                n += 1
                stats["rows_written"] += 1
            except (KeyError, ValueError, sqlite3.Error) as e:
                stats["bad"] += 1
                if verbose and stats["bad"] <= 5:
                    print(f"  bad row in {path.name}: {e}", file=sys.stderr)
        src = path.parent.name
        stats["by_source"][src] = stats["by_source"].get(src, 0) + n

    conn.commit()
    if verbose:
        print(f"loaded {stats['rows_written']}/{stats['rows_read']} rows "
              f"from {stats['files']} files into {db_path}")
        for src, n in sorted(stats["by_source"].items()):
            print(f"  {src:<8} {n}")
        if stats["bad"]:
            print(f"  {stats['bad']} rows rejected", file=sys.stderr)
    conn.close()
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Rebuild scores.db from the JSONL log.")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()
    build(args.db)
