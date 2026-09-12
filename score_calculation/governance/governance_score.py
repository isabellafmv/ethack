"""Governance & Capital Stewardship pillar score: climate governance,
compensation alignment, board independence & structure, capital stewardship,
and controversy/enforcement record, combined into one weighted score.

Reads Isabella's pipeline output directly (data/wide_FY2025_fallback.csv --
see pipeline/export_wide.py), the same source transition_score.py uses.

All five spec indicators now have real data (S04 proxy extraction and S18
EPA ECHO both landed):

- capital_stewardship_score: real, computed from XBRL (S01). Reinvestment
  share = (capex + R&D) / (capex + R&D + buybacks + dividends) -- the spec's
  own framing ("ship the discrepancy, not the level"): a company plowing
  money back into the business scores high, one mostly returning it to
  shareholders scores low. Needs capex_usd on record; buybacks/dividends/R&D
  default to 0 when absent, because those are genuinely optional line items
  (a company with no buyback program simply omits the XBRL tag -- unlike
  EBITDA or revenue, where absence means a data gap, not a real zero).
  Reinvestment share is really a capital-discipline/growth-stage signal more
  than a climate-specific one -- it's the spec's own chosen indicator, not
  something invented here, but it will reward any capital-intensive grower
  (not only a climate-motivated one) and that's worth knowing when reading it.
- climate_governance_score: mean of whichever of has_climate_oversight_
  committee / has_third_party_assurance / emissions_boundary_stated a
  company has (S04). Coverage is low (~45-60/500 each) -- these are a
  low-recall extraction rule (`concept_not_found_low_recall`), so a null here
  skews toward "we couldn't tell" more than the other sub-scores do; this is
  a different kind of null than this pipeline's usual "not_disclosed is a
  real finding," and data_confidence_pct below is what flags it, not the
  score itself. comp_tied_to_emissions_target is in the spec's four booleans
  but S04 doesn't emit it at all, so it's excluded rather than silently
  scored as false -- structurally missing, not a temporary gap; fixing it
  needs an S04 extraction change, not a scoring change.
- compensation_alignment_score: mean of has_clawback_policy / has_psu_plan
  (both ~495/500, high-confidence booleans) and performance_period_years
  (capped at 3 years -> 100; longer LTI performance periods reward
  longer-term thinking, per the spec).
- board_independence_score: mean of (independent directors / board size) and
  whether a lead independent director is named. The ratio (135/500 -- needs
  both `independent_director_count` and `board_size` trusted) is real,
  graded evidence; for the other ~360 companies this score rests on
  `lead_independent_director` alone, a single yes/no fact. Both produce a
  number under the same column, so data_confidence_pct distinguishes them --
  full confidence when the ratio is present, partial when it's the lone
  flag. Weight is deliberately the lowest of the five per the spec's own
  note: real and easy to pull, but weakly related to sustainability.
- controversy_score: real, from EPA ECHO (S18) penalty totals -- universe-wide
  percentile rank (498/500 covered), not sector-relative, since most
  companies genuinely have $0 in EPA penalties and that tie shouldn't be
  split arbitrarily by sector. S11 (Violation Tracker) still has no public
  API and remains unbuilt; S28/S29 haven't been pulled. NOT
  `esg_controversy_level_external` (S14): that field is validation-only by
  contract and must never enter a pillar score.

A company's governance_score_raw is a weighted average over whichever
sub-scores it actually has (renormalized), never a silent worst-case default
for a missing one -- see WEIGHTS.

Missing data on a sub-score doesn't mean one thing, though. This pillar
distinguishes two kinds of "missing" (a third, structural zero -- e.g. no
buyback program -- is handled inside each sub-score function above via
.fillna(0) on the raw input, never here):

- PIPELINE_GAP_INDICATORS: null because the data source hasn't been pulled
  for effectively the whole universe -- nobody's fault, and renormalizing
  around it for free is correct. Empty right now: all five spec indicators
  have real data as of this session (S04 proxy extraction, S18 EPA ECHO),
  so there is currently no governance sub-score that's systematically
  unpulled. Kept as an explicit (empty) list, not removed, because the next
  sub-score this pillar adds may start life exactly this way.
- Everything else in WEIGHTS is a disclosure gap by default: this company
  specifically doesn't have a climate oversight committee disclosed, a
  clawback policy, an independence ratio, etc., while its peers do. That's
  a real signal about the company, not a data-pull artifact, so it no
  longer renormalizes for free -- governance_score applies an explicit
  coverage penalty on top of governance_score_raw:

      governance_score = governance_score_raw * (0.6 + 0.4 * governance_disclosure_coverage)

  governance_disclosure_coverage is weight_sum restricted to
  disclosure-gap indicators (here, all five, since PIPELINE_GAP_INDICATORS
  is empty) divided by their total weight -- 1.0 when every disclosure-gap
  indicator is present, scaling down toward the 0.6 floor as more of them
  go missing. The 0.6 floor means even a company disclosing almost nothing
  keeps 60% of its raw score, rather than being driven toward 0 purely for
  under-disclosing -- raw_score already reflects what it does disclose;
  this penalty is about the disclosure gap itself, a separate signal.
  governance_score_raw is kept in the output for auditability -- so the
  size of the penalty is always visible, not just its result.

data_confidence_pct is a different, complementary signal and is untouched
by any of the above: how much of the composite rests on strong evidence (a
real ratio, most/all of a multi-part indicator's components) versus a
single weak flag or a partial reading -- not the same thing as
n_indicators_available (how many sub-scores exist) or
governance_disclosure_coverage (whether they exist at all); a sub-score can
be present, confidently evidenced, and still count toward disclosure
coverage identically to one that's present but weakly evidenced. This
project doesn't yet have a case where a sub-score is simultaneously
present-but-low-confidence AND its absence would matter for coverage in a
different company, but the two signals are kept orthogonal on purpose.
"""
from pathlib import Path

