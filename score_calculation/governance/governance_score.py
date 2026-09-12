"""Governance & Capital Stewardship pillar score: climate governance,
compensation alignment, board independence & structure, capital stewardship,
and controversy/enforcement record, combined into one weighted score.

Reads Isabella's pipeline output directly (data/wide_FY2025_fallback.csv --
see pipeline/export_wide.py), the same source transition_score.py uses.

Four of the five spec indicators now have real data (S04 proxy extraction
landed); only controversy/enforcement is still unbuilt:

- capital_stewardship_score: real, computed from XBRL (S01). Reinvestment
  share = (capex + R&D) / (capex + R&D + buybacks + dividends) -- the spec's
  own framing ("ship the discrepancy, not the level"): a company plowing
  money back into the business scores high, one mostly returning it to
  shareholders scores low. Needs capex_usd on record; buybacks/dividends/R&D
  default to 0 when absent, because those are genuinely optional line items
  (a company with no buyback program simply omits the XBRL tag -- unlike
  EBITDA or revenue, where absence means a data gap, not a real zero. See
  score_calculation/transition/transition_score.py's regulatory_momentum_score
  for the case where that same fillna(0) assumption used to be WRONG.)
- climate_governance_score: mean of whichever of has_climate_oversight_
  committee / has_third_party_assurance / emissions_boundary_stated a
  company has (S04). Coverage is low (~45-60/500 each) -- these are a
  low-recall extraction rule (`concept_not_found_low_recall`), so a null here
  skews toward "we couldn't tell" more than the other sub-scores do.
  comp_tied_to_emissions_target is in the spec's four booleans but S04
  doesn't emit it at all, so it's excluded rather than silently scored as
  false.
- compensation_alignment_score: mean of has_clawback_policy / has_psu_plan
  (both ~495/500, high-confidence booleans) and performance_period_years
  (capped at 3 years -> 100; longer LTI performance periods reward
  longer-term thinking, per the spec).
- board_independence_score: mean of (independent directors / board size) and
  whether a lead independent director is named. The ratio is the weaker of
  the two on coverage (135/500 -- needs both `independent_director_count`
  and `board_size` trusted for the same company).
- controversy_score: architecture is here, but still null for everyone --
  S11 (Violation Tracker) has no public API and S18/S28/S29 haven't been
  pulled. NOT `esg_controversy_level_external` (S14): that field is
  validation-only by contract and must never enter a pillar score.

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
    """Mean of whichever of the 3 available booleans a company has -- never
    all 4 of the spec's, since S04 doesn't emit comp_tied_to_emissions_target.
    """
    components = pd.concat([
        df["has_climate_oversight_committee"] * 100,
        df["has_third_party_assurance"] * 100,
        df["emissions_boundary_stated"] * 100,
    ], axis=1)
    return components.mean(axis=1, skipna=True)


def _compensation_alignment_score(df: pd.DataFrame) -> pd.Series:
    """Mean of has_clawback_policy, has_psu_plan, and performance_period_years
    (capped at 3 years -> 100, since a longer LTI period rewards long-term
    thinking and 3+ years is already a strong signal -- more isn't better).
    """
    performance_component = (df["performance_period_years"].clip(upper=3) / 3 * 100)
    components = pd.concat([
        df["has_clawback_policy"] * 100,
        df["has_psu_plan"] * 100,
        performance_component,
    ], axis=1)
    return components.mean(axis=1, skipna=True)


def _board_independence_score(df: pd.DataFrame) -> pd.Series:
    """Mean of (independent directors / board size) and whether a lead
    independent director is named. Needs board_size > 0 for the ratio half.
    """
    ratio_component = (100 * df["independent_director_count"] / df["board_size"]).where(df["board_size"] > 0)
    lead_component = df["lead_independent_director"] * 100
    components = pd.concat([ratio_component, lead_component], axis=1)
    return components.mean(axis=1, skipna=True)


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
