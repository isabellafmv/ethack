"""S09 — the SBTi "Companies taking action" export.

SBTi publishes one spreadsheet of every company with a validated target or a
commitment. There is no API and the download URL moves between releases, so
this tries a configured URL and otherwise tells you exactly what to download
and where to put it. A manual download is not a failure mode here — it is one
file, once, and it is the same file everyone else gets.

    export SBTI_URL="<the xlsx/csv link from the SBTi site>"   # optional
    python -m pipeline.sources.s09_sbti.pull

Or: download from https://sciencebasedtargets.org/companies-taking-action
(the "Download data" / export button) and save it into data/ — any filename
containing 'sbti' or 'companies-taking-action' is found automatically.
"""

from __future__ import annotations

import argparse
import os

from ...common import cache
from ...common.paths import DATA

SOURCE = "S09"
ENDPOINT = "https://sciencebasedtargets.org/companies-taking-action"

#: Direct exports linked from the dashboard. "by company" is the WIDE sheet
#: (one row per company, near-term and net-zero side by side) which is what
#: extract.py expects. "by target" is the long form, kept for reference.
DEFAULT_URL = "https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx"
TARGETS_URL = "https://files.sciencebasedtargets.org/production/files/targets-excel.xlsx"
DICTIONARY_URL = ("https://files.sciencebasedtargets.org/production/files/"
                  "Alpha-Dashboard-Data-Dictionary.xlsx")
PATTERNS = ["*sbti*.xlsx", "*sbti*.csv", "*companies-taking-action*.xlsx",
            "*companies-taking-action*.csv", "*target*dashboard*.xlsx"]


def find_local():
    for pat in PATTERNS:
        hits = sorted(DATA.glob(pat)) + sorted((DATA / "raw").glob(pat))
        if hits:
            return hits[0]
    return None


def pull(ticker_list=None, *, limit=None, verbose: bool = True) -> dict:
    url = os.environ.get("SBTI_URL", "").strip() or (
        DEFAULT_URL if not find_local() else "")
    if url:
        from ...common.http import PoliteSession
        sess = PoliteSession(SOURCE, "ETH Hackathon sustainability research", per_second=1)
        suffix = ".xlsx" if ".xls" in url.lower() else ".csv"
        data = sess.get(url, key="sbti_export", suffix=suffix)
        cache.put_raw(SOURCE, "sbti_export", data, suffix)
        if verbose:
            print(f"[S09] downloaded {len(data) / 1024:.0f} KB from SBTI_URL")
        return {"source": "url", "bytes": len(data), "suffix": suffix}

    local = find_local()
    if local is None:
        raise FileNotFoundError(
            f"No SBTi export found.\n"
            f"  Download it from {ENDPOINT} (the export / download-data button)\n"
            f"  and save it into {DATA} — any filename containing 'sbti' works.\n"
            f"  Or set SBTI_URL to the direct link and re-run."
        )
    suffix = local.suffix.lower()
    cache.put_raw(SOURCE, "sbti_export", local.read_bytes(), suffix)
    if verbose:
        print(f"[S09] cached {local.name} ({local.stat().st_size / 1024:.0f} KB)")
    return {"source": str(local), "bytes": local.stat().st_size, "suffix": suffix}


def main() -> None:
    argparse.ArgumentParser(description="S09 fetch the SBTi export").parse_args()
    pull()


if __name__ == "__main__":
    main()
