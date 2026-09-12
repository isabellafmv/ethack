"""Final sustainability score: the three pillar scores combined into one
number per company.

Reads each pillar's own output CSV directly (all three read
data/wide_FY2025_fallback.csv independently, so re-run them first if the
underlying data has moved):

    python -m score_calculation.environmental.environmental_score
    python -m score_calculation.transition.transition_score
    python -m score_calculation.governance.governance_score
    python -m score_calculation.final_score

PILLAR_WEIGHTS are equal (1/3 each) -- provisional, and deliberately mirrors
web/src/scoring's defaultWeights() (P1=P2=P3=1, normalised), so the Python
and TypeScript sides start from the same assumption even though nothing
forces them to move together. Revisit once there's a reason to weight one
pillar over another; nothing in the spec argues for unequal pillar weights
the way it argues for unequal sub-score weights within a pillar.

final_score is a weighted average over whichever pillars a company actually
has (renormalized), same pattern as every pillar file's own sub-score
combination -- a company missing a whole pillar (right now, always P1: it's
the only one not at 500/500) is not penalized to zero for that pillar, but
n_pillars_available says so explicitly, and a company scored on 2 of 3
pillars is a materially different claim than one scored on all 3.

data_confidence_pct is the same renormalized-average pattern one level up:
transition_score.py and governance_score.py each already carry their own
data_confidence_pct (how much of THAT pillar rests on real vs. modelled/
partial evidence); environmental_score.py doesn't track one yet since its
only real indicator (input_efficiency_score) has no measured/modelled tier
to distinguish, so it's treated as full confidence whenever present. This
number answers a different question than n_pillars_available: two companies
scored on the same 3 pillars can still rest on very different depths of
real evidence within them.

"""
from pathlib import Path

import pandas as pd

from score_calculation.coverage import renormalized_average

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ENVIRONMENTAL_PATH = DATA_DIR / "environmental_scores.csv"
TRANSITION_PATH = DATA_DIR / "transition_scores.csv"
GOVERNANCE_PATH = DATA_DIR / "governance_scores.csv"
OUTPUT_PATH = DATA_DIR / "final_scores.csv"

PILLAR_WEIGHTS = {
    "environmental_score": 1 / 3,
    "transition_score": 1 / 3,
    "governance_score": 1 / 3,
}

FULL_CONFIDENCE = 1.0


def compute_final_scores() -> pd.DataFrame:
    env = pd.read_csv(ENVIRONMENTAL_PATH)[["ticker", "company", "sector", "environmental_score"]]
    tra = pd.read_csv(TRANSITION_PATH)[["ticker", "transition_score", "data_confidence_pct"]].rename(
        columns={"data_confidence_pct": "transition_score_confidence"}
    )
    gov = pd.read_csv(GOVERNANCE_PATH)[["ticker", "governance_score", "data_confidence_pct"]].rename(
        columns={"data_confidence_pct": "governance_score_confidence"}
    )

    df = env.merge(tra, on="ticker", how="outer").merge(gov, on="ticker", how="outer")
    # transition/governance carry their own confidence as a 0-100 percentage;
    # rescale to 0-1 so it's on the same footing as environmental's FULL_CONFIDENCE
    # below, and so the weighted average only needs one final *100.
    df["transition_score_confidence"] = df["transition_score_confidence"] / 100
    df["governance_score_confidence"] = df["governance_score_confidence"] / 100
    df["environmental_score_confidence"] = df["environmental_score"].notna().map(
        {True: FULL_CONFIDENCE, False: float("nan")}
    )

    pillar_cols = list(PILLAR_WEIGHTS)
    weights = pd.Series(PILLAR_WEIGHTS)
    df["final_score"], _, _ = renormalized_average(df, pillar_cols, weights)
    df["n_pillars_available"] = df[pillar_cols].notna().sum(axis=1)

    confidence_cols = [f"{c}_confidence" for c in pillar_cols]
    confidence_renamed = pd.Series(PILLAR_WEIGHTS).rename(lambda c: f"{c}_confidence")
    confidence_score, _, _ = renormalized_average(df, confidence_cols, confidence_renamed)
    df["data_confidence_pct"] = 100 * confidence_score

    columns = [
        "ticker", "company", "sector",
        "environmental_score", "transition_score", "governance_score",
        "n_pillars_available", "data_confidence_pct", "final_score",
    ]
    return df[columns].sort_values("ticker").reset_index(drop=True)


if __name__ == "__main__":
    result = compute_final_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    scored = result["final_score"].notna().sum()
    print(f"Scored {scored}/{len(result)} companies.")
    print("Pillars available per company:")
    print(result["n_pillars_available"].value_counts().sort_index())
    print()
    print(result[["environmental_score", "transition_score", "governance_score",
                  "data_confidence_pct", "final_score"]].describe())
    print(f"\nSaved to {OUTPUT_PATH}")