import pandas as pd

from score_calculation.coverage import (
    apply_disclosure_penalty,
    disclosure_coverage,
    renormalized_average,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
WIDE_PATH = DATA_DIR / "wide_FY2025_fallback.csv"
OUTPUT_PATH = DATA_DIR / "governance_scores.csv"

# Provisional -- revisit once controversy actually has data to look at.
# board_independence_score's weight was cut from 0.10 to 0.05 (moved to
# climate_governance_score) per the spec's own explicit caution that it's
# "weakly related to sustainability" -- already the lowest weight here, cut
# further rather than left level with indicators that are actually
# climate-specific.
WEIGHTS = {
    "capital_stewardship_score": 0.25,
    "climate_governance_score": 0.30,
    "compensation_alignment_score": 0.15,
    "board_independence_score": 0.05,
    "controversy_score": 0.25,
}

# Sub-indicators in WEIGHTS that are null because the data source isn't
# pulled for the whole universe (not the company's fault) rather than
# because this specific company doesn't disclose. See the module docstring.
# Empty right now -- all five have real data -- kept explicit for whatever
# joins this pillar next in that state.
PIPELINE_GAP_INDICATORS: set[str] = set()

FULL_CONFIDENCE = 1.0
PARTIAL_CONFIDENCE = 0.5


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


def _climate_governance_score(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Mean of whichever of the 3 available booleans a company has -- never
    all 4 of the spec's, since S04 doesn't emit comp_tied_to_emissions_target.
    Confidence scales with how many of the 3 actually resolved -- a
    low-recall extraction rule means "only 1 of 3 found" is a real, weaker
    reading, not just a smaller sample.
    """
    components = pd.concat([
        df["has_climate_oversight_committee"] * 100,
        df["has_third_party_assurance"] * 100,
        df["emissions_boundary_stated"] * 100,
    ], axis=1)
    score = components.mean(axis=1, skipna=True)
    confidence = (components.notna().sum(axis=1) / components.shape[1]).where(score.notna())
    return score, confidence


def _compensation_alignment_score(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
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
    score = components.mean(axis=1, skipna=True)
    confidence = (components.notna().sum(axis=1) / components.shape[1]).where(score.notna())
    return score, confidence


def _board_independence_score(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Mean of (independent directors / board size) and whether a lead
    independent director is named. Needs board_size > 0 for the ratio half.
    Confidence is full when the ratio is present (graded, real evidence),
    partial when the score rests on the lead-director flag alone.
    """
    ratio_component = (100 * df["independent_director_count"] / df["board_size"]).where(df["board_size"] > 0)
    lead_component = df["lead_independent_director"] * 100
    components = pd.concat([ratio_component, lead_component], axis=1)
    score = components.mean(axis=1, skipna=True)
    confidence = ratio_component.notna().map({True: FULL_CONFIDENCE, False: PARTIAL_CONFIDENCE}).where(score.notna())
    return score, confidence


def _controversy_score(df: pd.DataFrame) -> pd.Series:
    """Penalty totals from EPA ECHO (S18) -- court/agency enforcement
    records, not news sentiment. NOT `esg_controversy_level_external` (S14):
    that field is validation-only by contract and must never enter a pillar
    score.

    Ranked by percentile across the whole universe (not per-sector): most
    companies genuinely have $0 in EPA penalties, so the tied-at-zero group
    all lands at the same score rather than an arbitrary 100. Real, nonzero
    penalties then rank below that.

    Known limitation, not fixed here: the spec's own note says penalty COUNT
    correlates with facility count and should be normalised per facility --
    S18 doesn't carry a reliable facility count for every company, so this
    is an absolute-dollar ranking, not an intensity measure. A large
    single-facility company and a large multi-facility one with the same
    total penalty read identically here.
    """
    penalty = df["penalty_total_usd"]
    pct_rank = penalty.rank(pct=True, method="average")
    return (100 * (1 - pct_rank)).where(penalty.notna())


def compute_governance_scores() -> pd.DataFrame:
    df = pd.read_csv(WIDE_PATH)

    df["capital_stewardship_score"] = _capital_stewardship_score(df)
    df["capital_stewardship_score_confidence"] = df["capital_stewardship_score"].notna().map(
        {True: FULL_CONFIDENCE, False: float("nan")}
    )
    df["climate_governance_score"], df["climate_governance_score_confidence"] = _climate_governance_score(df)
    df["compensation_alignment_score"], df["compensation_alignment_score_confidence"] = _compensation_alignment_score(df)
    df["board_independence_score"], df["board_independence_score_confidence"] = _board_independence_score(df)
    df["controversy_score"] = _controversy_score(df)
    df["controversy_score_confidence"] = df["controversy_score"].notna().map(
        {True: FULL_CONFIDENCE, False: float("nan")}
    )

    sub_cols = list(WEIGHTS)
    weights = pd.Series(WEIGHTS)
    df["governance_score_raw"], weight_matrix, _ = renormalized_average(df, sub_cols, weights)
    df["n_indicators_available"] = df[sub_cols].notna().sum(axis=1)

    # Coverage penalty: renormalize category-2 (pipeline-gap) indicators out
    # for free, but category-3 (disclosure-gap) ones dock the score. See the
    # module docstring.
    disclosure_cols = [c for c in sub_cols if c not in PIPELINE_GAP_INDICATORS]
    df["governance_disclosure_coverage"] = disclosure_coverage(weight_matrix, weights, disclosure_cols)
    df["governance_score"] = apply_disclosure_penalty(df["governance_score_raw"], df["governance_disclosure_coverage"])

    confidence_cols = [f"{c}_confidence" for c in sub_cols]
    confidence_weights = weights.rename(lambda c: f"{c}_confidence")
    confidence_score, _, _ = renormalized_average(df, confidence_cols, confidence_weights)
    df["data_confidence_pct"] = 100 * confidence_score

    columns = [
        "ticker", "company", "sector",
        "capex_usd", "rnd_expense_usd", "buybacks_usd", "dividends_paid_usd",
        *sub_cols, "n_indicators_available", "data_confidence_pct",
        "governance_score_raw", "governance_disclosure_coverage", "governance_score",
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
    print(result[["governance_score_raw", "governance_score", "data_confidence_pct"]].describe())

    penalized = result[result["governance_disclosure_coverage"] < 1.0]
    print(f"\nDisclosure coverage < 1.0: {len(penalized)}/{len(result)} companies.")
    if len(penalized):
        diff = penalized["governance_score_raw"] - penalized["governance_score"]
        print(f"Average raw-vs-adjusted point difference for those companies: {diff.mean():.2f}")
    print(f"\nSaved to {OUTPUT_PATH}")
