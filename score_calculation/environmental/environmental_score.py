"""Calculate the final Environmental pillar score."""
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RESOURCE_EFFICIENCY_PATH = DATA_DIR / "resource_efficiency_scores.csv"
STRUCTURAL_RISK_PATH = DATA_DIR / "structural_disruption_risk_scores.csv"
OUTPUT_PATH = DATA_DIR / "environmental_scores.csv"


def compute_environmental_scores() -> pd.DataFrame:
    resource = pd.read_csv(RESOURCE_EFFICIENCY_PATH)
    structural = pd.read_csv(STRUCTURAL_RISK_PATH)
    key = ["ticker", "company", "sector"]

    required_resource = set(key) | {"resource_efficiency_score"}
    required_structural = set(key) | {"structural_disruption_risk_score"}
    if missing := required_resource - set(resource.columns):
        raise ValueError(f"{RESOURCE_EFFICIENCY_PATH} is missing columns: {sorted(missing)}")
    if missing := required_structural - set(structural.columns):
        raise ValueError(f"{STRUCTURAL_RISK_PATH} is missing columns: {sorted(missing)}")

    result = resource[key + ["resource_efficiency_score"]].merge(
        structural[key + ["structural_disruption_risk_score"]],
        on=key,
        validate="one_to_one",
    )
    result["environmental_score"] = result[
        ["resource_efficiency_score", "structural_disruption_risk_score"]
    ].mean(axis=1)
    return result


if __name__ == "__main__":
    result = compute_environmental_scores()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    print(f"Scored {len(result)} companies.")
    print(f"Saved results to {OUTPUT_PATH}")
