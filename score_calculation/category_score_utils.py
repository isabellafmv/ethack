from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPANIES_PATH = PROJECT_ROOT / "data/sp500_companies.csv"

SECTOR_BASELINES = {
    "resource_efficiency": {
        "Information Technology": 72,
        "Health Care": 68,
        "Financials": 70,
        "Consumer Staples": 65,
        "Industrials": 62,
        "Materials": 58,
        "Energy": 48,
        "Utilities": 55,
        "Real Estate": 60,
        "Consumer Discretionary": 63,
        "Communication Services": 69,
    },
    "structural_disruption_risk": {
        "Information Technology": 52,
        "Health Care": 62,
        "Financials": 58,
        "Consumer Staples": 72,
        "Industrials": 60,
        "Materials": 55,
        "Energy": 50,
        "Utilities": 70,
        "Real Estate": 57,
        "Consumer Discretionary": 54,
        "Communication Services": 56,
    },
    "governance_capital_stewardship": {
        "Information Technology": 65,
        "Health Care": 64,
        "Financials": 62,
        "Consumer Staples": 68,
        "Industrials": 63,
        "Materials": 58,
        "Energy": 56,
        "Utilities": 70,
        "Real Estate": 60,
        "Consumer Discretionary": 61,
        "Communication Services": 63,
    },
}


def score_category(category: str, output_path: Path) -> None:
    companies = pd.read_csv(COMPANIES_PATH)
    if "sector" not in companies.columns:
        raise ValueError("The company CSV must contain a 'sector' column.")

    baselines = SECTOR_BASELINES[category]
    result = companies[["ticker", "company", "sector"]].copy()
    result["score"] = result["sector"].map(baselines).fillna(0).astype(int)
    result = result.rename(columns={"score": f"{category}_score"})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)
    print(f"Scored {len(result)} companies.")
    print(f"Saved results to {output_path}")
