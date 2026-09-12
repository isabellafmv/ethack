"""S13 — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

The canonical write pattern:

        from ...common.jsonl import ObservationWriter

    with ObservationWriter(SOURCE) as w:
        w.write(Observation(
            ticker="AAPL",
            field="revenue_usd",          # must exist in common/fields.py
            value=391035000000.0,
            unit="usd",                   # canonical token, converted already
            fiscal_year=2024,
            period_end="2024-09-28",
            quote=None,                   # structural facts carry no quote
            source=SOURCE,
            source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            source_section="us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            extracted_by="xbrl:RevenueFromContractWithCustomerExcludingAssessedTax",
            status=Status.STRUCTURAL,
        ))
        print(w.summary())

For a number read out of prose, pass the source text and let the validator do
the work — it downgrades a bad quote to quote_failed rather than trusting it:

        w.write(obs, source_text=filing_text)

And when the company said nothing, SAY SO. Skipping the company loses the most
valuable signal in the dataset:

        w.write(Observation(..., value=None, unit=None, quote=None,
                            status=Status.NOT_DISCLOSED, ...))
"""

from __future__ import annotations

import argparse

from ...common.entities import tickers
from ...common.jsonl import ObservationWriter

from .fields import EMITS

SOURCE = "S13"


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raise NotImplementedError(
                "S13 extract() not implemented. See SOURCE.md in this folder. "
                "Emit only: " + ", ".join(EMITS)
            )
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S13 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
