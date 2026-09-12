"""S14 — Sustainalytics-derived ESG risk ratings. VALIDATION ONLY.

This is the thing we are trying to beat. It must never become an input to a
pillar score; `common/fields.py` marks both its fields VALIDATION_ONLY and
`export_matrix.py` strips them from the browser payload.

No API needed: drop the CSV in data/ and this finds it. A copy is already in the
repo as 'SP 500 ESG Risk Ratings.csv'.
"""

from __future__ import annotations

import argparse

from ...common import cache
from ...common.paths import DATA

SOURCE = "S14"
ENDPOINT = "https://www.kaggle.com/datasets (search 'S&P 500 ESG Risk Ratings')"
CANDIDATES = ["SP 500 ESG Risk Ratings.csv", "sp500_esg_risk_ratings.csv",
              "S&P 500 ESG Risk Ratings.csv"]


def find_csv():
    for name in CANDIDATES:
        p = DATA / name
        if p.exists():
            return p
    hits = sorted(DATA.glob("*ESG*Risk*.csv")) + sorted(DATA.glob("*esg*risk*.csv"))
    return hits[0] if hits else None


def pull(ticker_list=None, *, limit=None, verbose: bool = True) -> dict:
    src = find_csv()
    if src is None:
        raise FileNotFoundError(
            f"No ESG ratings CSV in {DATA}. Download it from {ENDPOINT} and save "
            f"it there as 'SP 500 ESG Risk Ratings.csv'. VALIDATION ONLY -- it is "
            f"never an input to a score."
        )
    try:
        data = src.read_bytes()
    except OSError as e:
        raise OSError(
            f"Could not read {src.name}: {e}. If this repo is in iCloud Drive the "
            f"file may be a placeholder that has not downloaded -- open it once in "
            f"Finder, or run: brctl download '{src}'"
        ) from e
    cache.put_raw(SOURCE, "esg_risk_ratings", data, ".csv")
    if verbose:
        print(f"[S14] cached {src.name} ({len(data) / 1024:.0f} KB)")
    return {"path": str(src), "bytes": len(data)}


def main() -> None:
    argparse.ArgumentParser(description="S14 cache the ratings CSV").parse_args()
    pull()


if __name__ == "__main__":
    main()
