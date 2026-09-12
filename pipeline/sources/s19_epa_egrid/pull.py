"""S19 — fetch to the L1 raw cache. NO PARSING, NO JSONL.

See SOURCE.md in this folder for the full brief, endpoint and gotchas.

Contract:
  * network in, bytes to cache/raw/S19/ out
  * idempotent: a second run makes zero network calls
  * never writes observations, never touches the database
"""

from __future__ import annotations

import argparse
import re

from ...common import cache
from ...common.http import PoliteSession

SOURCE = "S19"
DOWNLOAD_PAGE = "https://www.epa.gov/egrid/download-data"
UA = "ETH Hackathon sustainability research (academic, non-commercial)"


def _session():
    return PoliteSession(SOURCE, UA, per_second=1.0)


def _find_xlsx_url(sess: PoliteSession) -> str:
    """The download page links to a dated file (egrid<year>_data_rev<n>.xlsx);
    scrape the link rather than hardcoding a filename that will go stale.
    Prefers the non-'_metric' workbook (short tons, matching this project's
    other US-sourced tonnage figures) and the highest revision number.
    """
    html = sess.get_text(DOWNLOAD_PAGE, key="download-page", suffix=".html")
    candidates = re.findall(r'href="(https://www\.epa\.gov/system/files/documents/[^"]+?egrid\d{4}_data(?:_rev\d+)?\.xlsx)"', html)
    if not candidates:
        raise RuntimeError(f"S19: no eGRID data workbook link found on {DOWNLOAD_PAGE}")
    candidates.sort()  # later years / higher rev numbers sort last
    return candidates[-1]


def pull(*, limit: int | None = None) -> dict:
    """Fetch the eGRID workbook (~20MB) once. `limit` is accepted for
    interface consistency with other sources but does nothing -- there is
    one file, not one fetch per company.

    The resolved URL is cached as small L2 metadata (not just embedded in
    the workbook's own cache key) so extract.py can read it back without
    ever re-touching the network to re-derive it.
    """
    sess = _session()
    url = _find_xlsx_url(sess)
    data = sess.get(url, key="egrid-workbook", suffix=".xlsx", timeout=120)
    cache.put_extracted("_S19", "workbook_url", {"url": url})
    return {"workbook_url": url, "bytes": len(data)}


def main() -> None:
    ap = argparse.ArgumentParser(description="S19 pull")
    ap.add_argument("--limit", type=int, help="unused, kept for CLI consistency")
    a = ap.parse_args()
    print(pull(limit=a.limit))


if __name__ == "__main__":
    main()
