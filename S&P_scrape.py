import io
import requests
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

def scrape_sp500(url: str = URL) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table", {"id": "constituents"})

    df = pd.read_html(io.StringIO(str(table)))[0]

    df.columns = [c.strip() for c in df.columns]
    df = df.rename(
        columns={
            "Symbol": "ticker",
            "Security": "company",
            "GICS Sector": "sector",
            "GICS Sub-Industry": "sub_industry",
            "Headquarters Location": "headquarters",
            "Date added": "date_added",
            "CIK": "cik",
            "Founded": "founded",
        }
    )

    df["ticker_yahoo"] = df["ticker"].str.replace(".", "-", regex=False)

    return df


df = scrape_sp500()
scraped_count = len(df)

# Randomly retain one row when a company has multiple share-class tickers.
company_key = df["company"].str.replace(
    r"\s*\(Class [^)]+\)$", "", regex=True
).str.strip()
df = (
    df.assign(company_key=company_key)
    .sample(frac=1)
    .drop_duplicates(subset="company_key")
    .drop(columns="company_key")
    .sort_index()
    .reset_index(drop=True)
)

print(f"Scraped {scraped_count} S&P 500 listings.")
print(f"Retained {len(df)} unique companies after random deduplication.")
print(f"Different sectors: {df['sector'].nunique()}\n")
print(df.head(10).to_string(index=False))

out_path = Path("data/sp500_companies.csv")
out_path.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(out_path, index=False)
print(f"\nSaved full list to {out_path}")
