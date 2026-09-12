"""Transition pillar score: carbon-price exposure, sector structural
exposure, innovation & regulatory momentum, and transition affordability,
combined into one weighted score.

Each sub-metric is built from real, per-company or bottom-up sector data
(see score_calculation/transition/data_sources/*) rather than hand-picked
constants:

- carbon_price_exposure_score: modeled EBITDA erosion under an assumed
  carbon price. Uses REAL, ownership-weighted EPA GHGRP facility emissions
  for companies with a matched parent-company record ("measured" tier,
  ~1/5 of the index per data_sources/epa_ghgrp_company_matches.py); falls
  back to a sector emissions-intensity benchmark x the company's own EDGAR
  revenue for everyone else ("modelled" tier). emissions_source_tier records
  which applies per company.
- sector_exposure_score: how structurally carbon-intensive the company's
  GICS sector is, ranked from the same GHGRP-derived intensity benchmark.
- regulatory_momentum_score: SBTi target tier (real, disclosed) blended with
  R&D intensity from EDGAR (real). Patent-based innovation signal (USPTO
  PatentsView Y02 share) from the spec is NOT included yet -- PatentsView
  requires a free API key and wasn't reachable from this environment; this
  is a known, explicit gap rather than a silently-dropped indicator.
- transition_affordability_score: whether the company can plausibly fund
  the transition implied by its own SBTi target (or, absent one, a
  sector-median counterfactual target -- see _sector_counterfactual_target).
  Formula: ((current emissions x target reduction %) x sector abatement
  cost/tonne / years to target) / free cash flow. This is the single
  riskiest number in the pillar -- it multiplies three uncertain inputs
  (an estimated emissions figure, a sector-average abatement cost, and an
  implied-not-disclosed reduction %). Spot-check extreme values before
  trusting them.

WEIGHTS below are provisional -- intended to be reviewed against the raw
sub-scores (all kept in the output CSV) before being finalized.
"""
from pathlib import Path

import pandas as pd

