"""ONE client for every SEC source (S01-S05). Do not write four fetchers.

Two reasons this is shared and not per-package:

  1. EDGAR blocks requests whose User-Agent lacks a real contact address. One
     place to get that right.
  2. The 10 req/s limit is per requester, not per script. Four independent
     fetchers each politely doing 10 req/s gets the whole team blocked at hour 3,
     which is unrecoverable inside a 24h build.

Set the contact address once, in the environment:

    export SEC_USER_AGENT="ETH Hackathon Team your.name@example.com"
"""

from __future__ import annotations

import os
from typing import Any

from .http import PoliteSession

SEC_RATE_LIMIT = 8.0   # below the documented 10/s, on purpose
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
COMPANY_CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={q}&forms={forms}"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{doc}"

_client: "SECClient | None" = None


class MissingUserAgent(RuntimeError):
    pass


def pad_cik(cik: str | int) -> str:
    return str(int(str(cik).strip().lstrip("CIK").lstrip("0") or 0)).zfill(10)


def user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        raise MissingUserAgent(
            "SEC_USER_AGENT must be set to a string containing a real contact "
            "email address, e.g.\n\n"
            '    export SEC_USER_AGENT="ETH Hackathon Team you@example.com"\n\n'
            "EDGAR blocks requests without one, and the block is IP-wide."
        )
    return ua


class SECClient:
    """Shared across S01-S05. Get it via `get_client()`, never construct it."""

    def __init__(self, source: str = "SEC"):
        self.session = PoliteSession(source, user_agent(), per_second=SEC_RATE_LIMIT)

    def submissions(self, cik: str | int) -> dict:
        c = pad_cik(cik)
        return self.session.get_json(SUBMISSIONS.format(cik=c), key=f"submissions-{c}")

    def company_facts(self, cik: str | int) -> dict:
        c = pad_cik(cik)
        return self.session.get_json(COMPANY_FACTS.format(cik=c), key=f"facts-{c}")

    def filing_index(self, cik: str | int, form: str = "10-K", limit: int = 3) -> list[dict]:
        """Most recent filings of one form type, newest first."""
        sub = self.submissions(cik)
        recent = sub.get("filings", {}).get("recent", {})
        out = []
        for i, f in enumerate(recent.get("form", [])):
            if f != form:
                continue
            out.append({
                "form": f,
                "accession": recent["accessionNumber"][i],
                "filing_date": recent["filingDate"][i],
                "report_date": recent.get("reportDate", [None] * (i + 1))[i],
                "primary_doc": recent["primaryDocument"][i],
                "cik": pad_cik(cik),
            })
            if len(out) >= limit:
                break
        return out

    def document(self, filing: dict, doc: str | None = None) -> bytes:
        """Fetch one document from a filing. Cached forever by accession."""
        acc = filing["accession"].replace("-", "")
        cik_int = int(filing["cik"])
        name = doc or filing["primary_doc"]
        url = ARCHIVE.format(cik_int=cik_int, accession_nodash=acc, doc=name)
        return self.session.get(url, key=f"{filing['accession']}-{name}", suffix=".html")

    def filing_files(self, filing: dict) -> list[dict]:
        """Everything in a filing, so EX-21 can be located for S05."""
        acc = filing["accession"].replace("-", "")
        cik_int = int(filing["cik"])
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/"
               f"{filing['accession']}-index.json")
        try:
            data = self.session.get_json(url, key=f"index-{filing['accession']}")
        except RuntimeError:
            return []
        return data.get("directory", {}).get("item", [])


def get_client() -> SECClient:
    global _client
    if _client is None:
        _client = SECClient()
    return _client
