"""Fields S04 is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "S04"

EMITS = [
    "has_climate_oversight_committee",
    "comp_tied_to_emissions_target",
    "has_third_party_assurance",
    "assurance_level",
    "emissions_boundary_stated",
    "has_clawback_policy",
    "has_psu_plan",
    "performance_period_years",
    "independent_director_count",
    "board_size",
    "lead_independent_director",
]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{_f} is not in common/fields.py -- add it there first"

SPECS = {f.name: f for f in fields_for_source(SOURCE)}
