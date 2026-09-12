from pathlib import Path

from category_score_utils import score_category


if __name__ == "__main__":
    score_category(
        "governance_capital_stewardship",
        Path("data/governance_capital_stewardship_scores.csv"),
    )
