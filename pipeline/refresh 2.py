"""Rebuild every derived artifact from the JSONL log. Run it after any scrape.

The JSONL log under data/observations/ is the source of truth; scores.db,
wide.csv, the per-pillar files, matrix.json and manifest.csv are all derived
from it. That means any scraper -- S05, S15, whatever lands next -- only has to
write its JSONL and then this runs. No source package ever touches a CSV.

    python -m pipeline.refresh              # rebuild if the log changed
    python -m pipeline.refresh --force      # rebuild even if it did not
    python -m pipeline.refresh --watch      # sit there and rebuild on every scrape

`--watch` is the hands-off mode: leave it running in a second terminal, scrape
in the first, and wide.csv is current a few seconds after each source finishes.

Change detection is a fingerprint of (path, size, mtime) over every *.jsonl in
the log, stored in data/.refresh_state.json. A file that is still being written
is NOT picked up until its fingerprint has held still for one poll -- otherwise
we would read a half-flushed last line mid-scrape and reject the whole run.

Order is fixed and matters: load first (everything else reads the DB), then the
exports, which are independent of each other.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from .common.jsonl import all_runs
from .common.paths import DATA, DB_PATH, MANIFEST_PATH, MATRIX_PATH, ensure_dirs

STATE_PATH = DATA / ".refresh_state.json"


# --------------------------------------------------------------------------
# change detection
# --------------------------------------------------------------------------

def fingerprint() -> dict[str, list]:
    """(size, mtime) per JSONL file. Cheap -- a stat per file, no reads."""
    fp = {}
    for p in all_runs():
        try:
            st = p.stat()
        except FileNotFoundError:      # deleted between listing and stat
            continue
        fp[str(p)] = [st.st_size, round(st.st_mtime, 3)]
    return fp


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(fp: dict, artifacts: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(
        {"fingerprint": fp, "last_refresh": datetime.now().astimezone().isoformat(),
         "artifacts": artifacts},
        indent=1), encoding="utf-8")


def diff(old: dict, new: dict) -> tuple[list[str], list[str]]:
    """(new or changed files, disappeared files) -- for the log line."""
    changed = [p for p, v in new.items() if old.get(p) != v]
    gone = [p for p in old if p not in new]
    return changed, gone


# --------------------------------------------------------------------------
# the rebuild
# --------------------------------------------------------------------------

def _step(name: str, fn, quiet: bool) -> str:
    """Run one build step. Never let one broken export kill the rest -- a bad
    matrix.json should not cost you wide.csv."""
    buf = io.StringIO()
    t0 = time.monotonic()
    try:
        with contextlib.redirect_stdout(buf if quiet else sys.stdout):
            fn()
        note = "ok"
    except Exception as e:                                   # noqa: BLE001
        note = f"FAILED  {type(e).__name__}: {e}"
        if quiet:                       # the detail was swallowed -- show it
            sys.stdout.write(buf.getvalue())
    print(f"  {name:<16} {note:<40} {time.monotonic() - t0:5.1f}s")
    return note


def rebuild(year: int | None = None, quiet: bool = False) -> dict:
    """load -> wide -> per-pillar -> matrix -> manifest. Returns step results."""
    from . import export_matrix, export_wide, manifest
    from .load import build

    ensure_dirs()
    results = {}
    print(f"\nrebuilding derived artifacts  ({datetime.now():%H:%M:%S})")
    results["load"] = _step("scores.db", lambda: build(verbose=not quiet), quiet)
    results["wide"] = _step(
        "wide.csv", lambda: export_wide.export(DB_PATH, year, with_status=True), quiet)
    results["pillars"] = _step(
        "wide_P*.csv", lambda: export_wide.export_by_pillar(DB_PATH, year), quiet)
    results["matrix"] = _step(
        "matrix.json", lambda: export_matrix.export(DB_PATH, MATRIX_PATH), quiet)
    results["manifest"] = _step(
        "manifest.csv", lambda: manifest.write_csv(manifest.grid(DB_PATH)), quiet)
    return results


def artifact_sizes() -> dict[str, int]:
    out = {}
    for p in [DATA / "wide.csv", DATA / "wide_status.csv", DATA / "wide_P1.csv",
              DATA / "wide_P2.csv", DATA / "wide_P3.csv", DATA / "wide_X.csv",
              MATRIX_PATH, MANIFEST_PATH, DB_PATH]:
        if p.exists():
            out[p.name] = p.stat().st_size
    return out


def refresh_once(force: bool = False, year: int | None = None,
                 quiet: bool = False, settled: dict | None = None) -> bool:
    """Rebuild iff the log changed. Returns True if a rebuild happened."""
    fp = settled if settled is not None else fingerprint()
    old = load_state().get("fingerprint", {})
    changed, gone = diff(old, fp)

    if not force and not changed and not gone:
        print(f"no change in the observation log ({len(fp)} files) — nothing to do")
        return False

    if changed or gone:
        print(f"{len(changed)} new/changed run file(s)"
              + (f", {len(gone)} removed" if gone else ""))
        for p in changed[:8]:
            print(f"    + {Path(p).parent.name}/{Path(p).name}")
        if len(changed) > 8:
            print(f"    ... and {len(changed) - 8} more")
    elif force:
        print(f"--force: rebuilding from {len(fp)} run file(s) regardless")

    results = rebuild(year=year, quiet=quiet)
    failed = [k for k, v in results.items() if v != "ok"]
    if failed:
        # State is NOT saved on failure, so the next run retries the same input
        # instead of declaring the log already processed.
        print(f"\n  {len(failed)} step(s) failed: {', '.join(failed)} — state not saved, "
              f"fix and re-run")
        return True
    save_state(fp, artifact_sizes())
    print(f"\n  up to date — data/wide.csv and friends now reflect "
          f"{len(fp)} run file(s)")
    return True


def watch(interval: float = 10.0, year: int | None = None, quiet: bool = True) -> None:
    """Poll the log; rebuild once a change has stopped moving.

    The settle step is the important bit: a scraper appending to its JSONL
    shows a different size on every poll, so we wait for two identical reads
    before touching it. Worst case that costs one extra interval.
    """
    print(f"watching {DATA / 'observations'} every {interval:g}s — Ctrl-C to stop")
    refresh_once(force=False, year=year, quiet=quiet)
    pending: dict | None = None
    try:
        while True:
            time.sleep(interval)
            fp = fingerprint()
            old = load_state().get("fingerprint", {})
            if not diff(old, fp)[0] and not diff(old, fp)[1]:
                pending = None
                continue
            if pending != fp:           # still moving — let it finish
                pending = fp
                print(f"  {datetime.now():%H:%M:%S}  change detected, waiting for it to settle")
                continue
            refresh_once(force=False, year=year, quiet=quiet, settled=fp)
            pending = None
    except KeyboardInterrupt:
        print("\nstopped watching")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="rebuild scores.db, wide*.csv, matrix.json and manifest.csv "
                    "from the observation log")
    ap.add_argument("--watch", action="store_true",
                    help="keep running and rebuild after every scrape")
    ap.add_argument("--interval", type=float, default=10.0,
                    help="poll seconds in --watch mode (default 10)")
    ap.add_argument("--force", action="store_true",
                    help="rebuild even if the log has not changed")
    ap.add_argument("--year", type=int,
                    help="pin a fiscal year for the wide exports; default latest per company")
    ap.add_argument("--quiet", action="store_true",
                    help="one line per step instead of each exporter's full report")
    a = ap.parse_args()

    if a.watch:
        watch(a.interval, a.year, quiet=not a.force or a.quiet or True)
    else:
        refresh_once(force=a.force, year=a.year, quiet=a.quiet)


if __name__ == "__main__":
    main()
