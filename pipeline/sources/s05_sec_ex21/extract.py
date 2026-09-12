"""S05 — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

subsidiary_count is a best-effort count against a format the register
itself warns is "wildly inconsistent": most filers use a 2-3 column table
(name, jurisdiction, sometimes DBA); some use a bulleted or numbered list;
a few just write a paragraph. This tries a table row count first (the
common case, and the most reliable one), then falls back to counting
list/paragraph lines that look like a subsidiary entry. Written STRUCTURAL
regardless -- it is a mechanical count of what is on the page, not a
judgment call, even when the heuristic used to count it is imperfect.
"""

from __future__ import annotations

import argparse
import json
import re

from bs4 import BeautifulSoup

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

SOURCE = "S05"

#: Lines that are exhibit boilerplate, not a subsidiary entry.
_BOILERPLATE = re.compile(
    r"^(exhibit|subsidiar(y|ies)|list of|state or |jurisdiction|name of|"
    r"the registrant|as of|none\.?$)", re.I,
)


def _count_table_rows(soup: BeautifulSoup) -> int | None:
    """The common case: a table of Name | Jurisdiction (| DBA). Picks the
    largest table on the page and counts its non-header, non-empty rows."""
    best = 0
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        data_rows = 0
        for tr in rows:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            if not cells:
                continue
            if _BOILERPLATE.match(cells[0]):
                continue
            data_rows += 1
        best = max(best, data_rows)
    return best or None


def _count_list_lines(soup: BeautifulSoup) -> int:
    """Fallback for paragraph/list-formatted exhibits: count non-empty,
    non-boilerplate lines/list items."""
    items = soup.find_all("li")
    lines = [li.get_text(strip=True) for li in items] if items else []
    if not lines:
        text = soup.get_text("\n")
        lines = [ln.strip() for ln in text.split("\n")]
    count = 0
    for ln in lines:
        if not ln or len(ln) < 3:
            continue
        if _BOILERPLATE.match(ln):
            continue
        count += 1
    return count


def _count_subsidiaries(html: str) -> tuple[int, str]:
    soup = BeautifulSoup(html, "html.parser")
    table_count = _count_table_rows(soup)
    if table_count:
        return table_count, "table_rows"
    return _count_list_lines(soup), "list_lines"


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raw = cache.get_raw(SOURCE, ticker, ".json")
            if raw is None:
                continue

            payload = json.loads(raw)
            filing = payload.get("filing")
            legal_name = payload.get("legal_name")
            fiscal_year = 0
            if filing:
                date_str = filing.get("report_date") or filing.get("filing_date")
                if date_str:
                    fiscal_year = int(date_str[:4])

            if legal_name:
                w.write(Observation(
                    ticker=ticker, field="legal_name", value=legal_name, unit=None,
                    fiscal_year=0, period_end=None, quote=None,
                    source=SOURCE, source_url="https://www.sec.gov/cgi-bin/browse-edgar",
                    source_section="submissions:name",
                    extracted_by="rule:sec_submissions_name",
                    status=Status.STRUCTURAL,
                ))

            html = payload.get("ex21_html")
            if html is None:
                w.write(Observation(
                    ticker=ticker, field="subsidiary_count", value=None, unit=None,
                    fiscal_year=fiscal_year or 0, period_end=None, quote=None,
                    source=SOURCE, source_url="https://www.sec.gov/cgi-bin/browse-edgar",
                    source_section="EX-21.x",
                    extracted_by="rule:ex21_count",
                    status=Status.NOT_DISCLOSED,
                ))
                continue

            count, method = _count_subsidiaries(html)
            acc = filing["accession"]
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(filing['cik'])}/"
                   f"{acc.replace('-', '')}/{acc}-index.html")
            w.write(Observation(
                ticker=ticker, field="subsidiary_count", value=count, unit="count",
                fiscal_year=fiscal_year, period_end=filing.get("report_date"), quote=None,
                source=SOURCE, source_url=url,
                source_section=f"EX-21.x:{method}",
                extracted_by=f"rule:ex21_{method}",
                status=Status.STRUCTURAL,
            ))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S05 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
