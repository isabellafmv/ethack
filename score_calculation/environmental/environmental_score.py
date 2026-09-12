"""Environmental & Resource Efficiency pillar score: carbon intensity,
energy mix, resource & waste intensity, and input & operational efficiency,
combined into one weighted score.

Reads Isabella's pipeline output directly (data/wide_FY2025_fallback.csv --
see pipeline/export_wide.py), the same source transition_score.py and
governance_score.py use.

Only ONE of the four spec indicators has real data right now:

- input_efficiency_score: mean of (COGS/revenue) and (energy cost/revenue),
  each ranked as a percentile within the company's own GICS sector, against
  a distribution built from real (not modelled) peer values only -- lower
  cost intensity scores higher. energy_cost_usd has almost no coverage
  (17/500) so most companies are scored on COGS alone; the
  mean-of-available-components pattern (same as governance_score.py) means
  that's not a penalty, just a narrower basis.
- carbon_intensity_score, energy_mix_score, resource_waste_score:
  architecture is here, but every company scores null on all three.
  carbon_intensity_score specifically was tried and DROPPED, not just
  never built: for the ~374 companies with no measured GHGRP data,
  transition_score.py's modelled-emissions estimate is
  `sector_benchmark x company_revenue` -- dividing that back by the same
  revenue to get an intensity just reconstructs `sector_benchmark`, a
  constant. Every modelled company in a sector ends up with the identical
  intensity value, so a "percentile within sector" is meaningless for them
  (it's not a per-company signal, just the sector average wearing one).
  That's fine for transition_score.py's carbon_price_exposure_score, which
  divides by EBITDA instead of revenue (independent of the modelled
  estimate's construction, so it still varies per company) -- but not here.
  Reviving this indicator needs either real Scope 1+2 coverage broad enough
  to drop the modelled fallback, or a genuinely different per-company
  denominator. energy_mix_score needs S20 (EIA 860/923) or S21 (Green Power
  Partnership); resource_waste_score needs S16 (EPA TRI), S17 (EPA RSEI),
  or S26 (WRI Aqueduct) -- none pulled. The spec itself expects resource &
  waste to stay sparse even at full build (manufacturing/mining only,
  ~120/500 estimated).

A company's final score is a weighted average over whichever sub-scores it
actually has (renormalized), never a silent worst-case default for a
missing one -- same pattern as transition_score.py and governance_score.py.
"""
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
WIDE_PATH = DATA_DIR / "wide_FY2025_fallback.csv"
OUTPUT_PATH = DATA_DIR / "environmental_scores.csv"

# Provisional -- revisit once carbon_intensity/energy_mix/resource_waste
# actually have data worth weighting.
WEIGHTS = {
    "input_efficiency_score": 0.40,
    "carbon_intensity_score": 0.20,
    "energy_mix_score": 0.20,
    "resource_waste_score": 0.20,
}


def _sector_percentile_vs_measured(df: pd.DataFrame, value_col: str, measured_mask: pd.Series) -> pd.Series:
    """For each company, what fraction of its OWN SECTOR'S measured peers
    have a value <= its value -- i.e. its percentile against real data only.
    A sector with zero measured peers has no distribution to rank against,
    so it's left null (handled by the caller, same "no data" contract as
    everywhere else in this project -- never defaulted to a guessed rank).
    """
    result = pd.Series(np.nan, index=df.index, dtype=float)
    for sector, idx in df.groupby("sector").groups.items():
        reference = df.loc[idx][measured_mask.loc[idx]][value_col].dropna()
        if reference.empty:
            continue
        sorted_ref = np.sort(reference.to_numpy())
        for i in idx:
            v = df.at[i, value_col]
            if pd.isna(v):
                continue
            result.at[i] = np.searchsorted(sorted_ref, v, side="right") / len(sorted_ref)
    return result


def _input_efficiency_score(df: pd.DataFrame) -> pd.Series:
    df["cogs_intensity_pct"] = 100 * df["cogs_usd"] / df["revenue_usd"]
    df["energy_cost_intensity_pct"] = 100 * df["energy_cost_usd"] / df["revenue_usd"]
    has_cogs = df["cogs_intensity_pct"].notna()
    has_energy = df["energy_cost_intensity_pct"].notna()

    cogs_pctile = _sector_percentile_vs_measured(df, "cogs_intensity_pct", has_cogs)
    energy_pctile = _sector_percentile_vs_measured(df, "energy_cost_intensity_pct", has_energy)

    components = pd.concat([100 * (1 - cogs_pctile), 100 * (1 - energy_pctile)], axis=1)
    return components.mean(axis=1, skipna=True)


def _carbon_intensity_score(df: pd.DataFrame) -> pd.Series:
    """Dropped -- see the module docstring. Reviving this needs real Scope
    1+2 coverage broad enough to retire the modelled (sector-average x
    revenue) fallback, since dividing that fallback back by revenue just
    reconstructs the sector constant it was built from.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def _energy_mix_score(df: pd.DataFrame) -> pd.Series:
    """Share of electricity from low-carbon sources (S20 EIA 860/923 for
    utilities, S21 Green Power Partnership for others). Not pulled yet.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def _resource_waste_score(df: pd.DataFrame) -> pd.Series:
    """RSEI toxicity-weighted score (S17) and water stress-weighted
    withdrawal (S16/S26). Not pulled yet -- and per the spec, expected to
    stay sparse (manufacturing/mining only, ~120/500) even once it is.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def compute_environmental_scores() -> pd.DataFrame:
    df = pd.read_csv(WIDE_PATH)

    df["input_efficiency_score"] = _input_efficiency_score(df)
    df["carbon_intensity_score"] = _carbon_intensity_score(df)
    df["energy_mix_score"] = _energy_mix_score(df)
    df["resource_waste_score"] = _resource_waste_score(df)

    sub_cols = list(WEIGHTS)
    weights = pd.Series(WEIGHTS)
    available = df[sub_cols].notna()
    weight_matrix = available * weights
    weight_sum = weight_matrix.sum(axis=1)

    df["environmental_score"] = (df[sub_cols].fillna(0) * weight_matrix).sum(axis=1) / weight_sum
    df["n_indicators_available"] = available.sum(axis=1)
    df.loc[weight_sum == 0, "environmental_score"] = pd.NA

    columns = [
        "ticker", "company", "sector",
        "revenue_usd", "cogs_usd", "energy_cost_usd",
        *sub_cols, "n_indicators_available", "environmental_score",
    ]
    return df[columns]


if __name__ == "__main__":
    result = compute_environmental_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    scored = result["environmental_score"].notna().sum()
    print(f"Scored {scored}/{len(result)} companies.")
    print("Indicators available per company:")
    print(result["n_indicators_available"].value_counts().sort_index())
    print()
    print(result["environmental_score"].describe())
    print(f"\nSaved to {OUTPUT_PATH}")
