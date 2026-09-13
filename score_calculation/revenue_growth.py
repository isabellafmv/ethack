"""Revenue CAGR per company, 2021 -> 2025, straight from the observations
database rather than any wide export.

Every wide export (data/wide_FY2025_fallback.csv, web/public/data/matrix.json)
pins each field to ONE fiscal year per company -- exactly what makes them
usable as a single flat table, and exactly why neither can answer "how has
this company's revenue moved over time." That history was never dropped,
though: the database still carries every (ticker, field, fiscal_year) triple
S01 ever wrote, one row per year, so a multi-year read has to go around the
wide export and query it directly -- see pipeline/common/schema.py for why
fiscal_year is part of the observations table's own primary key.

Written for the bonus $1B-portfolio page (web/src/components/
PortfolioAllocator.tsx), which needs a growth signal matrix.json can't
supply. Kept as its own small file/script rather than folded into
score_calculation/final_score.py or one of the three pillar files: this
isn't a sustainability sub-score, it's a fundamentals input, and mixing it
into a pillar file would misfile it under the wrong methodology.

    python -m score_calculation.revenue_growth
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path.home() / ".cache" / "ethack" / "scores.db"
OUTPUT_PATH = PROJECT_ROOT / "web" / "public" / "data" / "revenue_growth.json"

START_YEAR = 2021
END_YEAR = 2025


def compute_revenue_cagr() -> pd.Series:
    con = sqlite3.connect(DB_PATH)
    query = (
        "SELECT ticker, fiscal_year, value_num FROM observations "
        f"WHERE field='revenue_usd' AND fiscal_year IN ({START_YEAR}, {END_YEAR})"
    )
    rev = pd.read_sql(query, con)
    con.close()

    # A ticker can carry more than one observation for the same fiscal year
    # (a teammate's parallel pull under a "~team" source suffix, see
    # pipeline/load.py) -- averaging collapses that to one number per
    # (ticker, year) rather than picking one arbitrarily.
    rev = rev.groupby(["ticker", "fiscal_year"], as_index=False)["value_num"].mean()
    pivot = rev.pivot(index="ticker", columns="fiscal_year", values="value_num")

    valid = pivot[START_YEAR].notna() & pivot[END_YEAR].notna() & (pivot[START_YEAR] > 0)
    years = END_YEAR - START_YEAR
    cagr = (100 * ((pivot[END_YEAR] / pivot[START_YEAR]) ** (1 / years) - 1)).where(valid)
    return cagr.rename("revenue_cagr_pct")


if __name__ == "__main__":
    cagr = compute_revenue_cagr()
    payload = {ticker: round(v, 4) for ticker, v in cagr.items() if not math.isnan(v)}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(payload, f)

    print(f"Revenue CAGR ({START_YEAR}->{END_YEAR}): {len(payload)}/{len(cagr)} companies.")
    print(f"Saved to {OUTPUT_PATH}")
