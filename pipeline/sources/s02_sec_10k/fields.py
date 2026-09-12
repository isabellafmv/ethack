"""Fields S02 is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "S02"

EMITS = [
    "energy_cost_usd",
    "clean_capex_usd",
    "green_revenue_share_pct",
    "target_year",
    "risk_hitword_density",
    "risk_first_factor_topic",
]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{_f} is not in common/fields.py -- add it there first"

SPECS = {f.name: f for f in fields_for_source(SOURCE)}
