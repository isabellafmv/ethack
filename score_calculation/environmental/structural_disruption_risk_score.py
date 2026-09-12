from pathlib import Path

from score_calculation.category_score_utils import score_category


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parents[2] / "data"
    score_category(
        "structural_disruption_risk",
        data_dir / "structural_disruption_risk_scores.csv",
    )
