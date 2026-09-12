from pathlib import Path

from category_score_utils import score_category


if __name__ == "__main__":
    score_category(
        "structural_disruption_risk",
        Path("data/structural_disruption_risk_scores.csv"),
    )
