"""S09 extraction, proved against a synthetic SBTi export. No network.

The traps here are the ones that produce a flattering answer rather than an
error: a commitment counted as a validated target, a non-US namesake matched to
an S&P 500 ticker, a company absent from the export quietly skipped instead of
recorded as having no target.

    python -m pipeline.sources.s09_sbti.test_extract_fixture
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


# The real export is wide: one row per company, near-term and net-zero side by
# side. The fixture mirrors that shape so the test exercises the real path.
HEADERS = ["Company Name", "Location", "Action",
           "Near term - Target Status", "Near term - Target Year",
           "Near term - Scope", "Net zero - Target Status",
           "Net zero - Target Year", "Base Year", "Date Published"]


def fixture_csv(names: list[str]) -> bytes:
    a, b, c = names
    rows = [
        # Both a validated near-term (2030) AND a net-zero (2050) target.
        # Near-term must win: 2050 would spread the abatement bill over 26 years.
        [a, "United States", "Targets Set", "Targets Set", "2030", "Scope 1+2",
         "Targets Set", "2050", "2019", "2022-05-01"],
        # TRAP: merely committed, not validated.
        [b, "United States", "Committed", "", "", "", "", "", "", "2024-03-01"],
        # TRAP: a non-US namesake that must not match the US ticker.
        [c, "Japan", "Targets Set", "Targets Set", "2035", "Scope 1+2",
         "", "", "2018", "2021-01-01"],
    ]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADERS)
    w.writerows(rows)
    return buf.getvalue().encode()


def main() -> int:
    uni = list(universe())
    a, b, c, d = [r["company"] for r in uni[:4]]
    ta, tb, tc, td = [r["ticker"] for r in uni[:4]]

    tmp = Path(tempfile.mkdtemp(prefix="s09-fixture-"))
    cache.CACHE_RAW, jsonl.OBSERVATIONS = tmp / "raw", tmp / "obs"
    cache.put_raw("S09", "sbti_export", fixture_csv([a, b, c]), ".csv")

    from .extract import extract
    print(extract([ta, tb, tc, td], vintage=2024).replace("\n", "\n  "))

    from ...load import build
    db = tmp / "t.db"
    build(db, verbose=False, base=tmp / "obs")
    conn = sqlite3.connect(db)

    def v(ticker, field):
        r = conn.execute("SELECT value_num, value_text, status FROM observations "
                         "WHERE ticker=? AND field=?", (ticker, field)).fetchone()
        return r or (None, None, None)

    print()
    check("validated target recorded as True", v(ta, "sbti_target_validated")[0] == 1.0,
          str(v(ta, "sbti_target_validated")))
    # Deliberate: near-term beats net-zero. A 2050 horizon spreads the same
    # abatement bill over 26 years and flatters the affordability ratio.
    check("near-term target preferred over net-zero",
          v(ta, "sbti_target_type")[1] == "near-term", str(v(ta, "sbti_target_type")))
    check("target year is the near-term one, not 2050",
          v(ta, "target_year")[0] == 2030.0, str(v(ta, "target_year")))
    check("base year parsed", v(ta, "target_baseline_year")[0] == 2019.0)
    check("scope coverage carried", "Scope" in (v(ta, "target_scope_coverage")[1] or ""))

    check("a COMMITMENT is not a validated target",
          v(tb, "sbti_target_validated")[0] == 0.0, str(v(tb, "sbti_target_validated")))
    check("commitment typed as 'commitment', not a target",
          v(tb, "sbti_target_type")[1] == "commitment", str(v(tb, "sbti_target_type")))
    check("commitment has no target year",
          v(tb, "target_year")[2] == "not_disclosed", str(v(tb, "target_year")))

    check("non-US namesake not matched to the US ticker",
          v(tc, "sbti_target_validated")[0] == 0.0, str(v(tc, "sbti_target_validated")))

    check("company absent from the export is recorded, not skipped",
          v(td, "sbti_target_validated")[2] == "structural"
          and v(td, "sbti_target_validated")[0] == 0.0, str(v(td, "sbti_target_validated")))
    check("absent company's target year is not_disclosed, never 0",
          v(td, "target_year")[2] == "not_disclosed" and v(td, "target_year")[0] is None,
          str(v(td, "target_year")))

    n = conn.execute("SELECT COUNT(*) FROM observations WHERE field='target_year' "
                     "AND value_num IS NOT NULL").fetchone()[0]
    check("no target year invented for anyone", n == 1, f"{n} companies have a target year")
    conn.close()

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if _fail:
        print(f"{len(_fail)} FAILED: {', '.join(_fail)}")
        return 1
    print("S09 extraction logic verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
