from pathlib import Path

from category_score_utils import score_category


if __name__ == "__main__":
    score_category(
        "resource_efficiency",
        Path("data/resource_efficiency_scores.csv"),
    )
