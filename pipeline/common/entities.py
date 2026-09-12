"""Ticker <-> CIK <-> legal name. The prerequisite for every facility source.

The rule from the plan doc: match within a CONSTRAINING CONTEXT -- state, SIC,
address -- never on name alone. 'Delta' is an airline, a faucet manufacturer
and a dental plan. 'Apache' is an oil company and a software foundation.

Four layers, in order of trust:
  1. Exhibit 21 subsidiary lists (S05)  -- the registrant's own account
  2. GHGRP parent file (S15)            -- has ownership percentages
  3. GLEIF Level 2 (S06)                -- self-declared, exemptions allowed
  4. normalised string match, reviewed  -- last resort, always flagged
"""

from __future__ import annotations

import csv
import functools
import re

from .paths import UNIVERSE_PATH

_SUFFIXES = (
    "incorporated", "corporation", "company", "limited", "holdings", "holding",
    "group", "plc", "inc", "corp", "co", "ltd", "llc", "lp", "llp", "nv", "sa",
    "ag", "the", "and", "classa", "classb", "classc",
)


def normalise_name(name: str) -> str:
    """Aggressive normalisation for MATCHING only. Never store this as the
    legal name -- it is lossy on purpose."""
    s = re.sub(r"[^\w\s]", " ", (name or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    tokens = [t for t in s.split() if t not in _SUFFIXES]
    return " ".join(tokens) or s


@functools.lru_cache(maxsize=1)
def universe() -> list[dict]:
    """The frozen S&P 500 list. Freeze it once and commit it: membership
    changes mid-build silently break joins."""
    if not UNIVERSE_PATH.exists():
        raise FileNotFoundError(
            f"{UNIVERSE_PATH} missing. Run S&P_scrape.py (or s08_universe) first -- "
            f"every other source joins on it."
        )
    with UNIVERSE_PATH.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


#: Wikipedia sometimes lists a company's NEWEST registrant number rather than
#: the one carrying its filing history. A re-registration or holding-company
#: reshuffle creates a fresh CIK with only 10-Qs behind it, and the decades of
#: annual filings stay under the old one. Overriding here fixes pull and extract
#: together, because both resolve the CIK through this function.
#:
#: Each entry needs a reason. An unexplained CIK override is indistinguishable
#: from a typo six hours later.
CIK_OVERRIDES: dict[str, tuple[str, str]] = {
    # ticker: (cik, why)
    "XOM": ("0000034088",
            "Wikipedia lists 2115436 ('Exxon Mobil Corporation', 10-Q only, "
            "registered 2025). The 10-K history is under 34088."),
}


@functools.lru_cache(maxsize=1)
def ticker_to_cik() -> dict[str, str]:
    from .sec_client import pad_cik
    out = {r["ticker"]: pad_cik(r["cik"]) for r in universe() if r.get("cik")}
    for ticker, (cik, _why) in CIK_OVERRIDES.items():
        if ticker in out:
            out[ticker] = pad_cik(cik)
    return out


@functools.lru_cache(maxsize=1)
def cik_to_ticker() -> dict[str, str]:
    return {v: k for k, v in ticker_to_cik().items()}


@functools.lru_cache(maxsize=1)
def name_index() -> dict[str, str]:
    return {normalise_name(r["company"]): r["ticker"] for r in universe()}


@functools.lru_cache(maxsize=1)
def despaced_index() -> dict[str, str]:
    """Normalised names with spaces removed.

    EPA files carry legal names ('EXXON MOBIL CORP') while the constituent list
    carries trading names ('ExxonMobil'). After suffix-stripping those are
    'exxon mobil' and 'exxonmobil' — a mismatch on one space, which loses the
    single most carbon-material company in the index. Removing spaces is a
    narrow, deterministic fallback; it is NOT fuzzy matching and still requires
    every other character to agree.
    """
    return {normalise_name(r["company"]).replace(" ", ""): r["ticker"]
            for r in universe()}


def match_exact(name: str) -> str | None:
    """Ticker for a legal name, exact then space-insensitive. No fuzz."""
    n = normalise_name(name)
    return name_index().get(n) or despaced_index().get(n.replace(" ", ""))


@functools.lru_cache(maxsize=1)
def sectors() -> dict[str, str]:
    return {r["ticker"]: r["sector"] for r in universe()}


def tickers(limit: int | None = None) -> list[str]:
    t = [r["ticker"] for r in universe()]
    return t[:limit] if limit else t


def match_name(name: str, *, state: str | None = None, min_score: int = 88) -> tuple[str | None, int]:
    """Fuzzy match a legal name to a ticker. Returns (ticker, score).

    `state` is not optional in spirit: passing it is what separates a match
    from a coincidence. A match made without any constraining context should be
    written with status=imputed, never quote_verified.
    """
    exact = name_index().get(normalise_name(name))
    if exact:
        return exact, 100

    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return None, 0

    pool = name_index()
    if state:
        allowed = {normalise_name(r["company"]) for r in universe()
                   if state.lower() in (r.get("headquarters", "") or "").lower()}
        pool = {k: v for k, v in pool.items() if k in allowed} or pool

    if not pool:
        return None, 0
    hit = process.extractOne(normalise_name(name), list(pool), scorer=fuzz.token_sort_ratio)
    if hit and hit[1] >= min_score:
        return pool[hit[0]], int(hit[1])
    return None, int(hit[1]) if hit else 0
