"""S01 extraction, proved against a synthetic companyfacts document.

No network, no real cache touched. This exists because the extraction rules are
where the quiet errors live: a quarterly fact mistaken for an annual one, a
restatement picked over the original, a fiscal year misaligned by twelve months,
a half-computed FCF. Each of those produces a plausible number.

    python -m pipeline.sources.s01_sec_xbrl.test_extract_fixture
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

from ...common import cache, jsonl
from ...common.entities import ticker_to_cik

_fail: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'  ok  ' if cond else '  FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        _fail.append(name)


def _usd(*entries):
    return {"units": {"USD": list(entries)}}


def fixture() -> dict:
    """One company, two fiscal years, with the traps deliberately planted."""
    return {"facts": {"us-gaap": {
        # Revenue: the FIRST tag in the chain is absent, so the fallback must fire.
        "Revenues": _usd(
            {"start": "2024-01-01", "end": "2024-12-31", "val": 1000.0,
             "form": "10-K", "accn": "a-1", "filed": "2025-02-01"},
            # A restatement of the same year, filed later: this must win.
            {"start": "2024-01-01", "end": "2024-12-31", "val": 1100.0,
             "form": "10-K", "accn": "a-2", "filed": "2026-02-01"},
            # A QUARTER. Must be rejected -- same tag, same year, wrong period.
            {"start": "2024-10-01", "end": "2024-12-31", "val": 250.0,
             "form": "10-K", "accn": "a-3", "filed": "2025-02-01"},
            # A 10-Q. Must be rejected on form.
            {"start": "2023-01-01", "end": "2023-12-31", "val": 900.0,
             "form": "10-Q", "accn": "a-4", "filed": "2024-05-01"},
            {"start": "2023-01-01", "end": "2023-12-31", "val": 950.0,
             "form": "10-K", "accn": "a-5", "filed": "2024-02-01"},
        ),
        "OperatingIncomeLoss": _usd(
            {"start": "2024-01-01", "end": "2024-12-31", "val": 200.0,
             "form": "10-K", "accn": "b-1", "filed": "2025-02-01"}),
        "NetCashProvidedByUsedInOperatingActivities": _usd(
            {"start": "2024-01-01", "end": "2024-12-31", "val": 300.0,
             "form": "10-K", "accn": "c-1", "filed": "2025-02-01"}),
        "PaymentsToAcquirePropertyPlantAndEquipment": _usd(
            {"start": "2024-01-01", "end": "2024-12-31", "val": 120.0,
             "form": "10-K", "accn": "d-1", "filed": "2025-02-01"}),
        # D&A present for 2024 only -> EBITDA exists in 2024, absent in 2023.
        "DepreciationDepletionAndAmortization": _usd(
            {"start": "2024-01-01", "end": "2024-12-31", "val": 50.0,
             "form": "10-K", "accn": "e-1", "filed": "2025-02-01"}),
    }}}


def main() -> int:
    from .extract import extract, _facts_for_tag, _first_hit
    from .tags import TAG_CHAINS

    doc = fixture()

    print("fact selection")
    rev = _facts_for_tag(doc, "Revenues")
    check("quarterly fact rejected", 250.0 not in [f["val"] for f in rev.values()])
    check("10-Q rejected on form", 900.0 not in [f["val"] for f in rev.values()])
    check("later restatement wins", rev.get(2024, {}).get("val") == 1100.0,
          f"got {rev.get(2024, {}).get('val')}")
    check("prior year still present", rev.get(2023, {}).get("val") == 950.0)

    tag, _ = _first_hit(doc, TAG_CHAINS["revenue_usd"])
    check("fallback chain skips the absent first tag", tag == "Revenues", f"got {tag}")

    print("\nfull extract through the writer")
    ticker = next(iter(ticker_to_cik()))
    cik = ticker_to_cik()[ticker]
    tmp = Path(tempfile.mkdtemp(prefix="s01-fixture-"))
    cache.CACHE_RAW, jsonl.OBSERVATIONS = tmp / "raw", tmp / "obs"
    cache.put_raw("SEC", f"facts-{cik}", json.dumps(doc).encode(), ".json")

    print("  " + extract([ticker]).replace("\n", "\n  "))

    from ...load import build
    db = tmp / "t.db"
    build(db, verbose=False, base=tmp / "obs")
    conn = sqlite3.connect(db)

    def val(field, fy=2024):
        r = conn.execute("SELECT value_num, status, extracted_by FROM observations "
                         "WHERE ticker=? AND field=? AND fiscal_year=?",
                         (ticker, field, fy)).fetchone()
        return r or (None, None, None)

    check("revenue is the restated figure", val("revenue_usd")[0] == 1100.0, str(val("revenue_usd")))
    check("winning tag recorded in extracted_by",
          val("revenue_usd")[2] == "xbrl:Revenues", str(val("revenue_usd")[2]))
    check("FCF = OCF - capex", val("free_cash_flow_usd")[0] == 180.0,
          str(val("free_cash_flow_usd")))
    check("EBITDA = EBIT + D&A", val("ebitda_usd")[0] == 250.0, str(val("ebitda_usd")))
    check("EBITDA absent when D&A missing -> not_disclosed",
          val("ebitda_usd", 2023)[1] == "not_disclosed", str(val("ebitda_usd", 2023)))
    check("untagged concept -> not_disclosed, not skipped",
          val("rnd_expense_usd")[1] == "not_disclosed", str(val("rnd_expense_usd")))
    n = conn.execute("SELECT COUNT(*) FROM observations WHERE status='not_disclosed'").fetchone()[0]
    check("absences recorded rather than dropped", n > 0, f"got {n}")
    conn.close()

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if _fail:
        print(f"{len(_fail)} FAILED: {', '.join(_fail)}")
        return 1
    print("S01 extraction logic verified. Safe to run against the real cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
