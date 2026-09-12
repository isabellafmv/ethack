"""Repo-root anchored paths, so nothing depends on the current working directory."""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA = REPO_ROOT / "data"
CACHE = REPO_ROOT / "cache"
CACHE_RAW = CACHE / "raw"            # L1: source + key -> bytes, never deleted
CACHE_EXTRACTED = CACHE / "extracted"  # L2: ticker + field -> json, cheap to delete
OBSERVATIONS = DATA / "observations"  # append-only JSONL, one dir per source
# The database lives OUTSIDE the repo on purpose. This repo sits in iCloud
# Drive, and SQLite on a synced filesystem fails with "disk I/O error" (file
# locking is not honoured). It is also a derived artifact -- rebuildable from
# the JSONL log in seconds -- so syncing it would be churn at best and a
# corrupted file at worst. Override with ETHACK_DB if you want it elsewhere.
DB_PATH = Path(os.environ.get(
    "ETHACK_DB", Path.home() / ".cache" / "ethack" / "scores.db"))
MATRIX_PATH = DATA / "matrix.json"
MANIFEST_PATH = DATA / "manifest.csv"
UNIVERSE_PATH = DATA / "sp500_companies.csv"


def ensure_dirs() -> None:
    for p in (DATA, CACHE, CACHE_RAW, CACHE_EXTRACTED, OBSERVATIONS):
        p.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
