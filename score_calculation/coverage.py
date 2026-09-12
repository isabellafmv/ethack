"""Shared renormalized-weighted-average and disclosure-coverage-penalty
math, used identically by environmental_score.py, transition_score.py, and
governance_score.py. Extracted once the three-way missing-data taxonomy
(see any of those three modules' docstrings for the full explanation --
structural zero / pipeline gap / disclosure gap) turned out to need the
same dozen lines of pandas in all three places, differing only in which
columns are involved and whether weights are flat or per-sector.

Nothing here decides which sub-indicators are pipeline gaps vs. disclosure
gaps, or what a pillar's WEIGHTS are -- that's a judgment call specific to
each pillar and stays in each pillar's own module.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Floor and slope for the disclosure-coverage penalty: adjusted = raw *
# (FLOOR + SLOPE * coverage). A company disclosing none of a pillar's
# disclosure-gap indicators still keeps FLOOR of its raw score -- the
# penalty is about the size of the gap, not a second judgment on top of
# what the company does disclose.
DISCLOSURE_COVERAGE_FLOOR = 0.6
DISCLOSURE_COVERAGE_SLOPE = 0.4


def renormalized_average(
    df: pd.DataFrame, sub_cols: list[str], weights: pd.Series | pd.DataFrame
) -> tuple[pd.Series, pd.DataFrame, pd.Series]:
    """A weighted average over whichever of `sub_cols` a row actually has,
    renormalized so a missing column drops out of both the numerator and
    the denominator instead of being treated as a zero.

    `weights` is either a Series indexed by `sub_cols` (one flat weight per
    column, the same for every row -- transition_score.py and
    governance_score.py) or a DataFrame sharing df's index and `sub_cols`
    as columns (a per-row weight, e.g. environmental_score.py's per-sector
    materiality weights). Pandas broadcasts either shape correctly against
    the per-row availability mask below.

    Returns (score, weight_matrix, weight_sum). Callers that also need a
    disclosure-coverage penalty reuse weight_matrix rather than
    recomputing it -- see disclosure_coverage().
    """
    available = df[sub_cols].notna()
    weight_matrix = available.astype(float) * weights
    weight_sum = weight_matrix.sum(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        raw = (
            df[sub_cols].fillna(0).to_numpy(dtype=float) * weight_matrix.to_numpy(dtype=float)
        ).sum(axis=1) / weight_sum.to_numpy(dtype=float)
    score = pd.Series(raw, index=df.index).where(weight_sum > 0)
    return score, weight_matrix, weight_sum


def disclosure_coverage(
    weight_matrix: pd.DataFrame, weights: pd.Series | pd.DataFrame, disclosure_cols: list[str]
) -> pd.Series:
    """weight_sum restricted to `disclosure_cols` (the pillar's category-3,
    disclosure-gap sub-indicators), divided by their total available
    weight. Pipeline-gap indicators -- anything not in disclosure_cols --
    don't appear on either side of this fraction, so they neither help nor
    hurt coverage.

    1.0 when every disclosure-gap indicator is present; scales down as
    more of them go missing. See apply_disclosure_penalty() for how this
    number turns into an actual score adjustment.
    """
    if isinstance(weights, pd.Series):
        total = weights[disclosure_cols].sum()
        return weight_matrix[disclosure_cols].sum(axis=1) / total

    total = weights[disclosure_cols].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        coverage = weight_matrix[disclosure_cols].sum(axis=1).to_numpy(dtype=float) / total.to_numpy(dtype=float)
    return pd.Series(coverage, index=weight_matrix.index).where(total > 0)


def apply_disclosure_penalty(raw_score: pd.Series, coverage: pd.Series) -> pd.Series:
    """adjusted_score = raw_score * (0.6 + 0.4 * coverage) -- the one-line
    formula every pillar's docstring describes at length. Kept as a
    function (not inlined) so all three pillars are provably applying the
    exact same shape, not three copies that could quietly drift apart.
    """
    return raw_score * (DISCLOSURE_COVERAGE_FLOOR + DISCLOSURE_COVERAGE_SLOPE * coverage)
