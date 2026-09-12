"""Pull per-company Revenue, Operating Income and D&A from SEC EDGAR's XBRL API.

Used as the real-data denominator/scale for the Transition pillar's
carbon-price-exposure metric (EBITDA proxy = OperatingIncomeLoss + D&A).
"""
import time
from pathlib import Path

import pandas as pd
import requests

COMPANIES_PATH = Path("data/sp500_companies.csv")
OUTPUT_PATH = Path("data/company_financials.csv")

USER_AGENT = "sp500-sustainability-map research-contact@example.com"
REQUEST_DELAY_SECONDS = 0.11  # stay under SEC's 10 req/sec limit

REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueServicesNet",
]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
D_AND_A_TAGS = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "DepreciationAndAmortization",
]


def _latest_annual_value(session: requests.Session, cik10: str, tags: list[str]) -> tuple[float | None, int | None]:
    # A filer can switch which XBRL tag it uses for a concept over time (e.g. the
    # ASC 606 revenue-recognition transition around 2018), so the most recent data
    # may live under a different tag than the one that has the longest history.
    # Collect candidates from every tag and keep the globally most recent one.
    candidates = []
    for tag in tags:
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{tag}.json"
        resp = session.get(url, timeout=10)
        time.sleep(REQUEST_DELAY_SECONDS)
        if resp.status_code != 200:
            continue

        facts = resp.json().get("units", {}).get("USD", [])
        annual = [
            f for f in facts
            if f.get("form") == "10-K" and f.get("fp") == "FY" and f.get("val") is not None
        ]
        candidates.extend(annual)

    if not candidates:
        return None, None

    latest = max(candidates, key=lambda f: f["end"])
    return float(latest["val"]), int(latest["end"][:4])


def fetch_financials() -> pd.DataFrame:
    companies = pd.read_csv(COMPANIES_PATH, dtype={"cik": str})
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    rows = []
    for i, row in companies.iterrows():
        cik10 = row["cik"].zfill(10)
        revenue, rev_year = _latest_annual_value(session, cik10, REVENUE_TAGS)
        op_income, _ = _latest_annual_value(session, cik10, OPERATING_INCOME_TAGS)
        d_and_a, _ = _latest_annual_value(session, cik10, D_AND_A_TAGS)

        ebitda_proxy = None
        if op_income is not None:
            ebitda_proxy = op_income + (d_and_a or 0.0)

        rows.append({
            "ticker": row["ticker"],
            "company": row["company"],
            "sector": row["sector"],
            "cik": row["cik"],
            "fiscal_year": rev_year,
            "revenue_usd": revenue,
            "operating_income_usd": op_income,
            "d_and_a_usd": d_and_a,
            "ebitda_proxy_usd": ebitda_proxy,
        })
        print(f"[{i + 1}/{len(companies)}] {row['ticker']}: revenue={revenue}, ebitda_proxy={ebitda_proxy}")

    return pd.DataFrame(rows)


if __name__ == "__main__":
    result = fetch_financials()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    found = result["revenue_usd"].notna().sum()
    print(f"\nFetched financials for {len(result)} companies.")
    print(f"Revenue found for {found}/{len(result)} companies.")
    print(f"Saved to {OUTPUT_PATH}")
