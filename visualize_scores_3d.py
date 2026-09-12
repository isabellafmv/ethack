from pathlib import Path

import pandas as pd
import plotly.express as px


DATA_DIR = Path("data")
OUTPUT_PATH = DATA_DIR / "sp500_scores_3d.html"

SCORE_FILES = {
    "Environmental": (DATA_DIR / "environmental_scores.csv", "environmental_score"),
    "Transition": (DATA_DIR / "transition_scores.csv", "transition_score"),
    "Governance": (DATA_DIR / "governance_scores.csv", "governance_score"),
}


def load_scores() -> pd.DataFrame:
    merged = None

    for category, (path, score_column) in SCORE_FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing score file: {path}")

        scores = pd.read_csv(path)
        required_columns = {"ticker", "company", "sector", score_column}
        missing = required_columns - set(scores.columns)
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")

        scores = scores[
            ["ticker", "company", "sector", score_column]
        ].rename(columns={score_column: category})

        if merged is None:
            merged = scores
        else:
            merged = merged.merge(scores, on=["ticker", "company", "sector"])

    if merged is None or merged.empty:
        raise ValueError("No company scores were found.")
    return merged


def create_visualization(scores: pd.DataFrame) -> None:
    figure = px.scatter_3d(
        scores,
        x="Environmental",
        y="Transition",
        z="Governance",
        color="sector",
        hover_name="company",
        hover_data={
            "ticker": True,
            "sector": True,
            "Environmental": True,
            "Transition": True,
            "Governance": True,
        },
        title="S&P 500 Pillar Scores",
        labels={
            "Environmental": "Environmental",
            "Transition": "Transition",
            "Governance": "Governance",
        },
    )
    figure.update_traces(marker={"size": 5, "opacity": 0.8})
    figure.update_layout(
        scene={
            "xaxis": {"range": [0, 100]},
            "yaxis": {"range": [0, 100]},
            "zaxis": {"range": [0, 100]},
        },
        legend_title_text="Sector",
        margin={"l": 0, "r": 0, "b": 0, "t": 50},
    )
    figure.write_html(OUTPUT_PATH, include_plotlyjs=True)


if __name__ == "__main__":
    scores = load_scores()
    create_visualization(scores)
    print(f"Visualized {len(scores)} companies.")
    print(f"Saved interactive map to {OUTPUT_PATH}")
