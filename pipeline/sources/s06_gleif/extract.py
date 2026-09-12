"""S06 — raw cache to Observation records. NO NETWORK.

This must keep working at hour 20 with the wifi off. If it needs the network,
the missing fetch belongs in pull.py.

Matching rule: accept a GLEIF record ONLY if entities.normalise_name(its
legalName) == normalise_name(our company name) exactly. GLEIF's own search
ranking is not trustworthy for this (verified live -- see pull.py) so the
candidate pool from pull.py is treated as unranked, and this file does the
real selection. When more than one candidate normalises to the same name
(a real US subsidiary sharing a name with a foreign registered parent, e.g.
Accenture), the candidate whose legalAddress.country matches the ticker's
own headquarters country wins; with no country info to break the tie, or no
match at all, the field is written as not_disclosed rather than guessed --
a wrong LEI is worse than a missing one, since other joins may trust it.

Written as STRUCTURAL, not IMPUTED: unlike S18's substring facility-name
search, this is an exact match after normalisation, not a loose one.
"""

from __future__ import annotations

import argparse
import json

from ...common import cache
from ...common.entities import normalise_name, tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

SOURCE = "S06"

#: Headquarters in universe.csv is a US state name for domestic companies,
#: or a country name for the rest. Only the non-US countries that actually
#: appear need mapping -- this is a closed lookup, not a geocoder.
_HQ_COUNTRY = {
    "bermuda": "BM", "canada": "CA", "ireland": "IE",
    "netherlands": "NL", "switzerland": "CH", "united kingdom": "GB",
}


def _expected_country(headquarters: str | None) -> str | None:
    if not headquarters:
        return None
    tail = headquarters.split(",")[-1].strip().lower().rstrip("[0123456789]").strip()
    if tail in _HQ_COUNTRY:
        return _HQ_COUNTRY[tail]
    if tail in ("none", ""):
        return None
    return "US"  # anything else in that column is a US state name


def _best_match(records: list[dict], company: str, expected_country: str | None) -> dict | None:
    target = normalise_name(company)
    candidates = [
        r for r in records
        if normalise_name(r["attributes"]["entity"]["legalName"]["name"]) == target
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if expected_country:
        by_country = [r for r in candidates
                       if r["attributes"]["entity"]["legalAddress"]["country"] == expected_country]
        if len(by_country) == 1:
            return by_country[0]
    return None  # genuinely ambiguous -- not_disclosed beats a coin flip


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    ticker_list = ticker_list or tickers(limit)

    with ObservationWriter(SOURCE) as w:
        for ticker in ticker_list:
            raw = cache.get_raw(SOURCE, ticker, ".json")
            if raw is None:
                continue

            payload = json.loads(raw)
            url = payload.get("query_url") or "https://api.gleif.org/api/v1/lei-records"
            result = payload.get("result")
            records = (result or {}).get("data") or []

            match = None
            if payload.get("company") and records:
                match = _best_match(records, payload["company"],
                                     _expected_country(payload.get("headquarters")))

            if match is None:
                for field in ("legal_name", "lei", "ultimate_parent_lei"):
                    w.write(Observation(
                        ticker=ticker, field=field, value=None, unit=None,
                        fiscal_year=0, period_end=None, quote=None,
                        source=SOURCE, source_url=url,
                        source_section="lei-records:entity.legalName",
                        extracted_by="rule:gleif_exact_name_match",
                        status=Status.NOT_DISCLOSED,
                    ))
                continue

            attrs = match["attributes"]
            lei = match["id"]
            legal_name = attrs["entity"]["legalName"]["name"]
            ultimate_parent = (
                match.get("relationships", {})
                     .get("ultimate-parent", {})
                     .get("data")
            )
            ultimate_parent_lei = ultimate_parent["id"] if ultimate_parent else None

            w.write(Observation(
                ticker=ticker, field="legal_name", value=legal_name, unit=None,
                fiscal_year=0, period_end=None, quote=None,
                source=SOURCE, source_url=url,
                source_section="lei-records:entity.legalName",
                extracted_by="rule:gleif_exact_name_match",
                status=Status.STRUCTURAL,
            ))
            w.write(Observation(
                ticker=ticker, field="lei", value=lei, unit=None,
                fiscal_year=0, period_end=None, quote=None,
                source=SOURCE, source_url=url,
                source_section="lei-records:lei",
                extracted_by="rule:gleif_exact_name_match",
                status=Status.STRUCTURAL,
            ))
            if ultimate_parent_lei:
                w.write(Observation(
                    ticker=ticker, field="ultimate_parent_lei", value=ultimate_parent_lei,
                    unit=None, fiscal_year=0, period_end=None, quote=None,
                    source=SOURCE, source_url=f"https://api.gleif.org/api/v1/lei-records/{lei}",
                    source_section="lei-records:relationships.ultimate-parent",
                    extracted_by="rule:gleif_exact_name_match",
                    status=Status.STRUCTURAL,
                ))
            else:
                # No ultimate-parent relationship recorded. For most S&P 500
                # constituents this is the correct, expected answer -- they
                # ARE the top of their own structure -- not a data gap. GLEIF
                # gives no way to distinguish that from "declined to report"
                # without fetching the reporting-exception endpoint, which we
                # don't do here; not_disclosed is the honest middle ground.
                w.write(Observation(
                    ticker=ticker, field="ultimate_parent_lei", value=None, unit=None,
                    fiscal_year=0, period_end=None, quote=None,
                    source=SOURCE, source_url=f"https://api.gleif.org/api/v1/lei-records/{lei}",
                    source_section="lei-records:relationships.ultimate-parent",
                    extracted_by="rule:gleif_exact_name_match",
                    status=Status.NOT_DISCLOSED,
                ))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S06 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    print(extract(tl, limit=a.limit))


if __name__ == "__main__":
    main()
