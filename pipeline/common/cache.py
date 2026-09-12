"""Two cache layers, with different lifetimes and different owners.

L1 RAW      what came back over the wire, byte for byte, before any parsing.
            Keyed by source + a stable key (CIK, accession number, ticker).
            NEVER deleted -- re-running extraction must not re-hit an API.
            This is what lets `extract.py` run offline, forever, at hour 20
            when the wifi is off for the rehearsal.

L2 EXTRACTED  the result of an expensive extraction (an agent call), keyed by
            ticker + field. Cheap to delete: deleting it costs money and time
            but loses no ground truth, because L1 still holds the source.

If you find yourself wanting to clear L1 to "get fresh data", you want a new
run directory instead. L1 is an archive, not a performance optimisation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .paths import CACHE_RAW, CACHE_EXTRACTED


def _safe(key: str) -> str:
    """Filesystem-safe name that still reads like the original key."""
    clean = "".join(c if c.isalnum() or c in "-._" else "_" for c in key)[:80]
    digest = hashlib.sha256(key.encode()).hexdigest()[:10]
    return f"{clean}-{digest}"


# --- L1: raw --------------------------------------------------------------

def raw_path(source: str, key: str, suffix: str = ".bin") -> Path:
    d = CACHE_RAW / source
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_safe(key)}{suffix}"


def has_raw(source: str, key: str, suffix: str = ".bin") -> bool:
    return raw_path(source, key, suffix).exists()


def get_raw(source: str, key: str, suffix: str = ".bin") -> bytes | None:
    p = raw_path(source, key, suffix)
    return p.read_bytes() if p.exists() else None


def put_raw(source: str, key: str, data: bytes, suffix: str = ".bin") -> Path:
    p = raw_path(source, key, suffix)
    p.write_bytes(data)
    return p


def raw_text(source: str, key: str, suffix: str = ".bin", encoding: str = "utf-8") -> str | None:
    data = get_raw(source, key, suffix)
    return data.decode(encoding, errors="replace") if data is not None else None


# --- L2: extracted --------------------------------------------------------

def extracted_path(ticker: str, field: str) -> Path:
    d = CACHE_EXTRACTED / _safe(ticker)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_safe(field)}.json"


def get_extracted(ticker: str, field: str) -> Any | None:
    p = extracted_path(ticker, field)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def put_extracted(ticker: str, field: str, payload: Any) -> Path:
    p = extracted_path(ticker, field)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    return p


def cache_stats() -> dict[str, int]:
    raw = sum(1 for _ in CACHE_RAW.rglob("*")) if CACHE_RAW.exists() else 0
    ext = sum(1 for _ in CACHE_EXTRACTED.rglob("*.json")) if CACHE_EXTRACTED.exists() else 0
    return {"raw_files": raw, "extracted_records": ext}
