"""S04 extraction, proved against a synthetic proxy. No network.

The traps are the ones that turn a keyword match into a wrong answer:
negation ("we do not maintain a clawback policy"), an inverted board count
("all but one of our eleven directors"), and the difference between a document
we read that says nothing and a document we never fetched.

    python -m pipeline.sources.s04_sec_def14a.test_extract_fixture
"""

from __future__ import annotations

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


RICH = """<html><body>
<p>The Nominating and Corporate Governance Committee oversees the Company's
climate-related risks and opportunities.</p>
<p>We do not maintain a clawback policy for our executive officers.</p>
<p>All but one of our eleven directors are independent.</p>
<p>Our annual incentive scorecard includes a greenhouse gas emissions
reduction metric weighted at 10%.</p>
<p>The Company obtained limited assurance over its Scope 1 and Scope 2
emissions from an independent third party.</p>
<p>Awards granted under the plan vest over a three-year performance period.</p>
<p>The Board has designated a lead independent director.</p>
</body></html>"""

# A real proxy that simply says none of these things.
BARE = """<html><body><p>The Board met four times during the year.</p>
<p>Directors receive an annual retainer of $100,000.</p></body></html>"""


def main() -> int:
    uni = list(universe())
    ta, tb, tc = [r["ticker"] for r in uni[:3]]

    tmp = Path(tempfile.mkdtemp(prefix="s04-fixture-"))
    cache.CACHE_RAW, jsonl.OBSERVATIONS = tmp / "raw", tmp / "obs"
    cache.put_raw("S04", f"proxy-{ta}", RICH.encode(), ".html")
    cache.put_raw("S04", f"proxy-{tb}", BARE.encode(), ".html")
    # tc: nothing cached at all

    from .extract import extract
    print(extract([ta, tb, tc], year=2025).replace("\n", "\n  "))

    from ...load import build
    db = tmp / "t.db"
    build(db, verbose=False, base=tmp / "obs")
    conn = sqlite3.connect(db)

    def v(t, f):
        r = conn.execute("SELECT value_num, value_text, status, quote, extracted_by "
                         "FROM observations WHERE ticker=? AND field=?", (t, f)).fetchone()
        return r or (None, None, None, None, None)

    print()
    check("climate committee found", v(ta, "has_climate_oversight_committee")[0] == 1.0,
          str(v(ta, "has_climate_oversight_committee")[:3]))
    check("its quote survived validation",
          v(ta, "has_climate_oversight_committee")[2] == "quote_verified",
          str(v(ta, "has_climate_oversight_committee")[2]))

    cb = v(ta, "has_clawback_policy")
    check("NEGATION TRAP: 'we do not maintain a clawback policy' reads False",
          cb[0] == 0.0, str(cb[:3]))
    check("the negated sentence is kept as the evidence",
          cb[3] is not None and "do not maintain" in cb[3], str(cb[3]))
    check("negation recorded in extracted_by", cb[4] == "rule:phrase_negated", str(cb[4]))

    check("INVERTED COUNT: 'all but one of eleven' is 10 independent of 11",
          v(ta, "independent_director_count")[0] == 10.0
          and v(ta, "board_size")[0] == 11.0,
          f"{v(ta,'independent_director_count')[0]} of {v(ta,'board_size')[0]}")

    # comp_tied_to_emissions_target is deliberately NOT extracted here — see
    # parse.NOT_EXTRACTABLE. Pattern matching gave near-100% false positives.
    from . import parse as _p
    check("abandoned field is not emitted",
          "comp_tied_to_emissions_target" in _p.NOT_EXTRACTABLE
          and v(ta, "comp_tied_to_emissions_target")[2] is None,
          str(v(ta, "comp_tied_to_emissions_target")[2]))
    check("assurance level read as 'limited'", v(ta, "assurance_level")[1] == "limited",
          str(v(ta, "assurance_level")[1]))
    check("performance period read as 3 years",
          v(ta, "performance_period_years")[0] == 3.0)
    check("lead independent director found", v(ta, "lead_independent_director")[0] == 1.0)
    check("emissions boundary stated (Scope 1 and Scope 2 named)",
          v(ta, "emissions_boundary_stated")[0] == 1.0)

    # Absence means different things for different detectors.
    # HIGH RECALL (a term of art any proxy using the concept would state):
    # a silent document is a real False.
    bare_hr = v(tb, "has_clawback_policy")
    check("high-recall field: read-but-silent proxy gives False",
          bare_hr[0] == 0.0 and bare_hr[2] == "structural", str(bare_hr[:3]))
    check("  ...and carries no quote, so structural not quote_verified",
          bare_hr[3] is None, str(bare_hr[3]))
    # LOW RECALL (a concept detector that misses most real cases): absence is
    # NOT evidence of absence. Asserting False would invent a majority.
    bare_lr = v(tb, "has_climate_oversight_committee")
    check("low-recall field: silent proxy is not_disclosed, NOT False",
          bare_lr[2] == "not_disclosed" and bare_lr[0] is None, str(bare_lr[:3]))

    # No proxy at all -> not_disclosed. We did not look.
    none = v(tc, "has_clawback_policy")
    check("uncached company is not_disclosed, never False", none[2] == "not_disclosed"
          and none[0] is None, str(none[:3]))

    nq = conn.execute("SELECT COUNT(*) FROM observations WHERE status='quote_verified' "
                      "AND (quote IS NULL OR quote='')").fetchone()[0]
    check("no quote_verified record lacks a quote", nq == 0, f"{nq} found")
    conn.close()

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if _fail:
        print(f"{len(_fail)} FAILED: {', '.join(_fail)}")
        return 1
    print("S04 extraction logic verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
