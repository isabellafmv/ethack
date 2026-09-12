"""End-to-end proof of the shared contract, on fake records. No network.

    python -m pipeline.test_pipeline

This exists so that sixteen agents are building against something that has been
shown to work, rather than against a design. It tests the parts they all touch:
the record shape, the quote rule, the writer, the loader, and the rebuild
guarantee.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

from .common import quotes
from .common.fields import FIELDS
from .common.jsonl import ObservationWriter, run_stamp
from .common.paths import ensure_dirs
from .common.schema import Observation, SchemaError, Status, validate

PASS, FAIL = "  ok  ", "  FAIL"
_failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{PASS if cond else FAIL}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        _failures.append(name)


def obs(**kw) -> Observation:
    base = dict(
        ticker="TEST", field="revenue_usd", value=1.0e9, unit="usd",
        fiscal_year=2024, period_end="2024-12-31", quote=None, source="S01",
        source_url="https://example.invalid/x", source_section="us-gaap:Revenues",
        extracted_by="xbrl:Revenues", status=Status.STRUCTURAL,
    )
    base.update(kw)
    return Observation(**base)


def test_schema() -> None:
    print("\nschema")
    validate(obs())
    check("structural record with no quote is accepted", True)

    try:
        validate(obs(field="not_a_real_field"))
        check("unknown field rejected", False, "it was accepted")
    except SchemaError:
        check("unknown field rejected", True)

    try:
        validate(obs(unit="millions"))
        check("wrong unit rejected", False, "it was accepted")
    except SchemaError:
        check("wrong unit rejected", True)

    try:
        validate(obs(status=Status.QUOTE_VERIFIED, quote="we earned money"))
        check("quote_verified on a structural-only source is allowed", True)
    except SchemaError as e:
        check("quote_verified accepted", False, str(e))

    try:
        validate(obs(value=None))
        check("silent null rejected", False, "it was accepted")
    except SchemaError:
        check("silent null rejected", True)

    nd = validate(obs(value=None, unit=None, status=Status.NOT_DISCLOSED))
    check("not_disclosed carries no value", nd.value is None)

    try:
        validate(obs(field="cik", value="0000320193", unit=None, fiscal_year=2024))
        check("timeless field rejects a real fiscal_year", False, "it was accepted")
    except SchemaError:
        check("timeless field rejects a real fiscal_year", True)

    from .common.units import to_pct, to_tco2e, fiscal_year
    check("to_pct converts a fraction", to_pct(0.42, as_fraction=True) == 42.0)
    check("short tons convert to tonnes", abs(to_tco2e(1000, "short tons") - 907.185) < 1e-3)
    check("a January year-end aligns to the previous cohort",
          fiscal_year("2025-01-31") == 2024)

    try:
        validate(obs(field="target_reduction_pct", value=4200.0, unit="pct",
                     source="S09", status=Status.QUOTE_VERIFIED, quote="x" * 30))
        check("pct out of range rejected", False, "it was accepted")
    except SchemaError:
        check("pct out of range rejected", True)

    try:
        validate(obs(field="scope1_tco2e", value=1.0, unit="tco2e", source="S01",
                     status=Status.STRUCTURAL))
        check("source not declared for a field is rejected", False, "it was accepted")
    except SchemaError:
        check("source not declared for a field is rejected", True)


def test_quotes() -> None:
    print("\nthe quote rule")
    src = ("The Board's Nominating and Governance Committee has explicit "
           "oversight of climate‑related risks and opportunities.")
    check("verbatim quote validates",
          quotes.verify("explicit oversight of climate-related risks", src))
    check("paraphrase is rejected",
          not quotes.verify("the board oversees climate risk", src))
    check("smart quotes and nbsp normalise",
          quotes.verify("climate‑related risks", src))
    check("empty quote is rejected", not quotes.verify("", src))
    check("two-word quote flagged as insubstantive",
          not quotes.is_substantive("climate risk"))
    check("negation trap is flagged",
          quotes.looks_negated("we do not maintain a clawback policy for executives"))

    bad = validate(
        obs(status=Status.QUOTE_VERIFIED, quote="we tripled our revenue this year"),
        source_text=src,
    )
    check("non-substring quote downgrades to quote_failed",
          bad.status is Status.QUOTE_FAILED and bad.value is None)


def test_writer_and_loader() -> None:
    print("\nwriter -> jsonl -> loader -> db")
    ensure_dirs()
    run = "TEST" + run_stamp()
    tmp = Path(tempfile.mkdtemp(prefix="pipeline-test-"))

    with ObservationWriter("S01", run=run, base=tmp) as w:
        w.write(obs())
        w.write(obs(field="capex_usd", value=5.0e8))
        w.write(obs(field="ebitda_usd", value=None, unit=None, status=Status.NOT_DISCLOSED))
        w.write(obs(field="not_a_real_field"))          # must be rejected, not crash
    check("bad record rejected without killing the run", len(w.rejected) == 1)
    check("good records written", sum(w.counts.values()) == 3)

    # Same company-year, same field, DIFFERENT source: both must survive. This
    # is the say-do comparison at the storage layer.
    with ObservationWriter("S15", run=run, base=tmp) as w2:
        w2.write(obs(field="scope1_tco2e", value=1000.0, unit="tco2e", source="S15",
                     source_section="GHGRP", extracted_by="rule:ghgrp"))
    with ObservationWriter("S10", run=run, base=tmp) as w3:
        w3.write(obs(field="scope1_tco2e", value=600.0, unit="tco2e", source="S10",
                     status=Status.QUOTE_VERIFIED,
                     quote="our Scope 1 emissions totalled 600 tonnes of CO2e",
                     source_section="Sustainability Report p.14",
                     extracted_by="agent:test"))

    from .load import build
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "scores.db"
        build(db, verbose=False, base=tmp)
        conn = sqlite3.connect(db)

        n = conn.execute("SELECT COUNT(*) FROM observations WHERE ticker='TEST'").fetchone()[0]
        check("records loaded", n >= 5, f"got {n}")

        both = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE ticker='TEST' AND field='scope1_tco2e'"
        ).fetchone()[0]
        check("measured and reported values of the same number coexist", both == 2, f"got {both}")

        gap = conn.execute(
            "SELECT relative_gap FROM disagreements WHERE ticker='TEST' AND field='scope1_tco2e'"
        ).fetchone()
        # a.source < b.source, so a=S10 (reported 600), b=S15 (measured 1000):
        # the measured figure is 66.7% above what the company said.
        check("disagreements view finds the say-do gap",
              gap is not None and abs(gap[0] - 2 / 3) < 1e-9,
              f"got {gap}")

        conf = conn.execute(
            "SELECT mean_confidence FROM company_confidence WHERE ticker='TEST'"
        ).fetchone()
        check("confidence view populated", conf is not None and 0 < conf[0] <= 1)

        # The rebuild guarantee.
        build(db, verbose=False, base=tmp)
        n2 = conn.execute("SELECT COUNT(*) FROM observations WHERE ticker='TEST'").fetchone()[0]
        check("reload is idempotent (no duplicate rows)", n2 == n, f"{n} -> {n2}")
        conn.close()

        db.unlink()
        build(db, verbose=False, base=tmp)
        check("rm scores.db && load rebuilds from scratch", db.exists())

    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


def test_sources() -> None:
    print("\nsource packages")
    import importlib
    from .sources import __path__ as spath
    pkgs = sorted(p.name for p in Path(spath[0]).iterdir()
                  if p.is_dir() and p.name.startswith("s"))
    check("16 source packages exist", len(pkgs) == 16, f"got {len(pkgs)}")

    bad = []
    for pkg in pkgs:
        for mod in ("fields", "pull", "extract"):
            try:
                importlib.import_module(f".sources.{pkg}.{mod}", package="pipeline")
            except Exception as e:
                bad.append(f"{pkg}.{mod}: {e}")
    check("every source package imports cleanly", not bad, "; ".join(bad[:3]))

    declared = set()
    for pkg in pkgs:
        m = importlib.import_module(f".sources.{pkg}.fields", package="pipeline")
        declared |= set(m.EMITS)
    orphans = sorted(set(FIELDS) - declared)
    print(f"        {len(declared)}/{len(FIELDS)} vocabulary fields claimed by a source")
    if orphans:
        print(f"        unclaimed (no in-scope source emits these): {', '.join(orphans)}")


if __name__ == "__main__":
    test_schema()
    test_quotes()
    test_writer_and_loader()
    test_sources()
    print()
    if _failures:
        print(f"{len(_failures)} FAILED: {', '.join(_failures)}")
        sys.exit(1)
    print("contract holds. sixteen agents may now be pointed at pipeline/sources/.")
