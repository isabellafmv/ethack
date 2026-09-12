"""Fields S10 is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "S10"

EMITS = [
    "scope1_tco2e",
    "scope2_location_tco2e",
    "scope2_market_tco2e",
    "scope3_tco2e",
    "renewable_electricity_mwh",
    "total_electricity_mwh",
    "water_withdrawal_m3",
    "waste_total_tonnes",
    "waste_diverted_pct",
    "target_year",
    "target_baseline_year",
    "target_reduction_pct",
    "target_scope_coverage",
    "has_climate_oversight_committee",
    "comp_tied_to_emissions_target",
    "has_third_party_assurance",
    "assurance_level",
    "emissions_boundary_stated",
]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{_f} is not in common/fields.py -- add it there first"

SPECS = {f.name: f for f in fields_for_source(SOURCE)}
