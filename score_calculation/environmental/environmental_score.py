"""Environmental & Resource Efficiency pillar score: carbon intensity,
energy mix, resource & waste intensity, and input & operational efficiency,
combined into one weighted score.

Reads Isabella's pipeline output directly (data/wide_FY2025_fallback.csv --
see pipeline/export_wide.py), the same source transition_score.py and
governance_score.py use. Sub-score weights come from Isabella's
pipeline/materiality.py -- a SASB-inspired, per-GICS-sector materiality
matrix already wired into web/src/scoring, adopted here rather than
reinvented so the Python and TypeScript sides start from the same
weighting rationale. See that file for the per-sector "why".

Three of the four spec indicators have real data right now:

- carbon_intensity_score: REVIVED, measured-tier only. An earlier version
  tried to extend this to modelled-tier companies using transition_score.py's
  sector_benchmark x revenue emissions estimate -- dividing that back by the
  same revenue just reconstructs the sector constant it was built from, so
  every modelled company in a sector got an identical, non-differentiating
  value. Rather than patch that, this only scores the ~126 companies with a
  real measured scope1_tco2e, ranked as a percentile within their own sector
  against other real measured peers. Coverage is uneven by design: Utilities
  (94% measured), Materials (68%) and Energy (76%) get real coverage almost
  everywhere it materially matters most (materiality weight 35/38/32); Real
  Estate (3% measured) does not -- see energy_mix_score below for the fix.
- energy_mix_score: real, from S19 (EPA eGRID) -- a REGIONAL PROXY (grid
  carbon intensity where a company is headquartered), not the spec's own
  fields (renewable/total electricity, S10/S21, neither pulled). Every
  company in the same state shares the identical value, by construction --
  that's coarser than true company data, but it's a real government number,
  not a reconstruction of something else, so it isn't degenerate the way
  the dropped carbon_intensity_score modelled tier was. 475/500 covered;
  the rest are non-US-headquartered companies (Ireland, UK, Bermuda, etc.)
  with no US grid to join to. This is exactly the fix for Real Estate:
  3% GHGRP-measured, but 100% covered here, since a REIT's footprint is
  almost entirely purchased electricity, not a smokestack -- materiality
  weights energy_mix highest for that sector precisely because of this.
- input_efficiency_score: mean of (COGS/revenue) and (energy cost/revenue),
  each a percentile within sector against real peer values. energy_cost_usd
  has almost no coverage (17/500) so most companies are scored on COGS
  alone; the mean-of-available-components pattern (same as
  governance_score.py) means that's a narrower basis, not a penalty.
- resource_waste_score: architecture is here, but every company scores
  null. Needs S16 (EPA TRI), S17 (EPA RSEI), or S26 (WRI Aqueduct) -- none
  pulled, and the spec itself expects this to stay sparse (manufacturing/
  mining only, ~120/500) even once it is.

A company's environmental_score_raw is a weighted average over whichever
sub-scores it actually has (renormalized), never a silent worst-case default
for a missing one -- same pattern as transition_score.py and
governance_score.py. Weights themselves are now PER-SECTOR
(materiality-based) rather than one flat set for the whole index: a missing
carbon_intensity_score for a Financials company barely moves its
environmental_score_raw, because carbon intensity is only ~13% of
Financials' P1 weight to begin with; the same gap for a Utility (35% weight)
would matter far more, which is exactly backwards from the coverage the two
sectors actually have and precisely the problem materiality weighting
exists to fix.

Missing data on a sub-score doesn't mean one thing, though. This pillar
distinguishes two kinds of "missing" (a third, structural zero, doesn't
arise here -- there's no P1 indicator where "absent" is itself a real zero
the way an unclaimed buyback line item is in governance_score.py):

- PIPELINE_GAP_INDICATORS: null because the data source hasn't been pulled
  for effectively the whole universe -- nobody's fault, and renormalizing
  around it for free is correct. Only resource_waste_score qualifies right
  now (S16/S17/S26, none pulled, 0/500). carbon_intensity_score and
  energy_mix_score used to belong here too, back when GHGRP/eGRID weren't
  wired up -- now that they're real (126/500 measured-tier, 475/500 via
  S19), a company still missing one of those is missing it for a company-
  specific reason (no measured scope1_tco2e on file, non-US headquarters),
  not because nobody pulled the field, so they've moved to the list below.
- Everything else in the per-sector weight table is a disclosure gap by
  default: carbon_intensity_score, energy_mix_score, and
  input_efficiency_score. A company missing one of these is missing real,
  available-for-peers data, so it no longer renormalizes for free --
  environmental_score applies an explicit coverage penalty on top of
  environmental_score_raw:

      environmental_score = environmental_score_raw * (0.6 + 0.4 * environmental_disclosure_coverage)

  environmental_disclosure_coverage is weight_sum restricted to
  disclosure-gap indicators -- using this company's own PER-SECTOR weights,
  since that's the only weight table that exists here -- divided by that
  sector's total weight across just those disclosure-gap indicators. 1.0
  when every disclosure-gap indicator is present, scaling down toward the
  0.6 floor as more of them go missing. The 0.6 floor means a company
  disclosing almost nothing keeps 60% of its raw score rather than being
  driven toward 0 purely for under-disclosing -- raw_score already
  reflects what it does disclose; this penalty is about the disclosure gap
  itself, a separate signal. environmental_score_raw is kept in the output
  for auditability.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from score_calculation.coverage import (
    apply_disclosure_penalty,
    disclosure_coverage,
    renormalized_average,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
WIDE_PATH = DATA_DIR / "wide_FY2025_fallback.csv"
OUTPUT_PATH = DATA_DIR / "environmental_scores.csv"

sys.path.insert(0, str(PROJECT_ROOT))
from pipeline.materiality import matrix as _materiality_matrix  # noqa: E402

# Our column name -> pipeline/materiality.py's indicator key.
_INDICATOR_KEY = {
    "carbon_intensity_score": "carbon_intensity",
    "energy_mix_score": "energy_mix",
    "resource_waste_score": "resource_waste_intensity",
    "input_efficiency_score": "input_efficiency",
}

# Sub-indicators that are null because the data source isn't pulled for the
# whole universe (not the company's fault) rather than because this specific
# company doesn't disclose. See the module docstring.
PIPELINE_GAP_INDICATORS = {"resource_waste_score"}


def _materiality_weights_per_sector() -> pd.DataFrame:
    """One row per sector, one column per our sub-score name, weights
    renormalized to sum to 1 across just these 4 P1 indicators (the
    materiality matrix's own weights span all 13 indicators across all
    three pillars; only the P1 slice and its relative proportions matter
    here).
    """
    m = _materiality_matrix()
    rows = []
    for sector, ind_weights in m.items():
        raw = {our: ind_weights.get(theirs, 0.0) for our, theirs in _INDICATOR_KEY.items()}
        total = sum(raw.values()) or 1.0
        rows.append({"sector": sector, **{k: v / total for k, v in raw.items()}})
    return pd.DataFrame(rows)


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


def _carbon_intensity_score(df: pd.DataFrame) -> pd.Series:
    """Measured-tier only (real scope1_tco2e from GHGRP) -- see the module
    docstring for why the modelled tier was left out rather than patched.
    Percentile within sector, ranked against other measured peers; lower
    intensity scores higher.
    """
    is_measured = df["scope1_tco2e"].notna()
    df["measured_intensity_tco2e_per_usd_mm"] = (
        df["scope1_tco2e"] / (df["revenue_usd"] / 1e6)
    ).where(is_measured & df["revenue_usd"].notna())
    percentile = _sector_percentile_vs_measured(df, "measured_intensity_tco2e_per_usd_mm", is_measured)
    return 100 * (1 - percentile)


def _input_efficiency_score(df: pd.DataFrame) -> pd.Series:
    df["cogs_intensity_pct"] = 100 * df["cogs_usd"] / df["revenue_usd"]
    df["energy_cost_intensity_pct"] = 100 * df["energy_cost_usd"] / df["revenue_usd"]
    has_cogs = df["cogs_intensity_pct"].notna()
    has_energy = df["energy_cost_intensity_pct"].notna()

    cogs_pctile = _sector_percentile_vs_measured(df, "cogs_intensity_pct", has_cogs)
    energy_pctile = _sector_percentile_vs_measured(df, "energy_cost_intensity_pct", has_energy)

    components = pd.concat([100 * (1 - cogs_pctile), 100 * (1 - energy_pctile)], axis=1)
    return components.mean(axis=1, skipna=True)


def _energy_mix_score(df: pd.DataFrame) -> pd.Series:
    """The spec's own fields (renewable_electricity_mwh/total_electricity_mwh,
    S10/S21) aren't pulled -- this is a REGIONAL PROXY instead, from S19
    (EPA eGRID): the carbon intensity of the electricity grid where a
    company is headquartered, ranked as a percentile within its own sector.
    Real number, not company-specific -- every company in the same state
    shares the identical value, by construction (see s19_epa_egrid/extract.py).
    That's a coarser signal than the spec's own indicator would be, but it's
    not degenerate the way the dropped carbon_intensity_score modelled-tier
    was: eGRID publishes the state rate directly, it isn't reconstructed by
    dividing something back out of a formula it was built from.
    """
    has_grid_data = df["grid_intensity_kgco2e_per_mwh"].notna()
    percentile = _sector_percentile_vs_measured(df, "grid_intensity_kgco2e_per_mwh", has_grid_data)
    return 100 * (1 - percentile)


def _resource_waste_score(df: pd.DataFrame) -> pd.Series:
    """RSEI toxicity-weighted score (S17) and water stress-weighted
    withdrawal (S16/S26). Not pulled yet -- and per the spec, expected to
    stay sparse (manufacturing/mining only, ~120/500) even once it is.
    """
    return pd.Series(pd.NA, index=df.index, dtype="Float64")


def compute_environmental_scores() -> pd.DataFrame:
    df = pd.read_csv(WIDE_PATH)

    df["carbon_intensity_score"] = _carbon_intensity_score(df)
    df["input_efficiency_score"] = _input_efficiency_score(df)
    df["energy_mix_score"] = _energy_mix_score(df)
    df["resource_waste_score"] = _resource_waste_score(df)

    sub_cols = list(_INDICATOR_KEY)
    weight_cols = [f"{c}_weight" for c in sub_cols]
    weight_table = _materiality_weights_per_sector().rename(columns=dict(zip(sub_cols, weight_cols)))
    df = df.merge(weight_table, on="sector", how="left")
    # renormalized_average/disclosure_coverage expect weight columns named
    # the same as sub_cols (a flat Series does this implicitly; here the
    # per-sector weight table needs the "_weight" suffix stripped once).
    weights = df[weight_cols].set_axis(sub_cols, axis=1)

    df["environmental_score_raw"], weight_matrix, _ = renormalized_average(df, sub_cols, weights)
    df["n_indicators_available"] = df[sub_cols].notna().sum(axis=1)

    # Coverage penalty: renormalize category-2 (pipeline-gap) indicators out
    # for free, but category-3 (disclosure-gap) ones dock the score. Uses
    # this company's own per-sector weights, since that's the only weight
    # table that exists here. See the module docstring.
    disclosure_cols = [c for c in sub_cols if c not in PIPELINE_GAP_INDICATORS]
    df["environmental_disclosure_coverage"] = disclosure_coverage(weight_matrix, weights, disclosure_cols)
    df["environmental_score"] = apply_disclosure_penalty(
        df["environmental_score_raw"], df["environmental_disclosure_coverage"]
    )

    columns = [
        "ticker", "company", "sector",
        "revenue_usd", "cogs_usd", "energy_cost_usd",
        "scope1_tco2e", "measured_intensity_tco2e_per_usd_mm", "grid_intensity_kgco2e_per_mwh",
        *sub_cols, "n_indicators_available",
        "environmental_score_raw", "environmental_disclosure_coverage", "environmental_score",
    ]
    return df[columns]


if __name__ == "__main__":
    result = compute_environmental_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    scored = result["environmental_score"].notna().sum()
    measured = result["scope1_tco2e"].notna().sum()
    print(f"Scored {scored}/{len(result)} companies.")
    print(f"Carbon intensity measured-tier coverage: {measured}/{len(result)}")
    print("Indicators available per company:")
    print(result["n_indicators_available"].value_counts().sort_index())
    print()
    print(result[["environmental_score_raw", "environmental_score"]].describe())

    penalized = result[result["environmental_disclosure_coverage"] < 1.0]
    print(f"\nDisclosure coverage < 1.0: {len(penalized)}/{len(result)} companies.")
    if len(penalized):
        diff = penalized["environmental_score_raw"] - penalized["environmental_score"]
        print(f"Average raw-vs-adjusted point difference for those companies: {diff.mean():.2f}")
    print(f"\nSaved to {OUTPUT_PATH}")
