"""S19 — raw cache to Observation records. NO NETWORK.

Emits grid_intensity_kgco2e_per_mwh only (not scope2_location_tco2e -- that
needs a company's own electricity consumption to weight the regional rate
by, which nothing has pulled yet; see SOURCE.md).

This is a REGIONAL PROXY, not company data: every company headquartered in
the same state gets the identical value, by construction, because eGRID
publishes one grid-average rate per state, not per company. That is stated
here and in the field's own description, not hidden -- the same honesty
standard as an "imputed" record, even though this qualifies as STRUCTURAL
(machine-readable, no quote possible) since it's a real government number,
just not a company-specific one.

Companies headquartered outside the US (Ireland, UK, Switzerland, Bermuda,
etc. -- ~27 of 500, mostly tax/reincorporation domiciles) have no US grid to
join to. Written as not_disclosed, not skipped -- "no matching state" is a
real, checkable finding, not a silent gap.
"""

from __future__ import annotations

import argparse
import re

from ...common import cache
from ...common.entities import universe
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from .pull import SOURCE

# Standard USPS state abbreviations -- eGRID's ST23 sheet keys on these, the
# S&P 500 universe carries full state names (and non-US country names, which
# deliberately have no entry here).
_STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "D.C.": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME",
    "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI",
    "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX",
    "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "Puerto Rico": "PR",
}

SHORT_TON_TO_KG = 907.18474


def _hq_state(headquarters: str) -> str | None:
    """'North Chicago, Illinois' -> 'Illinois'. Identical to
    s08_universe/extract.py's own _state() -- universe() only carries the
    raw 'headquarters' string, not the already-parsed hq_state field (that's
    itself an OBSERVATION S08 writes, not a column on the frozen CSV), so
    this is reproduced here rather than depending on another source's output.
    """
    if not headquarters or "," not in headquarters:
        return headquarters.strip() or None
    return re.sub(r"\s*\[.*\]$", "", headquarters.rsplit(",", 1)[-1]).strip() or None


def _cached_workbook_url() -> str:
    meta = cache.get_extracted("_S19", "workbook_url")
    if meta is None:
        raise FileNotFoundError(
            "S19: no cached workbook URL -- run `python -m pipeline.sources.s19_epa_egrid.pull` first"
        )
    return meta["url"]


def _load_state_intensity() -> dict[str, float]:
    """{2-letter state abbrev: grid_intensity_kgco2e_per_mwh} from the cached
    eGRID workbook's ST23 sheet. STCO2AN is short tons CO2/year, STNGENAN is
    MWh/year -- ratio converted to kg/MWh.
    """
    import openpyxl

    if not cache.has_raw(SOURCE, "egrid-workbook", ".xlsx"):
        raise FileNotFoundError(
            "S19: no cached eGRID workbook -- run `python -m pipeline.sources.s19_epa_egrid.pull` first"
        )
    path = cache.raw_path(SOURCE, "egrid-workbook", ".xlsx")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["ST23"]

    rows = ws.iter_rows(min_row=2, values_only=True)
    codes = next(rows)  # short-code header row (PSTATABB, STCO2AN, STNGENAN, ...)
    col = {name: i for i, name in enumerate(codes)}

    out = {}
    for row in rows:
        state = row[col["PSTATABB"]]
        co2_tons = row[col["STCO2AN"]]
        gen_mwh = row[col["STNGENAN"]]
        if not state or not gen_mwh:
            continue
        out[state] = (co2_tons or 0) * SHORT_TON_TO_KG / gen_mwh
    return out


def extract(*, limit: int | None = None) -> str:
    state_intensity = _load_state_intensity()
    url = _cached_workbook_url()
    companies = universe()
    if limit:
        companies = companies[:limit]

    with ObservationWriter(SOURCE) as w:
        for row in companies:
            ticker = row["ticker"]
            hq_state = _hq_state(row.get("headquarters", "")) or ""
            abbr = _STATE_ABBR.get(hq_state)
            intensity = state_intensity.get(abbr) if abbr else None

            if intensity is None:
                w.write(Observation(
                    ticker=ticker, field="grid_intensity_kgco2e_per_mwh",
                    value=None, unit=None, fiscal_year=2023, period_end=None,
                    quote=None, source=SOURCE, source_url=url,
                    source_section="ST23",
                    extracted_by="rule:egrid_state_lookup",
                    status=Status.NOT_DISCLOSED,
                ))
                continue

            w.write(Observation(
                ticker=ticker, field="grid_intensity_kgco2e_per_mwh",
                value=round(intensity, 4), unit="kgco2e_per_mwh", fiscal_year=2023,
                period_end=None, quote=None, source=SOURCE, source_url=url,
                source_section="ST23",
                extracted_by="rule:egrid_state_lookup",
                status=Status.STRUCTURAL,
            ))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S19 extract")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print(extract(limit=a.limit))


if __name__ == "__main__":
    main()
