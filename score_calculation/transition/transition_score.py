"""Transition pillar score: carbon-price exposure, sector structural
exposure, regulatory commitment, and transition affordability, combined
into one weighted score.

Reads Isabella's pipeline output directly (data/wide_FY2025_fallback.csv --
see pipeline/export_wide.py), not a separately-fetched copy of the same
data:

- carbon_price_exposure_score: modeled EBITDA erosion under an assumed
  carbon price. Uses REAL EPA GHGRP facility emissions (scope1_tco2e) for
  companies where the pipeline has a measured value ("measured" tier); falls
  back to a sector emissions-intensity benchmark x the company's own EDGAR
  revenue for everyone else ("modelled" tier). emissions_source_tier records
  which applies per company.
- sector_exposure_score: how structurally carbon-intensive the company's
  GICS sector is, ranked from the same GHGRP-derived intensity benchmark.
  Measured correlation with carbon_price_exposure_score for modelled-tier
  companies is 0.50 -- real but partial overlap (EBITDA varies independently
  of revenue, so the two aren't identical), which is why its weight is kept
  low rather than dropped outright.
- regulatory_commitment_score: SBTi target tier (real, disclosed) blended
  with R&D intensity from EDGAR (real). Named "commitment," not "momentum" --
  it's a snapshot of what's been committed to, not a rate of change; nothing
  here is a trend measure, and calling it momentum overclaimed what a single
  point in time can show. Patent-based innovation signal (USPTO PatentsView
  Y02 share) from the spec is NOT included yet -- PatentsView requires a free
  API key and wasn't reachable from this environment; this is a known,
  explicit gap rather than a silently-dropped indicator.
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

A company's transition_score_raw is a weighted average over whichever
sub-scores it actually has (renormalized), never a silent worst-case default
for a missing one -- missing EBITDA, FCF, or R&D used to be treated as "erosion/
cost so bad it hit the ceiling" or "spends nothing," which was the single
largest source of 0-scores in the pillar and had nothing to do with the
company's actual transition risk. See info.md for the before/after numbers.
This EBITDA/FCF/R&D null-handling is untouched by the taxonomy below --
it was already right.

Missing data on a sub-score doesn't mean one thing, though, and this pillar
now distinguishes two kinds of it:

- PIPELINE_GAP_INDICATORS: null for a reason that isn't the company's own
  disclosure choice -- carbon_price_exposure_score and
  transition_affordability_score go null purely from missing/non-positive
  EBITDA or FCF (a financial-statement pull gap, see above, not touched
  here), and sector_exposure_score is a sector-level fact built from GHGRP
  data, never something an individual company discloses or withholds. All
  three renormalize for free, as before.
- regulatory_commitment_score is the one disclosure-gap (category-3)
  indicator: a missing SBTi target is itself a disclosure signal, not a
  data-pull artifact, the way a missing climate oversight committee is in
  governance_score.py. transition_score applies a coverage penalty on top
  of transition_score_raw for it:

      transition_score = transition_score_raw * (0.6 + 0.4 * transition_disclosure_coverage)

  transition_disclosure_coverage is weight_sum restricted to
  regulatory_commitment_score, divided by its own weight -- 1.0 when
  present, dropping toward the 0.6 floor when it isn't.

  IMPORTANT CAVEAT, flagged rather than silently papered over:
  regulatory_commitment_score is not actually null-capable today.
  _commitment_tier() maps an unknown/undisclosed SBTi status to the same
  "no_target" tier as an explicitly-disclosed absence of one, and
  COMMITMENT_SCORES scores "no_target" as 0 -- not NaN. So every company
  gets a regulatory_commitment_score, and transition_disclosure_coverage is
  1.0 for the whole universe right now, making this penalty a no-op for P2.
  Fixing that would mean changing how an undisclosed SBTi status is
  recorded (null instead of defaulting to the same score as a disclosed
  "no target"), which is a change to existing scoring logic beyond this
  taxonomy's scope -- left alone deliberately, not missed.

data_confidence_pct carries how much of that composite rests on real,
company-specific evidence (measured emissions, a disclosed target) versus a
sector-level or counterfactual estimate -- two companies can show the same
transition_score for very different reasons, and n_subscores_available alone
doesn't say whether the sub-scores it does have are strongly or weakly
evidenced. It is untouched by, and independent from, the coverage penalty
above.
"""
from pathlib import Path

import pandas as pd

from score_calculation.coverage import (
    apply_disclosure_penalty,
    disclosure_coverage,
    renormalized_average,
)
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

