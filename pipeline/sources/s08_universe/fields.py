"""Fields S08 is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "S08"

EMITS = [
    "cik",
    "legal_name",
    "gics_sector",
    "gics_sub_industry",
    "hq_state",
]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{_f} is not in common/fields.py -- add it there first"

SPECS = {f.name: f for f in fields_for_source(SOURCE)}
