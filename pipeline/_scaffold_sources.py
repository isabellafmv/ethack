"""Generate one package per in-scope source, with its brief pre-filled from the
data-source register. Re-runnable: never overwrites a file an agent has touched
(pass --force to rewrite SOURCE.md only).

    python -m pipeline._scaffold_sources
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .common.fields import fields_for_source
from .common.paths import REPO_ROOT

REGISTER = REPO_ROOT / "sp500_sustainability_data_sources.xlsx"
SOURCES_DIR = REPO_ROOT / "pipeline" / "sources"

SLUGS = {
    "S01": "s01_sec_xbrl", "S02": "s02_sec_10k", "S03": "s03_sec_fts",
    "S04": "s04_sec_def14a", "S05": "s05_sec_ex21", "S06": "s06_gleif",
    "S07": "s07_market", "S08": "s08_universe", "S09": "s09_sbti",
    "S10": "s10_reports", "S11": "s11_violation_tracker", "S12": "s12_senate_lda",
    "S13": "s13_cdp", "S14": "s14_kaggle_esg", "S15": "s15_epa_ghgrp",
    "S19": "s19_epa_egrid",
}

SEC_SOURCES = {"S01", "S02", "S03", "S04", "S05"}

# Sources that cannot be pulled programmatically today. The folder still exists
# so the manifest can say WHY coverage is zero instead of showing a silent gap.
BLOCKED = {
    "S11": "No public API. Web UI only; bulk data on request. Check licence "
           "terms before redistributing. Options: manual CSV export into "
           "cache/raw/S11/, or fall back to S18 (ECHO) for the environmental "
           "subset only.",
    "S13": "Useful bulk data is licence-gated. Free registration exposes some "
           "scores. Do NOT build a required indicator on this -- S10 (company "
           "sustainability PDFs) is the free substitute.",
}

# Extra per-source notes that are not in the register but came out of the
# planning conversation.
EXTRA = {
    "S01": "Revenue splits across 4+ XBRL tags. The fallback chain lives in\n"
           "this package's fields.py, as data, not scattered through caller code.\n"
           "FCF = NetCashProvidedByUsedInOperatingActivities - capex; if either leg\n"
           "is missing, emit not_disclosed rather than a partial number.",
    "S02": "DO NOT send whole filings to an agent (75k-200k tokens). Strip HTML,\n"
           "locate the section by heading, keep +/-2-3k chars around keyword hits,\n"
           "send 5-15k tokens. ~15x cheaper and MORE accurate.\n"
           "For risk_hitword_density: position beats frequency. Every company\n"
           "mentions litigation; what comes FIRST in Item 1A is what management\n"
           "fears. Naive counting has no negation handling -- name that limit.",
    "S04": "Extract BOOLEANS with verbatim quotes, never graded scores. Graded\n"
           "scores over prose is where hallucination lives. This is the only\n"
           "near-complete pillar, so it deserves the best extraction.\n"
           "NEGATION TRAP: 'we do not maintain a clawback policy' contains the\n"
           "keyword and means the opposite. Use quotes.looks_negated() as a flag.",
    "S05": "Companies may omit subsidiaries deemed immaterial -- a short list does\n"
           "NOT mean a simple company. Format is wildly inconsistent (tables,\n"
           "lists, paragraphs). No ownership percentages here; those come from S15.",
    "S08": "FREEZE the list at one date and commit it. Membership changes mid-build\n"
           "silently break every join. ~503 tickers for 500 companies (dual class).\n"
           "Already implemented at repo root as S&P_scrape.py -- port it here.",
    "S09": "Name matching to tickers is the only real work: match on normalised\n"
           "legal name WITHIN COUNTRY. Companies with no SBTi target still need a\n"
           "counterfactual (sector median commitment) written with status=imputed --\n"
           "never a null, because nulls reward silence.",
    "S10": "Self-reported: every number is a CLAIM with a quote attached, never a\n"
           "fact. PDFs are 60-150pp; pre-filter to the data-table pages first.\n"
           "A renewable claim that moves market-based Scope 2 but NOT the\n"
           "location-based figure is an unbundled REC purchase -- flag, don't credit.",
    "S14": "VALIDATION ONLY. Never an input to any pillar score -- it is the thing\n"
           "we are trying to beat. Expect modest rank correlation and investigate\n"
           "the disagreements; three explained disagreements beat any chart.",
    "S15": "The 'Reported Parent Companies' file is XLSB -- needs `pyxlsb`.\n"
           "Matches ~69 constituents but those carry ~82% of index Scope 1:\n"
           "deep, not broad. Emit ghg_facility_count every year -- a divestiture\n"
           "looks identical to an emissions cut, and companies whose facility\n"
           "count moves YoY must be excluded from trajectory scoring.",
    "S19": "Feeds location-based Scope 2 via the subregion intensity of a company's\n"
           "facility footprint. Depends on entity resolution (S05/S15) being done\n"
           "first -- without a facility list there is nothing to weight.",
}

SOURCE_MD = """# {sid} — {name}

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** {owner}  **Tier** {tier}  **Priority** {priority}  **Effort** {effort}
**Pillar** {pillar}  **Expected coverage** {coverage} / 500