# SBTi target ambition -> commitment score. Isabella's field contract only
# distinguishes three tiers (commitment / near-term / net-zero), coarser than
# the old 1.5C-vs-2C split this used to have -- there's no data to support
# that finer split anymore.
COMMITMENT_SCORES = {
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
# sector_exposure_score's weight was cut from 0.15 to 0.08 (redistributed to
# carbon_price_exposure and affordability): the two carbon metrics measure
# r=0.50 correlated for modelled-tier companies (same underlying GHGRP
# sector-intensity table), so giving them near-equal weight double-counts
# one signal more than the nominal split suggests. Not dropped entirely --
# the correlation is partial, not total, so it still adds information.
WEIGHTS = {
    "carbon_price_exposure_score": 0.32,
    "sector_exposure_score": 0.08,
    "regulatory_commitment_score": 0.25,
    "transition_affordability_score": 0.35,
}

# Sub-indicators in WEIGHTS that are null for a reason that isn't the
# company's own disclosure choice (missing EBITDA/FCF, a sector-level fact)
# rather than a disclosure gap. See the module docstring -- including the
# caveat that regulatory_commitment_score (the one indicator NOT listed
# here) is not currently null-capable, making the coverage penalty below a
# no-op for this pillar today.
PIPELINE_GAP_INDICATORS = {
    "carbon_price_exposure_score",
    "transition_affordability_score",
    "sector_exposure_score",
}

# Blend within regulatory_commitment_score: disclosed SBTi commitment vs. R&D
# spend as a proxy for innovation capacity (patents would sit here too, once available).
COMMITMENT_SUBWEIGHTS = {"sbti": 0.7, "rnd_intensity": 0.3}

# Per-sub-score confidence when it rests on the strongest evidence tier
# available (measured emissions, a disclosed target, R&D actually reported) --
# scaled down, not zeroed, for the weaker tier, since a modelled/counterfactual
# value is still a real estimate, not a guess. Purely a transparency signal;
# it does not change transition_score itself.
FULL_CONFIDENCE = 1.0
PARTIAL_CONFIDENCE = 0.5


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


def _commitment_tier(row: pd.Series) -> str:
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


def _confidence(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sub-score confidence (1.0 = strongest evidence tier, 0.5 = the
    weaker one), then a weighted average over whichever sub-scores a company
    has -- same weights and same renormalization as transition_score itself,
    so the two numbers are directly comparable.
    """
    df["carbon_price_exposure_score_confidence"] = df["carbon_price_exposure_score"].notna() & (
        df["emissions_source_tier"] == "measured"
    )
    df["carbon_price_exposure_score_confidence"] = df["carbon_price_exposure_score_confidence"].map(
        {True: FULL_CONFIDENCE, False: PARTIAL_CONFIDENCE}
    ).where(df["carbon_price_exposure_score"].notna())

    # sector_exposure_score is always a real (if coarse) sector-level fact
    # when it exists -- no weaker tier to distinguish.
    df["sector_exposure_score_confidence"] = df["sector_exposure_score"].notna().map(
        {True: FULL_CONFIDENCE, False: None}
    )

    has_rnd = df["rnd_intensity_pct"].notna()
    df["regulatory_commitment_score_confidence"] = df["regulatory_commitment_score"].notna() & has_rnd
    df["regulatory_commitment_score_confidence"] = df["regulatory_commitment_score_confidence"].map(
        {True: FULL_CONFIDENCE, False: PARTIAL_CONFIDENCE}
    ).where(df["regulatory_commitment_score"].notna())

    df["transition_affordability_score_confidence"] = df["transition_affordability_score"].notna() & (
        df["target_basis"] == "disclosed"
    )
    df["transition_affordability_score_confidence"] = df["transition_affordability_score_confidence"].map(
        {True: FULL_CONFIDENCE, False: PARTIAL_CONFIDENCE}
    ).where(df["transition_affordability_score"].notna())

    confidence_cols = [f"{c}_confidence" for c in WEIGHTS]
    weights = pd.Series(WEIGHTS, index=WEIGHTS.keys()).rename(lambda c: f"{c}_confidence")
    confidence_score, _, _ = renormalized_average(df, confidence_cols, weights)
    df["data_confidence_pct"] = 100 * confidence_score
    return df


def compute_transition_scores() -> pd.DataFrame:
    df = pd.read_csv(WIDE_PATH)

    sector_intensity = _build_sector_intensity(df)
    df = df.merge(sector_intensity, on="sector", how="left")
    df = _estimate_emissions(df)

    # --- Carbon-price exposure ---
    # No EBITDA on record is a data gap, not "erosion so bad it hit the
    # ceiling" -- null it and let the final weighting skip it, rather than
    # silently scoring these companies as maximally exposed (see info.md;
    # this used to be the largest single cause of 0-scores in the pillar).
    df["carbon_price_cost_usd"] = df["estimated_emissions_tco2e"] * ASSUMED_CARBON_PRICE_USD_PER_TON
    df["pct_ebitda_erosion"] = (100 * df["carbon_price_cost_usd"] / df["ebitda_usd"]).where(df["ebitda_usd"] > 0)
    df["carbon_price_exposure_score"] = _ceiling_score(
        df["pct_ebitda_erosion"].clip(lower=0), CARBON_PRICE_EROSION_CEILING_PCT
    )

    # --- Regulatory commitment: SBTi tier blended with R&D intensity ---
    # rnd_expense_usd absent means "not broken out as its own XBRL line item",
    # not "spends nothing on R&D" (most non-tech sectors never tag it
    # separately even when they do spend) -- so a missing R&D figure drops
    # that half of the blend entirely rather than defaulting it to 0, which
    # used to force this sub-score toward "no commitment" for 54% of the
    # index regardless of their actual SBTi status. See info.md.
    df["commitment_tier"] = df.apply(_commitment_tier, axis=1)
    sbti_score = df["commitment_tier"].map(COMMITMENT_SCORES).astype(float)
    df["rnd_intensity_pct"] = 100 * df["rnd_expense_usd"] / df["revenue_usd"]
    rnd_score = (100 * df["rnd_intensity_pct"].clip(lower=0, upper=RND_INTENSITY_CAP_PCT) / RND_INTENSITY_CAP_PCT)
    has_rnd = rnd_score.notna()
    df["regulatory_commitment_score"] = sbti_score.where(
        ~has_rnd,
        COMMITMENT_SUBWEIGHTS["sbti"] * sbti_score + COMMITMENT_SUBWEIGHTS["rnd_intensity"] * rnd_score,
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
    # Missing or non-positive FCF is a data gap, not "committed >=100% of
    # cash flow" -- null it rather than defaulting to worst-case. Before this
    # fix, every single 0 on this sub-score came from a missing FCF figure,
    # never a genuinely over-committed company (see info.md).
    df["pct_fcf_committed"] = (100 * df["annualized_transition_cost_usd"] / df["free_cash_flow_usd"]).where(
        df["free_cash_flow_usd"] > 0
    )
    df["transition_affordability_score"] = _ceiling_score(
        df["pct_fcf_committed"].clip(lower=0), AFFORDABILITY_COST_CEILING_PCT
    )

    # Weighted average over whichever sub-scores a company actually has,
    # renormalized -- a missing sub-score no longer drags the composite
    # toward 0 just because one term of a sum went NaN.
    sub_cols = list(WEIGHTS)
    weights = pd.Series(WEIGHTS)
    df["transition_score_raw"], weight_matrix, _ = renormalized_average(df, sub_cols, weights)
    df["n_subscores_available"] = df[sub_cols].notna().sum(axis=1)

    # Coverage penalty: renormalize category-2 (pipeline-gap) indicators out
    # for free, but category-3 (disclosure-gap) ones dock the score. See the
    # module docstring, including the caveat that this is currently a no-op
    # (regulatory_commitment_score is never actually null).
    disclosure_cols = [c for c in sub_cols if c not in PIPELINE_GAP_INDICATORS]
    df["transition_disclosure_coverage"] = disclosure_coverage(weight_matrix, weights, disclosure_cols)
    df["transition_score"] = apply_disclosure_penalty(df["transition_score_raw"], df["transition_disclosure_coverage"])

    df = _confidence(df)

    columns = [
        "ticker", "company", "sector",
        "revenue_usd", "ebitda_usd", "free_cash_flow_usd", "rnd_expense_usd",
        "estimated_emissions_tco2e", "emissions_source_tier",
        "pct_ebitda_erosion", "carbon_price_exposure_score",
        "sector_exposure_score",
        "rnd_intensity_pct", "commitment_tier", "regulatory_commitment_score",
        "target_basis", "target_reduction_pct", "target_year", "years_to_target",
        "abatement_cost_usd_per_tco2e", "pct_fcf_committed", "transition_affordability_score",
        "n_subscores_available", "data_confidence_pct",
        "transition_score_raw", "transition_disclosure_coverage", "transition_score",
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
        "regulatory_commitment_score", "transition_affordability_score",
        "data_confidence_pct", "transition_score_raw", "transition_score",
    ]].describe())

    penalized = result[result["transition_disclosure_coverage"] < 1.0]
    print(f"\nDisclosure coverage < 1.0: {len(penalized)}/{len(result)} companies.")
    if len(penalized):
        diff = penalized["transition_score_raw"] - penalized["transition_score"]
        print(f"Average raw-vs-adjusted point difference for those companies: {diff.mean():.2f}")
    else:
        print("(Expected -- see the module docstring's caveat: regulatory_commitment_score "
              "is never actually null today, so this penalty is currently a no-op for P2.)")
    print(f"\nSaved to {OUTPUT_PATH}")
