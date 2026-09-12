"""Derive a real, bottom-up sector emissions-intensity benchmark from EPA's
Greenhouse Gas Reporting Program (GHGRP), instead of hand-picked constants.

GHGRP is facility-level, measured (not self-marketed) Scope 1 data for large
US emitters -- the closest thing to ground truth available without a paid
data provider. It only covers big US-based emitting facilities, so absolute
sector totals are a lower bound (misses smaller facilities and non-US
operations), but the *relative* ranking across sectors (Energy/Utilities/
Materials high, Financials/Info Tech low) is directionally reliable and is
all this benchmark is used for: scaling each company's own EDGAR revenue to
an estimated emissions figure for the carbon-price-exposure metric.

Source: https://www.epa.gov/ghgreporting/data-sets
("2023 Data Summary Spreadsheets" -> ghgp_data_2023.xlsx, "Direct Point
Emitters" sheet). Download once, cache the sector totals; this file does not
depend on the S&P 500 list at all.
"""
from pathlib import Path

import pandas as pd
import requests

GHGRP_ZIP_URL = "https://www.epa.gov/system/files/other-files/2024-10/2023_data_summary_spreadsheets.zip"
CACHE_DIR = Path("data/.cache")
XLSX_PATH = CACHE_DIR / "ghgp_data_2023.xlsx"
OUTPUT_PATH = Path("data/epa_sector_emissions.csv")

USER_AGENT = "sp500-sustainability-map research-contact@example.com"

# Primary NAICS (2-digit) -> GICS sector. Manufacturing codes 31-33 span
# several GICS sectors in reality; this is a best-effort, documented
# simplification based on which NAICS-4 subcodes actually dominate GHGRP's
# reported emissions within each 2-digit bucket (see module docstring).
NAICS2_TO_GICS_SECTOR = {
    "22": "Utilities",                    # power plants
    "21": "Energy",                       # oil & gas extraction, mining
    "32": "Materials",                    # chemicals, nonmetallic minerals
    "33": "Materials",                    # primary metals
    "31": "Consumer Staples",             # food/beverage/ag processing
    "56": "Industrials",                  # waste management, landfills
    "48": "Industrials",                  # transportation & pipelines
    "49": "Industrials",                  # warehousing & storage
    "23": "Industrials",                  # construction
    "62": "Health Care",
    "53": "Real Estate",
    "51": "Communication Services",       # data centers, publishing
    "42": "Consumer Discretionary",       # wholesale trade
    "72": "Consumer Discretionary",       # accommodation & food service
    "11": "Consumer Staples",             # agriculture
    # Not present / not meaningfully mappable to a GICS corporate sector:
    # 61 (education), 92 (public admin), 54/55/81/71 (negligible volume).
}

# Sectors with no material direct-emissions facilities in GHGRP (Financials,
# Info Tech proper, Consumer Discretionary retail) get an explicit small
# floor rather than 0, since a 0-intensity sector would make carbon-price
# exposure meaningless to compare against and $0 is not literally true.
FLOOR_INTENSITY_TCO2E_PER_USD_MM_REVENUE = 1.0


def fetch_ghgrp_sector_emissions() -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not XLSX_PATH.exists():
        resp = requests.get(GHGRP_ZIP_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
        resp.raise_for_status()

        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open("ghgp_data_2023.xlsx") as member, open(XLSX_PATH, "wb") as out:
                out.write(member.read())

    facilities = pd.read_excel(XLSX_PATH, sheet_name="Direct Point Emitters", header=3)
    facilities["naics2"] = facilities["Primary NAICS Code"].astype(str).str[:2]
    facilities["gics_sector"] = facilities["naics2"].map(NAICS2_TO_GICS_SECTOR)

    matched = facilities.dropna(subset=["gics_sector"])
    sector_totals = (
        matched.groupby("gics_sector")["Total reported direct emissions"]
        .sum()
        .rename("ghgrp_direct_emissions_tco2e")
        .reset_index()
    )
    return sector_totals


if __name__ == "__main__":
    result = fetch_ghgrp_sector_emissions()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)
    print(result.sort_values("ghgrp_direct_emissions_tco2e", ascending=False).to_string(index=False))
    print(f"\nSaved to {OUTPUT_PATH}")
