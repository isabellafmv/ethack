"""S15 — EPA GHGRP facility emissions and parent-company ownership.

Two inputs, either downloadable or dropped in by hand:

  1. "Reported Parent Companies" — facility, parent, ownership %.  XLSB, so
     `pip install pyxlsb`. https://www.epa.gov/ghgreporting/data-sets
  2. Facility emissions by year — the FLIGHT export, or Envirofacts:
     https://data.epa.gov/efservice/

Set GHGRP_PARENT_URL / GHGRP_EMISSIONS_URL to fetch directly, or save the files
into data/ with 'parent' and 'emissions' (or 'flight') in their names.

Coverage is ~69 of the S&P 500 — but those carry roughly 82% of the index's
reported Scope 1. Deep, not broad. Do not read a low match count as failure.
"""

from __future__ import annotations

import argparse
import os

from ...common import cache
from ...common.paths import DATA

SOURCE = "S15"
ENDPOINT = "https://www.epa.gov/ghgreporting/data-sets"

#: Direct links from the EPA data-sets page. The parent file carries facility,
#: parent and ownership %; the summary zip carries facility emissions by year.
#: If the parent file already includes an emissions column, the zip is optional
#: -- extract.py uses whichever it finds.
DEFAULT_URLS = {
    "parent": ("https://www.epa.gov/system/files/other-files/2024-10/"
               "ghgp_data_parent_company.xlsb"),
    "emissions": ("https://www.epa.gov/system/files/other-files/2024-10/"
                  "2023_data_summary_spreadsheets.zip"),
}
OPTIONAL = {"emissions"}
#: Patterns are DELIBERATELY narrow. An earlier version matched "*emission*.csv"
#: and silently ingested a teammate's own ticker-level output from data/ as if
#: it were EPA facility data — joined against nothing and produced 500 blanks
#: with no error. A loose glob over a shared folder is an unforced bug.
WANTED = {
    "parent": ["ghgp_data_parent_company*.xlsb", "*ghgp*parent*.xls*"],
    "emissions": ["*data_summary_spreadsheets*.zip", "ghgp_data_20*.xlsx",
                  "*flight*.xlsx", "*flight*.csv"],
}


def _find(patterns):
    for pat in patterns:
        hits = sorted(DATA.glob(pat))
        if hits:
            return hits[0]
    return None


def pull(ticker_list=None, *, limit=None, verbose: bool = True) -> dict:
    got, missing = {}, []
    for kind, patterns in WANTED.items():
        # L1 is an archive, not a performance trick: if it is already here,
        # do not spend 8 MB and a minute fetching it again.
        already = [sfx for sfx in (".xlsb", ".xlsx", ".zip", ".csv")
                   if cache.has_raw(SOURCE, kind, sfx)]
        if already and not os.environ.get(f"GHGRP_{kind.upper()}_URL", "").strip():
            got[kind] = f"already cached ({already[0]})"
            continue
        # The known EPA URL beats a local file unless the local one is already
        # cached — we want the real dataset, not whatever happens to sit in data/.
        local_first = _find(patterns)
        url = (os.environ.get(f"GHGRP_{kind.upper()}_URL", "").strip()
               or ("" if local_first else DEFAULT_URLS.get(kind, "")))
        if url:
            from ...common.http import PoliteSession
            sess = PoliteSession(SOURCE, "ETH Hackathon sustainability research", 1)
            suffix = "." + url.rsplit(".", 1)[-1].split("?")[0][:4]
            data = sess.get(url, key=kind, suffix=suffix)
            cache.put_raw(SOURCE, kind, data, suffix)
            got[kind] = f"url ({len(data) // 1024} KB)"
            continue
        local = _find(patterns)
        if local is None:
            missing.append(kind)
            continue
        cache.put_raw(SOURCE, kind, local.read_bytes(), local.suffix.lower())
        got[kind] = f"{local.name} ({local.stat().st_size // 1024} KB)"

    missing = [m for m in missing if m not in OPTIONAL]
    if missing:
        raise FileNotFoundError(
            f"GHGRP input(s) not found: {', '.join(missing)}.\n"
            f"  Download from {ENDPOINT}:\n"
            f"    - 'Reported Parent Companies' (XLSB) -> data/, name contains 'parent'\n"
            f"    - facility emissions (FLIGHT export) -> data/, name contains 'flight'\n"
            f"  Or set GHGRP_PARENT_URL / GHGRP_EMISSIONS_URL.\n"
            f"  Note: the parent file is XLSB — pip install pyxlsb"
        )
    if verbose:
        for k, v in got.items():
            print(f"[S15] cached {k}: {v}")
    return got


def main() -> None:
    argparse.ArgumentParser(description="S15 fetch GHGRP inputs").parse_args()
    pull()


if __name__ == "__main__":
    main()
