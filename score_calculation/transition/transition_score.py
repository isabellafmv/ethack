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
    TARGET_REDUCTION_PCT_BY_TIER,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
FINANCIALS_PATH = DATA_DIR / "company_financials.csv"
SECTOR_EMISSIONS_PATH = DATA_DIR / "epa_sector_emissions.csv"
SBTI_PATH = DATA_DIR / "sbti_matches.csv"
GHGRP_MATCHES_PATH = DATA_DIR / "epa_ghgrp_company_matches.csv"
OUTPUT_PATH = DATA_DIR / "transition_scores.csv"

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


def _build_sector_intensity(financials: pd.DataFrame, sector_emissions: pd.DataFrame) -> pd.DataFrame:
    sector_revenue = (
        financials.dropna(subset=["revenue_usd"])
        .groupby("sector")["revenue_usd"].sum()
        .rename("sector_revenue_usd")
        .reset_index()
    )
    intensity = sector_emissions.merge(sector_revenue, left_on="gics_sector", right_on="sector", how="left")
    intensity["tco2e_per_usd_mm_revenue"] = (
        intensity["ghgrp_direct_emissions_tco2e"] / (intensity["sector_revenue_usd"] / 1e6)
    )

    # Sectors with no GHGRP-reported facilities (e.g. Financials, Info Tech)
    # aren't in sector_emissions at all -- give them the lowest observed
    # intensity's floor rather than treating them as "no data".
    all_sectors = financials["sector"].dropna().unique()
    floor = intensity["tco2e_per_usd_mm_revenue"].min()
    missing = set(all_sectors) - set(intensity["gics_sector"])
    if missing:
        filler = pd.DataFrame({"gics_sector": sorted(missing), "tco2e_per_usd_mm_revenue": floor})
        intensity = pd.concat([intensity[["gics_sector", "tco2e_per_usd_mm_revenue"]], filler], ignore_index=True)

    # sector_exposure_score: min-max rank of intensity, inverted so lower
    # structural exposure -> higher score.
    lo, hi = intensity["tco2e_per_usd_mm_revenue"].min(), intensity["tco2e_per_usd_mm_revenue"].max()
    intensity["sector_exposure_score"] = 100 * (1 - (intensity["tco2e_per_usd_mm_revenue"] - lo) / (hi - lo))
    return intensity[["gics_sector", "tco2e_per_usd_mm_revenue", "sector_exposure_score"]]


def _estimate_emissions(df: pd.DataFrame) -> pd.DataFrame:
    modelled = df["tco2e_per_usd_mm_revenue"] * (df["revenue_usd"] / 1e6)
    df["estimated_emissions_tco2e"] = df["ghgrp_emissions_tco2e"].where(df["ghgrp_matched"], modelled)
    df["emissions_source_tier"] = df["ghgrp_matched"].map({True: "measured", False: "modelled"})
    return df


def _sector_counterfactual_target(sbti: pd.DataFrame) -> dict:
    """Median (reduction %, target year) among each sector's SBTi-quantified
    peers, used as the counterfactual for companies with no stated target --
    'no target' still carries the liability, it just isn't acknowledged.
    """
    quantified = sbti[sbti["momentum_tier"].isin(["targets_set_1.5c", "targets_set_2c", "net_zero_validated"])].copy()
    quantified["reduction_pct"] = quantified["momentum_tier"].map(TARGET_REDUCTION_PCT_BY_TIER)

    by_sector = quantified.groupby("sector").agg(
        reduction_pct=("reduction_pct", "median"),
        target_year=("near_term_target_year", "median"),
    )
    global_fallback = {
        "reduction_pct": quantified["reduction_pct"].median(),
        "target_year": quantified["near_term_target_year"].median(),
    }
    return by_sector.to_dict("index"), global_fallback


def _target_inputs(sbti_row: pd.Series, counterfactual_by_sector: dict, global_fallback: dict) -> tuple[float, float, str]:
    reduction_pct = TARGET_REDUCTION_PCT_BY_TIER.get(sbti_row["momentum_tier"])
    target_year = sbti_row["near_term_target_year"]

    if reduction_pct is not None and pd.notna(target_year):
        return reduction_pct, target_year, "disclosed"

    fallback = counterfactual_by_sector.get(sbti_row["sector"], global_fallback)
    return fallback["reduction_pct"], fallback["target_year"], "counterfactual_sector_median"


def compute_transition_scores() -> pd.DataFrame:
    financials = pd.read_csv(FINANCIALS_PATH)
    sector_emissions = pd.read_csv(SECTOR_EMISSIONS_PATH)
    sbti = pd.read_csv(SBTI_PATH)
    ghgrp = pd.read_csv(GHGRP_MATCHES_PATH)

    sector_intensity = _build_sector_intensity(financials, sector_emissions)

    df = financials.merge(sector_intensity, left_on="sector", right_on="gics_sector", how="left")
    df = df.merge(ghgrp[["ticker", "ghgrp_matched", "ghgrp_emissions_tco2e"]], on="ticker", how="left")
    df = df.merge(
        sbti[["ticker", "momentum_tier", "regulatory_momentum_score", "near_term_target_year"]],
        on="ticker", how="left",
    )
    df = _estimate_emissions(df)

    # --- Carbon-price exposure ---
    df["carbon_price_cost_usd"] = df["estimated_emissions_tco2e"] * ASSUMED_CARBON_PRICE_USD_PER_TON
    df["pct_ebitda_erosion"] = 100 * df["carbon_price_cost_usd"] / df["ebitda_proxy_usd"]
    erosion_for_scoring = df["pct_ebitda_erosion"].clip(lower=0).where(df["ebitda_proxy_usd"] > 0, CARBON_PRICE_EROSION_CEILING_PCT)
    df["carbon_price_exposure_score"] = _ceiling_score(erosion_for_scoring, CARBON_PRICE_EROSION_CEILING_PCT)

    # --- Regulatory momentum: SBTi tier blended with R&D intensity ---
    sbti_score = df["regulatory_momentum_score"].fillna(0)
    df["rnd_intensity_pct"] = 100 * df["rnd_expense_usd"].fillna(0) / df["revenue_usd"]
    rnd_score = (100 * df["rnd_intensity_pct"].clip(lower=0, upper=RND_INTENSITY_CAP_PCT) / RND_INTENSITY_CAP_PCT).fillna(0)
    df["regulatory_momentum_score"] = (
        MOMENTUM_SUBWEIGHTS["sbti"] * sbti_score + MOMENTUM_SUBWEIGHTS["rnd_intensity"] * rnd_score
    )

    # --- Transition affordability ---
    counterfactual_by_sector, global_fallback = _sector_counterfactual_target(sbti)
    target_inputs = sbti.apply(
        lambda row: _target_inputs(row, counterfactual_by_sector, global_fallback), axis=1, result_type="expand"
    )
    target_inputs.columns = ["target_reduction_pct", "target_year", "target_basis"]
    df = df.merge(pd.concat([sbti["ticker"], target_inputs], axis=1), on="ticker", how="left")

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
        "revenue_usd", "ebitda_proxy_usd", "free_cash_flow_usd", "rnd_expense_usd",
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
