"""Column patterns for the EPA GHGRP files. HAND-WRITTEN.

Two files matter and they can arrive separately or combined:
  * "Reported Parent Companies" (XLSB) — facility, parent name, ownership %
  * facility emissions (FLIGHT / Envirofacts) — facility, year, total reported

`detect` tolerates either layout; `REQUIRED` says what extract cannot proceed
without.
"""

from __future__ import annotations

from ...common.columns import detect as _detect, report  # noqa: F401

COLUMNS = {
    "facility_id": ["ghgrp facility id", "facility id", "ghgrp id", "frs id"],
    "facility_name": ["facility name"],
    "year": ["reporting year", "report year", "year"],
    "parent_name": ["parent company name", "parent companies", "parent company",
                    "parent co name"],
    "ownership": ["parent co percent ownership", "percent ownership",
                  "ownership percentage", "parent company percent ownership",
                  "ownership"],
    "state": ["facility state", "state where facility is located", "state", "st"],
    "emissions": ["total reported direct emissions",
                  "ghg quantity metric tons co2e", "total reported emissions",
                  "ghg quantity", "co2e emissions", "emissions"],
}

REQUIRED = ["facility_id", "year", "parent_name", "emissions"]


def detect(headers):
    return _detect(list(headers), COLUMNS)


def number(value) -> float | None:
    """EPA files carry thousands separators, footnote markers and 'NA'."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if s.lower() in ("", "na", "n/a", "none", "nan", "--", "-", "cbi"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
