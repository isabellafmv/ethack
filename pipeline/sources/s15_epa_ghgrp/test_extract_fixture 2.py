"""S15 extraction, proved against synthetic GHGRP files. No network.

The traps are the ones that inflate or flatter rather than crash: a jointly
owned facility counted twice, a company with no US facilities scored as zero
emissions, a divestiture read as decarbonisation.

    python -m pipeline.sources.s15_epa_ghgrp.test_extract_fixture
"""

from __future__ import annotations

import csv
import io
import sqlite3
import tempfile
from pathlib import Path

from ...common import cache, jsonl
from ...common.entities import universe

_fail: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'  ok  ' if cond else '  FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        _fail.append(name)


PARENT_HEADERS = ["GHGRP Facility ID", "Reporting Year", "Facility Name",
                  "Parent Company Name", "Parent Co. Percent Ownership",
                  "Facility State", "Total Reported Direct Emissions"]


def parent_csv(a: str, b: str) -> bytes:
    rows = [
        # A jointly owned facility: 60/40. Must split, not double-count.
        ["F1", 2023, "Joint Plant", a, "60", "Texas", "1000"],
        ["F1", 2023, "Joint Plant", b, "40", "Texas", "1000"],
        # A wholly owned second facility for A.
        ["F2", 2023, "Solo Plant", a, "100", "Ohio", "500"],
        # 2024: A has SOLD F2. Emissions fall, but it is a divestiture.
        ["F1", 2024, "Joint Plant", a, "60", "Texas", "1000"],
        ["F1", 2024, "Joint Plant", b, "40", "Texas", "1000"],
        # A parent that is not in the S&P 500 at all.
        ["F9", 2023, "Outsider", "Some Private Holdings LLC", "100", "Utah", "9999"],
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(PARENT_HEADERS)
    w.writerows(rows)
    return buf.getvalue().encode()


def main() -> int:
    uni = list(universe())
    a, b, c = [r["company"] for r in uni[:3]]
    ta, tb, tc = [r["ticker"] for r in uni[:3]]

    tmp = Path(tempfile.mkdtemp(prefix="s15-fixture-"))
    cache.CACHE_RAW, jsonl.OBSERVATIONS = tmp / "raw", tmp / "obs"
    cache.put_raw("S15", "parent", parent_csv(a, b), ".csv")

    from .extract import extract
    print(extract([ta, tb, tc]).replace("\n", "\n  "))

    from ...load import build
    db = tmp / "t.db"
    build(db, verbose=False, base=tmp / "obs")
    conn = sqlite3.connect(db)

    def v(ticker, field, year):
        r = conn.execute("SELECT value_num, status, extracted_by FROM observations "
                         "WHERE ticker=? AND field=? AND fiscal_year=?",
                         (ticker, field, year)).fetchone()
        return r or (None, None, None)

    print()
    # A 2023: 60% of 1000 + 100% of 500 = 1100
    check("ownership weighting applied", v(ta, "scope1_tco2e", 2023)[0] == 1100.0,
          str(v(ta, "scope1_tco2e", 2023)))
    # B 2023: 40% of 1000 = 400 — not the full 1000
    check("jointly owned facility split, not double-counted",
          v(tb, "scope1_tco2e", 2023)[0] == 400.0, str(v(tb, "scope1_tco2e", 2023)))
    check("partial ownership recorded in extracted_by",
          "partial" in (v(tb, "scope1_tco2e", 2023)[2] or ""),
          str(v(tb, "scope1_tco2e", 2023)[2]))
    check("facility count per year", v(ta, "ghg_facility_count", 2023)[0] == 2.0
          and v(ta, "ghg_facility_count", 2024)[0] == 1.0,
          f"{v(ta,'ghg_facility_count',2023)} {v(ta,'ghg_facility_count',2024)}")
    # A 2024: only F1 at 60% = 600. Looks like a 45% cut; it is a sale.
    check("divestiture is visible as a facility-count change, not just a fall",
          v(ta, "scope1_tco2e", 2024)[0] == 600.0
          and v(ta, "ghg_facility_count", 2023)[0] != v(ta, "ghg_facility_count", 2024)[0],
          str(v(ta, "scope1_tco2e", 2024)))

    # C has no GHGRP facilities. This is the 430-company question in miniature.
    check("company absent from GHGRP is NOT scored as zero emissions",
          v(tc, "scope1_tco2e", 2024)[1] == "not_disclosed"
          and v(tc, "scope1_tco2e", 2024)[0] is None,
          str(v(tc, "scope1_tco2e", 2024)))
    zeros = conn.execute("SELECT COUNT(*) FROM observations WHERE field='scope1_tco2e' "
                         "AND value_num = 0").fetchone()[0]
    check("no company anywhere gets a zero-emissions score by default", zeros == 0,
          f"{zeros} zero rows")

    outsider = conn.execute("SELECT COUNT(*) FROM observations WHERE value_num=9999"
                            ).fetchone()[0]
    check("non-constituent parent not attributed to anyone", outsider == 0)
    conn.close()

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if _fail:
        print(f"{len(_fail)} FAILED: {', '.join(_fail)}")
        return 1
    print("S15 extraction logic verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
