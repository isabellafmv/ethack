"""Facility emissions -> listed parent. HAND-WRITTEN.

This is the entity-resolution step the whole facility-based half of the
framework rests on, and it has three ways to go quietly wrong:

  1. **Ownership.** A facility owned 50/50 by two parents must contribute half
     its emissions to each, not all of it to both. Double-counting here inflates
     exactly the companies the framework is meant to scrutinise.
  2. **Name alone.** 'Delta' is an airline, a faucet manufacturer and a dental
     plan. Matching is constrained by state; an unconstrained match is recorded
     as imputed, never as measured.
  3. **Divestitures.** A facility sold looks identical to a facility cleaned up.
     `ghg_facility_count` is emitted per year so a moving count can be detected
     and those companies excluded from trajectory scoring.

And the one that matters most for interpretation: **absence from GHGRP is not
zero emissions.** GHGRP covers US facilities above 25k tCO2e. A company with no
facilities may be a bank, or may emit abroad. Those companies get
`not_disclosed`, never 0.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FacilityRow:
    facility_id: str
    year: int
    parent_name: str
    ownership_pct: float      # 0-100; 100 when the file does not say
    emissions_tco2e: float
    state: str | None = None


@dataclass(slots=True)
class ParentYear:
    scope1_tco2e: float = 0.0
    facilities: set = None
    partial: bool = False     # any facility counted at <100% ownership

    def __post_init__(self):
        if self.facilities is None:
            self.facilities = set()


def rollup(rows: list[FacilityRow]) -> dict[tuple[str, int], ParentYear]:
    """{(normalised parent name, year): ParentYear}, ownership-weighted."""
    out: dict[tuple[str, int], ParentYear] = defaultdict(ParentYear)
    for r in rows:
        if r.emissions_tco2e is None or r.year is None:
            continue
        pct = 100.0 if r.ownership_pct is None else float(r.ownership_pct)
        pct = min(max(pct, 0.0), 100.0)
        key = (r.parent_name, int(r.year))
        acc = out[key]
        acc.scope1_tco2e += float(r.emissions_tco2e) * pct / 100.0
        acc.facilities.add(r.facility_id)
        if pct < 100.0:
            acc.partial = True
    return dict(out)


def facility_count_moved(per_year: dict[int, int]) -> bool:
    """True if the reporting facility count changed across the years present.

    A company whose footprint moved cannot have its emissions trend read as an
    abatement trend — the two are indistinguishable from the outside.
    """
    counts = [per_year[y] for y in sorted(per_year)]
    return len(set(counts)) > 1