## What it is
{what_is}

## What you get from it
{what_get}

## Feeds
{feeds}

## Access
| | |
|---|---|
| Method | {access} |
| Endpoint | {endpoint} |
| Auth | {auth} |
| Format | {fmt} |
| Packages | {pkgs} |

## Gotchas (from the register)
{gotchas}
{extra}
## Fields this package may emit
{fieldtable}

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.{slug}.test_smoke` passes on 10 tickers
- [ ] Coverage matches the {coverage}/500 expectation above, or you can say why not
{blocked}"""

BLOCKED_MD = """
## ⚠ BLOCKED — not cleanly pullable

{reason}

`pull()` raises `NotImplementedError` on purpose. The folder exists so the
coverage manifest reports *why* this source is empty instead of showing a
silent gap. If you unblock it, delete this section.
"""

PULL_PY = '''"""{sid} — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/{sid}/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database
"""

from __future__ import annotations

import argparse

from ...common import cache{sec_import}
from ...common.entities import tickers

SOURCE = "{sid}"
{endpoint_const}

def pull(ticker_list: list[str] | None = None, *, limit: int | None = None) -> dict:
    """Fetch raw material for `ticker_list` (default: the whole universe).

    Returns a small dict of counts for the run log.
    """
    ticker_list = ticker_list or tickers(limit)
{body}

def main() -> None:
    ap = argparse.ArgumentParser(description="{sid} pull")
    ap.add_argument("--tickers", help="comma-separated; default is the whole universe")
    ap.add_argument("--limit", type=int, help="first N tickers, for a smoke run")
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(pull(tl, limit=a.limit))


if __name__ == "__main__":
    main()
'''

EXTRACT_PY = '''"""{sid} — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

The canonical write pattern:

    from ...common.schema import Observation, Status
    from ...common.jsonl import ObservationWriter

    with ObservationWriter(SOURCE) as w:
        w.write(Observation(
            ticker="AAPL",
            field="revenue_usd",          # must exist in common/fields.py
            value=391035000000.0,
            unit="usd",                   # canonical token, converted already
            fiscal_year=2024,
            period_end="2024-09-28",
            quote=None,                   # structural facts carry no quote
            source=SOURCE,
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            source_section="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            extracted_by="xbrl:RevenueFromContractWithCustomerExcludingAssessedTax",
            status=Status.STRUCTURAL,
        ))
        print(w.summary())

For a number read out of prose, pass the source text and let the validator do
the work — it downgrades a bad quote to quote_failed rather than trusting it:

        w.write(obs, source_text=filing_text)

And when the company said nothing, SAY SO. Skipping the company loses the most
valuable signal in the dataset:

        w.write(Observation(..., value=None, unit=None, quote=None,
                            status=Status.NOT_DISCLOSED, ...))
"""

from __future__ import annotations

import argparse

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from .fields import EMITS

SOURCE = "{sid}"


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raise NotImplementedError(
                "{sid} extract() not implemented. See SOURCE.md in this folder. "
                "Emit only: " + ", ".join(EMITS)
            )
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="{sid} extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
'''

FIELDS_PY = '''"""Fields {sid} is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "{sid}"

EMITS = [
{emits}]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{{_f}} is not in common/fields.py -- add it there first"

SPECS = {{f.name: f for f in fields_for_source(SOURCE)}}
'''

SMOKE_PY = '''"""Smoke test for {sid}: 10 tickers, end to end, cheap.

    python -m pipeline.sources.{slug}.test_smoke

Run this BEFORE the full 500. A source that fails on 10 fails on 500 slower.
"""

from __future__ import annotations

from ...common.entities import tickers
from .fields import EMITS, SOURCE


def main() -> int:
    sample = tickers(10)
    print(f"{{SOURCE}}: smoke on {{len(sample)}} tickers -> {{', '.join(sample)}}")
    print(f"declared fields: {{', '.join(EMITS) or '(none)'}}")

    from .pull import pull
    from .extract import extract

    pull(sample)
    print(extract(sample))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _clean(v, default: str = "—") -> str:
    """Empty spreadsheet cells arrive as float('nan'); rendering that as 'nan'
    in a brief makes the brief look untrustworthy."""
    if v is None or (isinstance(v, float) and v != v):
        return default
    t = str(v).strip()
    if not t or t.lower() == "nan":
        return default
    return t.replace("|", "\\|")   # a raw pipe silently breaks the markdown table


def render(sid: str, row: dict, force: bool) -> None:
    slug = SLUGS[sid]
    pkg = SOURCES_DIR / slug
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(f'"""{sid} — {row["Source"]}"""\n\nSOURCE = "{sid}"\n')

    specs = fields_for_source(sid)
    fieldtable = "\n".join(
        f"| `{s.name}` | {s.unit or '—'} | {s.dtype.__name__} | {s.description.splitlines()[0]} |"
        for s in specs
    ) or "| _(none — this source feeds entity resolution or validation only)_ | | | |"
    fieldtable = ("| field | unit | type | what it is |\n|---|---|---|---|\n" + fieldtable)

    extra = EXTRA.get(sid)
    md = SOURCE_MD.format(
        sid=sid, name=_clean(row["Source"]), owner=_clean(row.get("Owner")),
        tier=_clean(row.get("Tier")), priority=_clean(row.get("Priority")),
        effort=_clean(row.get("Effort")), pillar=_clean(row.get("Pillar")),
        coverage=_clean(row.get("Est. coverage (of 500)"), "?"),
        what_is=_clean(row.get("What it is")), what_get=_clean(row.get("What you get from it")),
        feeds=_clean(row.get("Feeds indicators")), access=_clean(row.get("Access method")),
        endpoint=_clean(row.get("Endpoint or download URL")),
        auth=_clean(row.get("Auth"), "None required"),
        fmt=_clean(row.get("Format")), pkgs=_clean(row.get("Python / package")),
        gotchas=_clean(row.get("Gotchas & rate limits")),
        extra=f"\n## Notes from the planning session\n{extra}\n" if extra else "",
        fieldtable=fieldtable, slug=slug,
        blocked=BLOCKED_MD.format(reason=BLOCKED[sid]) if sid in BLOCKED else "",
    )
    p = pkg / "SOURCE.md"
    if force or not p.exists():
        p.write_text(md, encoding="utf-8")

    emits = "".join(f'    "{s.name}",\n' for s in specs)
    _write(pkg / "fields.py", FIELDS_PY.format(sid=sid, emits=emits), force)

    if sid in BLOCKED:
        body = (f'    raise NotImplementedError(\n'
                f'        "{sid} is not cleanly pullable. See SOURCE.md. "\n'
                f'        "{BLOCKED[sid].splitlines()[0]}"\n    )\n')
    else:
        body = ('    raise NotImplementedError(\n'
                f'        "{sid} pull() not implemented -- see SOURCE.md in this folder"\n'
                '    )\n')

    sec_import = ("\nfrom ...common.sec_client import get_client" if sid in SEC_SOURCES else "")
    endpoint = row.get("Endpoint or download URL", "")
    endpoint_const = (f'ENDPOINT = "{endpoint}"\n' if isinstance(endpoint, str)
                      and endpoint.startswith("http") else "")

    _write(pkg / "pull.py", PULL_PY.format(sid=sid, body=body, sec_import=sec_import,
                                           endpoint_const=endpoint_const), force)
    _write(pkg / "extract.py", EXTRACT_PY.format(sid=sid), force)
    _write(pkg / "test_smoke.py", SMOKE_PY.format(sid=sid, slug=slug), force)
    print(f"  {sid}  {slug:<26} {len(specs):>2} fields"
          + ("   [BLOCKED]" if sid in BLOCKED else ""))


#: Files a source package owns by hand. --force must never overwrite these;
#: losing hand-written tag chains to a regeneration is a silent, expensive bug.
HANDWRITTEN = {"tags.py", "parse.py", "rollup.py", "notes.md",
               "diagnose.py", "test_extract_fixture.py"}


def _write(path: Path, text: str, force: bool) -> None:
    if path.name in HANDWRITTEN:
        return
    if force or not path.exists():
        path.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="rewrite files even if they exist (loses agent edits)")
    a = ap.parse_args()

    df = pd.read_excel(REGISTER, "Data Sources").set_index("ID")
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    (SOURCES_DIR / "__init__.py").write_text('"""One package per in-scope data source."""\n')
    print(f"scaffolding {len(SLUGS)} source packages into {SOURCES_DIR}")
    for sid in SLUGS:
        render(sid, df.loc[sid].to_dict(), a.force)


if __name__ == "__main__":
    main()
