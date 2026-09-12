"""One command for the structural layer: pull, extract, load, report.

Structural = machine-readable sources that need no LLM extraction and no PDF
parsing. These are cheap, complete, and they fill the denominators every other
indicator divides by, so they go first.

    export SEC_USER_AGENT="ETH Hackathon Team you@example.com"
    python -m pipeline.run_structural --limit 10     # smoke on 10 companies
    python -m pipeline.run_structural                # all 500

One source failing never stops the others: each is reported and the run
continues. Re-running is cheap — everything already fetched is cached.
"""

from __future__ import annotations

import argparse
import importlib
import time

# Order matters: the universe is the join key for everything after it.
STRUCTURAL = [
    ("S08", "s08_universe", "frozen constituent list — CIK, sector, HQ"),
    ("S01", "s01_sec_xbrl", "XBRL financials — 11 fields, the denominators"),
    ("S07", "s07_market", "market cap + shares (bubble size)"),
    ("S14", "s14_kaggle_esg", "external ESG ratings — VALIDATION ONLY"),
    ("S09", "s09_sbti", "SBTi targets — the affordability numerator"),
    ("S15", "s15_epa_ghgrp", "EPA-measured Scope 1 — the only measured emissions"),
]


def run_one(sid: str, slug: str, tickers, limit, skip_pull: bool) -> tuple[str, str]:
    mod = f"pipeline.sources.{slug}"
    try:
        if not skip_pull:
            importlib.import_module(f"{mod}.pull").pull(tickers, limit=limit)
        out = importlib.import_module(f"{mod}.extract").extract(tickers, limit=limit)
        # "ok" must mean data arrived. A source that ran cleanly and wrote
        # nothing is failure mode #1 (silent partial failure) wearing a green
        # tick, so it gets its own status.
        if "wrote 0 records" in out or "nothing cached" in out:
            return "ran, no data", out
        return "ok", out
    except ModuleNotFoundError as e:
        return "missing dependency", f"{e}. Install it and re-run just this source."
    except Exception as e:                          # noqa: BLE001
        return "failed", f"{type(e).__name__}: {e}"


def main() -> None:
    ap = argparse.ArgumentParser(description="run the structural sources end to end")
    ap.add_argument("--tickers", help="comma-separated subset")
    ap.add_argument("--limit", type=int, help="first N companies — use 10 for a smoke run")
    ap.add_argument("--only", help="comma-separated source IDs, e.g. S01,S07")
    ap.add_argument("--skip-pull", action="store_true",
                    help="extract from the existing cache only, no network")
    a = ap.parse_args()

    tl = a.tickers.split(",") if a.tickers else None
    only = {s.strip().upper() for s in a.only.split(",")} if a.only else None
    results = {}

    for sid, slug, what in STRUCTURAL:
        if only and sid not in only:
            continue
        print(f"\n{'=' * 66}\n{sid}  {what}\n{'=' * 66}")
        t0 = time.monotonic()
        status, out = run_one(sid, slug, tl, a.limit, a.skip_pull)
        print(out)
        results[sid] = (status, time.monotonic() - t0)

    print(f"\n{'=' * 66}\nload\n{'=' * 66}")
    from .load import build
    build()

    print(f"\n{'=' * 66}\nsummary\n{'=' * 66}")
    for sid, (status, secs) in results.items():
        print(f"  {sid}  {status:<20} {secs:5.1f}s")
    bad = [s for s, (st, _) in results.items() if st != "ok"]
    if bad:
        print(f"\n  {len(bad)} source(s) need attention: {', '.join(bad)}")
    print("\nnext:  python -m pipeline.manifest --csv     # coverage by field and sector")
    print("       python -m pipeline.export_matrix       # JSON for the dashboard")


if __name__ == "__main__":
    main()
