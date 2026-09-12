"""Match S&P 500 companies to their own EPA GHGRP facilities via the
"Parent Company" crosswalk, and roll up ownership-weighted Scope 1 emissions.

This is the "measured" tier from the spec: real, facility-level, EPA-verified
emissions for the subset of companies (spec estimates ~69, carrying ~82% of
the index's reported Scope 1) that operate large US-reporting facilities.
Everyone else falls back to the sector-average proxy in transition_score.py.

Sources:
- https://www.epa.gov/system/files/other-files/2024-10/2023_data_summary_spreadsheets.zip
  ("Direct Point Emitters" sheet) -- facility-level measured Scope 1.
- https://www.epa.gov/system/files/other-files/2024-10/ghgp_data_parent_company.xlsb
  -- facility -> self-declared parent company + ownership %, the entity-
  resolution layer that makes per-company rollup possible.
"""
import io
import zipfile
from pathlib import Path

import pandas as pd
import pyxlsb
import requests

from score_calculation.transition.data_sources.name_matching import best_match, normalize_name

COMPANIES_PATH = Path("data/sp500_companies.csv")
OUTPUT_PATH = Path("data/epa_ghgrp_company_matches.csv")

CACHE_DIR = Path("data/.cache")
FACILITIES_XLSX = CACHE_DIR / "ghgp_data_2023.xlsx"
PARENT_XLSB = CACHE_DIR / "ghgp_parent_company.xlsb"

FACILITIES_ZIP_URL = "https://www.epa.gov/system/files/other-files/2024-10/2023_data_summary_spreadsheets.zip"
PARENT_XLSB_URL = "https://www.epa.gov/system/files/other-files/2024-10/ghgp_data_parent_company.xlsb"
USER_AGENT = "sp500-sustainability-map research-contact@example.com"


def _ensure_cached(path: Path, fetch_fn) -> None:
    if not path.exists():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fetch_fn(path)


def _fetch_facilities_xlsx(path: Path) -> None:
    resp = requests.get(FACILITIES_ZIP_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open("ghgp_data_2023.xlsx") as member, open(path, "wb") as out:
            out.write(member.read())


def _fetch_parent_xlsb(path: Path) -> None:
    resp = requests.get(PARENT_XLSB_URL, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    path.write_bytes(resp.content)


def _load_parent_company_2023() -> pd.DataFrame:
    with pyxlsb.open_workbook(str(PARENT_XLSB)) as wb, wb.get_sheet("2023") as sheet:
        rows = [[c.v for c in row] for row in sheet.rows()]
    return pd.DataFrame(rows[1:], columns=rows[0])


def match_ghgrp_emissions() -> pd.DataFrame:
    _ensure_cached(FACILITIES_XLSX, _fetch_facilities_xlsx)
    _ensure_cached(PARENT_XLSB, _fetch_parent_xlsb)

    facilities = pd.read_excel(FACILITIES_XLSX, sheet_name="Direct Point Emitters", header=3)
    facilities = facilities[["Facility Id", "Total reported direct emissions"]].dropna()
    facilities["Facility Id"] = facilities["Facility Id"].astype(int)

    parents = _load_parent_company_2023()
    parents = parents[["GHGRP FACILITY ID", "PARENT COMPANY NAME", "PARENT CO. PERCENT OWNERSHIP"]].dropna(
        subset=["GHGRP FACILITY ID", "PARENT COMPANY NAME"]
    )
    parents["GHGRP FACILITY ID"] = parents["GHGRP FACILITY ID"].astype(int)
    parents["PARENT CO. PERCENT OWNERSHIP"] = parents["PARENT CO. PERCENT OWNERSHIP"].fillna(100.0)

    joined = facilities.merge(parents, left_on="Facility Id", right_on="GHGRP FACILITY ID", how="inner")
    joined["attributed_emissions_tco2e"] = (
        joined["Total reported direct emissions"] * joined["PARENT CO. PERCENT OWNERSHIP"] / 100.0
    )
    joined["normalized_parent"] = joined["PARENT COMPANY NAME"].apply(normalize_name)

    parent_totals = (
        joined.groupby("normalized_parent")
        .agg(
            ghgrp_emissions_tco2e=("attributed_emissions_tco2e", "sum"),
            facility_count=("Facility Id", "nunique"),
        )
        .reset_index()
    )
    parent_lookup = parent_totals.set_index("normalized_parent").to_dict("index")
    parent_names = list(parent_lookup.keys())

    companies = pd.read_csv(COMPANIES_PATH)
    rows = []
    for _, row in companies.iterrows():
        normalized = normalize_name(row["company"])
        match, match_quality = best_match(normalized, parent_lookup, parent_names)

        rows.append({
            "ticker": row["ticker"],
            "company": row["company"],
            "sector": row["sector"],
            "ghgrp_matched": match is not None,
            "match_quality": match_quality,
            "ghgrp_emissions_tco2e": match["ghgrp_emissions_tco2e"] if match else None,
            "ghgrp_facility_count": match["facility_count"] if match else 0,
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    result = match_ghgrp_emissions()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    matched = result["ghgrp_matched"].sum()
    fuzzy = (result["match_quality"] == "fuzzy").sum()
    print(f"Matched {matched}/{len(result)} companies to GHGRP parent-company records ({fuzzy} via fuzzy match).")
    print(f"(Spec estimate for this source: ~69 companies, ~82% of index Scope 1.)")
    print(f"Saved to {OUTPUT_PATH}")
