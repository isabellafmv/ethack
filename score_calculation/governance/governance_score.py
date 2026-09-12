"""Governance & Capital Stewardship pillar score: climate governance,
compensation alignment, board independence & structure, capital stewardship,
and controversy/enforcement record, combined into one weighted score.

Reads Isabella's pipeline output directly (data/wide_FY2025_fallback.csv --
see pipeline/export_wide.py), the same source transition_score.py uses.

Right now only ONE of the five spec indicators has any real data:

- capital_stewardship_score: real, computed from XBRL (S01). Reinvestment
  share = (capex + R&D) / (capex + R&D + buybacks + dividends) -- the spec's
  own framing ("ship the discrepancy, not the level"): a company plowing
  money back into the business scores high, one mostly returning it to
  shareholders scores low. Needs capex_usd on record; buybacks/dividends/R&D
  default to 0 when absent, because those are genuinely optional line items
  (a company with no buyback program simply omits the XBRL tag -- unlike
  EBITDA or revenue, where absence means a data gap, not a real zero. See
  score_calculation/transition/transition_score.py's regulatory_momentum_score
  for the case where that same fillna(0) assumption is WRONG.)
- climate_governance_score, compensation_alignment_score,
  board_independence_score, controversy_score: architecture is here, but
  every company scores null on all four -- S04 (DEF 14A proxy text) and
  S11/S18 (enforcement records) haven't been pulled at all yet. Wiring them
  up once those land means filling in the four `_score` functions below;
  nothing else changes.

A company's final score is a weighted average over whichever sub-scores it
actually has (renormalized), never a silent worst-case default for a missing
one -- see WEIGHTS and the todo item this was written to fix.
"""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
WIDE_PATH = DATA_DIR / "wide_FY2025_fallback.csv"
OUTPUT_PATH = DATA_DIR / "governance_scores.csv"

# Provisional -- revisit once climate_governance/compensation/board/controversy
# actually have data to look at. Board independence is deliberately the
# lowest weight per the spec's own note: real and easy to pull, but weakly
# related to sustainability -- a judge will ask why it's here at all if it's
# not.
WEIGHTS = {
    "capital_stewardship_score": 0.25,
    "climate_governance_score": 0.25,
    "compensation_alignment_score": 0.15,
    "board_independence_score": 0.10,
    "controversy_score": 0.25,
}


def _capital_stewardship_score(df: pd.DataFrame) -> pd.Series:
    capex = df["capex_usd"]
    rnd = df["rnd_expense_usd"].fillna(0)
    buybacks = df["buybacks_usd"].fillna(0)
    dividends = df["dividends_paid_usd"].fillna(0)

    reinvestment = capex + rnd
    total = reinvestment + buybacks + dividends
    score = 100 * reinvestment / total

    # Needs a real capex figure and a non-zero denominator to mean anything;
    # everything else here is allowed to be a real zero.
    score = score.where(capex.notna() & (total > 0))
    return score


def _climate_governance_score(df: pd.DataFrame) -> pd.Series:
    """4 DEF 14A booleans (S04): climate-oversight committee, comp tied to
    emissions target, third-party assurance, boundary stated. Not pulled yet.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def _compensation_alignment_score(df: pd.DataFrame) -> pd.Series:
    """PSUs, multi-year performance periods, clawback provisions (S04).
    Not pulled yet.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def _board_independence_score(df: pd.DataFrame) -> pd.Series:
    """Independent director count / board size, lead independent director
    (S04). Not pulled yet.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def _controversy_score(df: pd.DataFrame) -> pd.Series:
    """Penalty totals/counts from court and agency records (S11/S18/S28/S29).
    Not pulled yet -- and NOT `esg_controversy_level_external` (S14): that
    field is validation-only by contract (pipeline/common/fields.py -- "this
    is the thing we are trying to beat") and must never enter a pillar score.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def compute_governance_scores() -> pd.DataFrame:
    df = pd.read_csv(WIDE_PATH)

    df["capital_stewardship_score"] = _capital_stewardship_score(df)
    df["climate_governance_score"] = _climate_governance_score(df)
    df["compensation_alignment_score"] = _compensation_alignment_score(df)
    df["board_independence_score"] = _board_independence_score(df)
    df["controversy_score"] = _controversy_score(df)

    sub_cols = list(WEIGHTS)
    weights = pd.Series(WEIGHTS)
    available = df[sub_cols].notna()
    weight_matrix = available * weights
    weight_sum = weight_matrix.sum(axis=1)

    df["governance_score"] = (df[sub_cols].fillna(0) * weight_matrix).sum(axis=1) / weight_sum
    df["n_indicators_available"] = available.sum(axis=1)
    df.loc[weight_sum == 0, "governance_score"] = pd.NA

    columns = [
        "ticker", "company", "sector",
        "capex_usd", "rnd_expense_usd", "buybacks_usd", "dividends_paid_usd",
        *sub_cols, "n_indicators_available", "governance_score",
    ]
    return df[columns]


if __name__ == "__main__":
    result = compute_governance_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    scored = result["governance_score"].notna().sum()
    print(f"Scored {scored}/{len(result)} companies (rest have zero available indicators).")
    print("Indicators available per company:")
    print(result["n_indicators_available"].value_counts().sort_index())
    print()
    print(result["governance_score"].describe())
    print(f"\nSaved to {OUTPUT_PATH}")
