"""Fields S09 is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "S09"

EMITS = [
    "sbti_target_validated",
    "sbti_target_type",
    "target_year",
    "target_baseline_year",
    "target_reduction_pct",
    "target_scope_coverage",
]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{_f} is not in common/fields.py -- add it there first"

SPECS = {f.name: f for f in fields_for_source(SOURCE)}
