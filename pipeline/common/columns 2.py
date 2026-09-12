"""Fuzzy column detection for third-party spreadsheets.

Every external file in this project — SBTi, EPA, Kaggle — renames its columns
between releases. Hard-coding a header means a release silently empties a field
for all 500 companies, which is the quietest failure in the whole pipeline.

So each source declares logical names with a list of patterns, and `detect`
reports what it matched. Longest pattern wins, so 'near term target year' beats
a bare 'year'.
"""

from __future__ import annotations

import re


def norm(header: str) -> str:
    """Lowercase, punctuation to spaces, runs of whitespace collapsed.

    The collapse is load-bearing: 'Near term - Target Status' becomes
    'near term   target status' without it, and no pattern matches.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(header).lower())).strip()


def detect(headers: list[str], columns: dict[str, list[str]]) -> dict[str, str | None]:
    """{logical name: actual header or None}."""
    normed = [(norm(h), h) for h in headers]
    out: dict[str, str | None] = {}
    for logical, patterns in columns.items():
        best, best_len = None, -1
        for pat in patterns:
            for n, original in normed:
                if pat in n and len(pat) > best_len:
                    best, best_len = original, len(pat)
        out[logical] = best
    return out


def report(detected: dict[str, str | None], required: list[str]) -> str | None:
    """Human-readable complaint if a required column is missing, else None."""
    missing = [k for k in required if not detected.get(k)]
    if not missing:
        return None
    return (f"missing required columns: {', '.join(missing)}. "
            f"Update the COLUMNS patterns for this source.")
