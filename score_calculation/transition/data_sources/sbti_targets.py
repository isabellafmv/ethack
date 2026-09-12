"""Match S&P 500 companies against the Science Based Targets initiative's
public company/target export, and derive a "regulatory momentum" tier.

Source: https://sciencebasedtargets.org/target-dashboard bulk export
(files.sciencebasedtargets.org/production/files/companies-excel.xlsx),
a real, per-company disclosed dataset -- no scraping or NLP needed.
"""
import difflib
import re
from pathlib import Path

import pandas as pd
import requests

COMPANIES_PATH = Path("data/sp500_companies.csv")
OUTPUT_PATH = Path("data/sbti_matches.csv")
SBTI_XLSX_URL = "https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx"

USER_AGENT = "sp500-sustainability-map research-contact@example.com"

# Ordinal momentum tiers -> 0-100 score. A removed/expired commitment counts as
# "no target" since the company no longer holds a valid one.
MOMENTUM_SCORES = {
    "no_target": 0,
    "committed": 25,
    "targets_set_2c": 50,
    "targets_set_1.5c": 75,
    "net_zero_validated": 100,
}

SUFFIXES = [
    "incorporated", "corporation", "company", "holdings", "holding",
    "group", "limited", "worldwide", "international", "inc", "corp",
    "co", "plc", "ltd", "llc", "na", "sa", "nv", "se", "ag", "the",
]


def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\(class [^)]+\)", "", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name)  # drop punctuation and stray artifacts (e.g. trailing "|")
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens).strip()


def _fuzzy_match_is_safe(query: str, candidate: str) -> bool:
    """Guard against same-edit-distance, different-company collisions
    (e.g. "vertiv" vs "veritiv" are both ratio~0.92 but unrelated firms).
    Single-token names are only ever matched exactly (too risky to fuzz);
    multi-token names must agree on every token but the last.
    """
    query_tokens, candidate_tokens = query.split(), candidate.split()
    if len(query_tokens) == 1 or len(candidate_tokens) == 1:
        return query == candidate
    return query_tokens[:-1] == candidate_tokens[:-1]


def _momentum_tier(row: pd.Series) -> str:
    near_status = row.get("near_term_status")
    near_class = row.get("near_term_target_classification")
    net_zero_status = row.get("net_zero_status")

    if net_zero_status == "Targets set":
        return "net_zero_validated"
    if near_status == "Targets set" and near_class == "1.5°C":
        return "targets_set_1.5c"
    if near_status == "Targets set":
        return "targets_set_2c"
    if near_status == "Committed":
        return "committed"
    return "no_target"


def fetch_sbti_targets() -> pd.DataFrame:
    resp = requests.get(SBTI_XLSX_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

    xlsx_path = Path("data/.sbti_companies_raw.xlsx")
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    xlsx_path.write_bytes(resp.content)

    sbti = pd.read_excel(xlsx_path)
    sbti = sbti[sbti["organization_type"].isin(["Corporate", "Financial Institution"])].copy()
    sbti["normalized_name"] = sbti["company_name"].apply(normalize_name)
    # Prefer the most recently updated record when a company appears more than once.
    sbti = sbti.sort_values("date_updated").drop_duplicates("normalized_name", keep="last")

    sbti_lookup = dict(zip(sbti["normalized_name"], sbti.to_dict("records")))
    sbti_names = list(sbti_lookup.keys())

    companies = pd.read_csv(COMPANIES_PATH)
    rows = []
    for _, row in companies.iterrows():
        normalized = normalize_name(row["company"])
        match = sbti_lookup.get(normalized)
        match_quality = "exact" if match else None

        if match is None:
            close = difflib.get_close_matches(normalized, sbti_names, n=3, cutoff=0.92)
            safe_close = [c for c in close if _fuzzy_match_is_safe(normalized, c)]
            if safe_close:
                match = sbti_lookup[safe_close[0]]
                match_quality = "fuzzy"

        if match is None:
            tier = "no_target"
            near_status = near_class = near_year = net_zero_status = net_zero_year = None
        else:
            tier = _momentum_tier(match)
            near_status = match.get("near_term_status")
            near_class = match.get("near_term_target_classification")
            near_year = match.get("near_term_target_year")
            net_zero_status = match.get("net_zero_status")
            net_zero_year = match.get("net_zero_year")

        rows.append({
            "ticker": row["ticker"],
            "company": row["company"],
            "sector": row["sector"],
            "sbti_matched": match is not None,
            "match_quality": match_quality,
            "near_term_status": near_status,
            "near_term_target_classification": near_class,
            "near_term_target_year": near_year,
            "net_zero_status": net_zero_status,
            "net_zero_year": net_zero_year,
            "momentum_tier": tier,
            "regulatory_momentum_score": MOMENTUM_SCORES[tier],
        })

    return pd.DataFrame(rows)


if __name__ == "__main__":
    result = fetch_sbti_targets()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT_PATH, index=False)

    matched = result["sbti_matched"].sum()
    fuzzy = (result["match_quality"] == "fuzzy").sum()
    print(f"Matched {matched}/{len(result)} companies to SBTi records ({fuzzy} via fuzzy match).")
    print(result["momentum_tier"].value_counts())
    print(f"Saved to {OUTPUT_PATH}")
