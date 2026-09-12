"""Transition pillar score: carbon-price exposure, sector structural
exposure, and regulatory momentum, combined into one weighted score.

Each sub-metric is built from real, per-company or bottom-up sector data
(see score_calculation/data_sources/*) rather than hand-picked constants:

- carbon_price_exposure_score: modeled EBITDA erosion under an assumed
  carbon price, using each company's own EDGAR revenue/EBITDA proxy scaled
  by a sector emissions-intensity benchmark derived from EPA GHGRP facility
  data (real Scope 1 measurements, not self-reported).
- sector_exposure_score: how structurally carbon-intensive the company's
  GICS sector is, ranked from the same GHGRP intensity benchmark.
- regulatory_momentum_score: tiered signal from the company's actual SBTi
  target status (no target / committed / 2C / 1.5C / net-zero validated).

WEIGHTS below are provisional -- intended to be reviewed against the raw
sub-scores (all kept in the output CSV) before being finalized.
"""
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
FINANCIALS_PATH = DATA_DIR / "company_financials.csv"
SECTOR_EMISSIONS_PATH = DATA_DIR / "epa_sector_emissions.csv"
SBTI_PATH = DATA_DIR / "sbti_matches.csv"
OUTPUT_PATH = DATA_DIR / "transition_scores.csv"

ASSUMED_CARBON_PRICE_USD_PER_TON = 100.0
# % EBITDA erosion at/above which carbon_price_exposure_score bottoms out at 0.
EROSION_CEILING_PCT = 50.0

# Provisional -- revisit once the raw sub-scores have been reviewed.
WEIGHTS = {
    "carbon_price_exposure_score": 0.5,
    "sector_exposure_score": 0.25,
    "regulatory_momentum_score": 0.25,
}


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


def compute_transition_scores() -> pd.DataFrame:
    financials = pd.read_csv(FINANCIALS_PATH)
    sector_emissions = pd.read_csv(SECTOR_EMISSIONS_PATH)
    sbti = pd.read_csv(SBTI_PATH)

    sector_intensity = _build_sector_intensity(financials, sector_emissions)

    df = financials.merge(sector_intensity, left_on="sector", right_on="gics_sector", how="left")
    df = df.merge(sbti[["ticker", "regulatory_momentum_score", "momentum_tier"]], on="ticker", how="left")

    df["estimated_emissions_tco2e"] = df["tco2e_per_usd_mm_revenue"] * (df["revenue_usd"] / 1e6)
    df["carbon_price_cost_usd"] = df["estimated_emissions_tco2e"] * ASSUMED_CARBON_PRICE_USD_PER_TON
    df["pct_ebitda_erosion"] = 100 * df["carbon_price_cost_usd"] / df["ebitda_proxy_usd"]

    # Negative/zero EBITDA makes the ratio meaningless (undefined or a sign
    # flip, not "extremely exposed") -- treat as worst-case (ceiling) instead.
    erosion_for_scoring = df["pct_ebitda_erosion"].clip(lower=0)
    erosion_for_scoring = erosion_for_scoring.where(df["ebitda_proxy_usd"] > 0, EROSION_CEILING_PCT)
    df["carbon_price_exposure_score"] = 100 * (1 - (erosion_for_scoring.clip(upper=EROSION_CEILING_PCT) / EROSION_CEILING_PCT))

    df["regulatory_momentum_score"] = df["regulatory_momentum_score"].fillna(0)

    df["transition_score"] = sum(df[col] * w for col, w in WEIGHTS.items())

    columns = [
        "ticker", "company", "sector",
        "revenue_usd", "ebitda_proxy_usd",
        "tco2e_per_usd_mm_revenue", "estimated_emissions_tco2e",
        "pct_ebitda_erosion", "carbon_price_exposure_score",
        "sector_exposure_score",
        "momentum_tier", "regulatory_momentum_score",
        "transition_score",
    ]
    return df[columns]


if __name__ == "__main__":
    result = compute_transition_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    missing_financials = result["revenue_usd"].isna().sum()
    print(f"Scored {len(result)} companies ({missing_financials} missing EDGAR financials).")
    print(result[["ticker", "sector", "carbon_price_exposure_score", "sector_exposure_score",
                   "regulatory_momentum_score", "transition_score"]].describe())
    print(f"\nSaved to {OUTPUT_PATH}")