from score_calculation.transition.sector_assumptions import (
    DEFAULT_ABATEMENT_COST_USD_PER_TCO2E,
    SECTOR_ABATEMENT_COST_USD_PER_TCO2E,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
# Isabella's pipeline output: one row per company, fallback-filled to FY2025
# (falls back to the latest available year per field rather than dropping a
# company for being off-year -- see pipeline/export_wide.py).
WIDE_PATH = DATA_DIR / "wide_FY2025_fallback.csv"
OUTPUT_PATH = DATA_DIR / "transition_scores.csv"

# SBTi target ambition -> momentum score. Isabella's field contract only
# distinguishes three tiers (commitment / near-term / net-zero), coarser than
# the old 1.5C-vs-2C split this used to have -- there's no data to support
# that finer split anymore.
MOMENTUM_SCORES = {
    "no_target": 0,
    "committed": 25,
    "near_term_set": 75,
    "net_zero_validated": 100,
}

ASSUMED_CARBON_PRICE_USD_PER_TON = 100.0
CURRENT_YEAR = 2024  # anchor for "years to target"; matches the EDGAR/GHGRP vintage in use

# % EBITDA / FCF erosion at/above which the respective score bottoms out at 0.
CARBON_PRICE_EROSION_CEILING_PCT = 50.0
AFFORDABILITY_COST_CEILING_PCT = 100.0

RND_INTENSITY_CAP_PCT = 15.0  # R&D/revenue at/above which the R&D component maxes out (roughly top-decile tech/pharma)

# Provisional -- revisit once the raw sub-scores have been reviewed.
WEIGHTS = {
    "carbon_price_exposure_score": 0.30,
    "sector_exposure_score": 0.15,
    "regulatory_momentum_score": 0.25,
    "transition_affordability_score": 0.30,
}

# Blend within regulatory_momentum_score: disclosed SBTi commitment vs. R&D
# spend as a proxy for innovation capacity (patents would sit here too, once available).
MOMENTUM_SUBWEIGHTS = {"sbti": 0.7, "rnd_intensity": 0.3}


def _ceiling_score(pct_of_base: pd.Series, ceiling_pct: float) -> pd.Series:
    """Map a %-of-base erosion/cost figure to a 0-100 score, 0% -> 100, >=ceiling -> 0."""
    clipped = pct_of_base.clip(lower=0, upper=ceiling_pct)
    return 100 * (1 - clipped / ceiling_pct)


def _build_sector_intensity(df: pd.DataFrame) -> pd.DataFrame:
    """Sector-level tCO2e/$mm-revenue benchmark, built live from whichever
    companies in `df` have a real (GHGRP-measured) scope1_tco2e -- replaces
    the old hand-built epa_sector_emissions.csv with the same companies the
    rest of the pipeline already pulled.
    """
    measured = df.dropna(subset=["scope1_tco2e", "revenue_usd"])
    intensity = (
        measured.groupby("sector")
        .agg(scope1_tco2e=("scope1_tco2e", "sum"), revenue_usd=("revenue_usd", "sum"))
        .reset_index()
    )
    intensity["tco2e_per_usd_mm_revenue"] = intensity["scope1_tco2e"] / (intensity["revenue_usd"] / 1e6)

    # Sectors with no GHGRP-measured company at all (e.g. Financials, Info
    # Tech) aren't in `measured` -- give them the lowest observed intensity's
    # floor rather than treating them as "no data".
    all_sectors = df["sector"].dropna().unique()
    floor = intensity["tco2e_per_usd_mm_revenue"].min()
    missing = set(all_sectors) - set(intensity["sector"])
    if missing:
        filler = pd.DataFrame({"sector": sorted(missing), "tco2e_per_usd_mm_revenue": floor})
        intensity = pd.concat([intensity[["sector", "tco2e_per_usd_mm_revenue"]], filler], ignore_index=True)

    # sector_exposure_score: min-max rank of intensity, inverted so lower
    # structural exposure -> higher score.
    lo, hi = intensity["tco2e_per_usd_mm_revenue"].min(), intensity["tco2e_per_usd_mm_revenue"].max()
    intensity["sector_exposure_score"] = 100 * (1 - (intensity["tco2e_per_usd_mm_revenue"] - lo) / (hi - lo))
    return intensity[["sector", "tco2e_per_usd_mm_revenue", "sector_exposure_score"]]


def _estimate_emissions(df: pd.DataFrame) -> pd.DataFrame:
    measured = df["scope1_tco2e"].notna()
    modelled = df["tco2e_per_usd_mm_revenue"] * (df["revenue_usd"] / 1e6)
    df["estimated_emissions_tco2e"] = df["scope1_tco2e"].where(measured, modelled)
    df["emissions_source_tier"] = measured.map({True: "measured", False: "modelled"})
    return df


def _momentum_tier(row: pd.Series) -> str:
    if row["sbti_target_validated"] != 1:
        return "no_target"
    return {"net-zero": "net_zero_validated", "near-term": "near_term_set", "commitment": "committed"}.get(
        row["sbti_target_type"], "no_target"
    )


def _sector_counterfactual_target(df: pd.DataFrame) -> tuple[dict, dict]:
    """Median (reduction %, target year) among each sector's SBTi-quantified
    peers, used as the counterfactual for companies with no stated target --
    'no target' still carries the liability, it just isn't acknowledged.
    """
    quantified = df.dropna(subset=["target_reduction_pct", "target_year"])
    by_sector = quantified.groupby("sector").agg(
        reduction_pct=("target_reduction_pct", "median"),
        target_year=("target_year", "median"),
    )
    global_fallback = {
        "reduction_pct": quantified["target_reduction_pct"].median(),
        "target_year": quantified["target_year"].median(),
    }
    return by_sector.to_dict("index"), global_fallback


def _target_inputs(row: pd.Series, counterfactual_by_sector: dict, global_fallback: dict) -> tuple[float, float, str]:
    reduction_pct, target_year = row["target_reduction_pct"], row["target_year"]

    if pd.notna(reduction_pct) and pd.notna(target_year):
        return reduction_pct / 100.0, target_year, "disclosed"  # wide file's pct is 0-100, formula wants a fraction

    fallback = counterfactual_by_sector.get(row["sector"], global_fallback)
    return fallback["reduction_pct"] / 100.0, fallback["target_year"], "counterfactual_sector_median"


def compute_transition_scores() -> pd.DataFrame:
    df = pd.read_csv(WIDE_PATH)

    sector_intensity = _build_sector_intensity(df)
    df = df.merge(sector_intensity, on="sector", how="left")
    df = _estimate_emissions(df)

    # --- Carbon-price exposure ---
    df["carbon_price_cost_usd"] = df["estimated_emissions_tco2e"] * ASSUMED_CARBON_PRICE_USD_PER_TON
    df["pct_ebitda_erosion"] = 100 * df["carbon_price_cost_usd"] / df["ebitda_usd"]
    erosion_for_scoring = df["pct_ebitda_erosion"].clip(lower=0).where(df["ebitda_usd"] > 0, CARBON_PRICE_EROSION_CEILING_PCT)
    df["carbon_price_exposure_score"] = _ceiling_score(erosion_for_scoring, CARBON_PRICE_EROSION_CEILING_PCT)

    # --- Regulatory momentum: SBTi tier blended with R&D intensity ---
    df["momentum_tier"] = df.apply(_momentum_tier, axis=1)
    sbti_score = df["momentum_tier"].map(MOMENTUM_SCORES).fillna(0)
    df["rnd_intensity_pct"] = 100 * df["rnd_expense_usd"].fillna(0) / df["revenue_usd"]
    rnd_score = (100 * df["rnd_intensity_pct"].clip(lower=0, upper=RND_INTENSITY_CAP_PCT) / RND_INTENSITY_CAP_PCT).fillna(0)
    df["regulatory_momentum_score"] = (
        MOMENTUM_SUBWEIGHTS["sbti"] * sbti_score + MOMENTUM_SUBWEIGHTS["rnd_intensity"] * rnd_score
    )

    # --- Transition affordability ---
    counterfactual_by_sector, global_fallback = _sector_counterfactual_target(df)
    target_inputs = df.apply(
        lambda row: _target_inputs(row, counterfactual_by_sector, global_fallback), axis=1, result_type="expand"
    )
    df[["target_reduction_pct", "target_year", "target_basis"]] = target_inputs

    df["years_to_target"] = (df["target_year"] - CURRENT_YEAR).clip(lower=1)
    df["abatement_cost_usd_per_tco2e"] = df["sector"].map(SECTOR_ABATEMENT_COST_USD_PER_TCO2E).fillna(
        DEFAULT_ABATEMENT_COST_USD_PER_TCO2E
    )
    df["emissions_reduction_needed_tco2e"] = df["estimated_emissions_tco2e"] * df["target_reduction_pct"]
    df["annualized_transition_cost_usd"] = (
        df["emissions_reduction_needed_tco2e"] * df["abatement_cost_usd_per_tco2e"] / df["years_to_target"]
    )
    df["pct_fcf_committed"] = 100 * df["annualized_transition_cost_usd"] / df["free_cash_flow_usd"]
    affordability_for_scoring = df["pct_fcf_committed"].clip(lower=0).where(
        df["free_cash_flow_usd"] > 0, AFFORDABILITY_COST_CEILING_PCT
    )
    df["transition_affordability_score"] = _ceiling_score(affordability_for_scoring, AFFORDABILITY_COST_CEILING_PCT)

    df["transition_score"] = sum(df[col] * w for col, w in WEIGHTS.items())

    columns = [
        "ticker", "company", "sector",
        "revenue_usd", "ebitda_usd", "free_cash_flow_usd", "rnd_expense_usd",
        "estimated_emissions_tco2e", "emissions_source_tier",
        "pct_ebitda_erosion", "carbon_price_exposure_score",
        "sector_exposure_score",
        "rnd_intensity_pct", "momentum_tier", "regulatory_momentum_score",
        "target_basis", "target_reduction_pct", "target_year", "years_to_target",
        "abatement_cost_usd_per_tco2e", "pct_fcf_committed", "transition_affordability_score",
        "transition_score",
    ]
    return df[columns]


if __name__ == "__main__":
    result = compute_transition_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    missing_financials = result["revenue_usd"].isna().sum()
    measured = (result["emissions_source_tier"] == "measured").sum()
    print(f"Scored {len(result)} companies ({missing_financials} missing EDGAR financials).")
    print(f"Emissions source tier: {measured} measured (GHGRP), {len(result) - measured} modelled (sector proxy).")
    print(result["target_basis"].value_counts())
    print(result[[
        "carbon_price_exposure_score", "sector_exposure_score",
        "regulatory_momentum_score", "transition_affordability_score", "transition_score",
    ]].describe())
    print(f"\nSaved to {OUTPUT_PATH}")
