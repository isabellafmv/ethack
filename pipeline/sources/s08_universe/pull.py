"""S08 — freeze the S&P 500 constituent list.

The register's instruction is the whole job: FREEZE the list at one date and
commit it. Membership changes mid-build silently break every join, and a silent
join break is indistinguishable from a coverage gap.

Two behaviours on purpose:
  * If data/sp500_companies.csv exists, this does NOTHING and does not touch the
    network. The frozen list is the frozen list.
  * Deduplication of dual-class tickers is DETERMINISTIC (first listing wins).
    The original scrape sampled randomly, so two runs produced different
    universes -- which is the exact failure the register warns about.

Use --refreeze to deliberately re-scrape. Expect to explain why.
"""

from __future__ import annotations

import argparse
import io

from ...common.paths import UNIVERSE_PATH, ensure_dirs

SOURCE = "S08"
ENDPOINT = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

RENAMES = {
    "Symbol": "ticker", "Security": "company", "GICS Sector": "sector",
    "GICS Sub-Industry": "sub_industry", "Headquarters Location": "headquarters",
    "Date added": "date_added", "CIK": "cik", "Founded": "founded",
}


def scrape() -> "pandas.DataFrame":
    import pandas as pd
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(ENDPOINT, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    table = BeautifulSoup(resp.text, "lxml").find("table", {"id": "constituents"})
    df = pd.read_html(io.StringIO(str(table)))[0]
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=RENAMES)
    df["ticker_yahoo"] = df["ticker"].str.replace(".", "-", regex=False)

    # Deterministic dedup: keep the FIRST listing of each company. ~503 tickers
    # for 500 companies (dual share classes); which class survives must not
    # change between runs.
    key = df["company"].str.replace(r"\s*\(Class [^)]+\)$", "", regex=True).str.strip()
    df = (df.assign(_k=key).drop_duplicates(subset="_k", keep="first")
            .drop(columns="_k").sort_values("ticker").reset_index(drop=True))
    df["cik"] = df["cik"].astype(str).str.strip().str.zfill(10)
    return df


def pull(ticker_list=None, *, limit=None, refreeze: bool = False) -> dict:
    ensure_dirs()
    if UNIVERSE_PATH.exists() and not refreeze:
        import csv
        rows = list(csv.DictReader(UNIVERSE_PATH.open(encoding="utf-8")))
        return {"frozen": True, "path": str(UNIVERSE_PATH), "companies": len(rows),
                "note": "already frozen; --refreeze to re-scrape"}

    df = scrape()
    df.to_csv(UNIVERSE_PATH, index=False)
    return {"frozen": True, "path": str(UNIVERSE_PATH), "companies": len(df),
            "note": "re-scraped and frozen"}


def main() -> None:
    ap = argparse.ArgumentParser(description="S08 freeze the universe")
    ap.add_argument("--refreeze", action="store_true",
                    help="re-scrape Wikipedia and overwrite the frozen list")
    a = ap.parse_args()
    print(pull(refreeze=a.refreeze))


if __name__ == "__main__":
    main()
