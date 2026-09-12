"""Fields S01 is allowed to emit. Declared, not invented.

The full spec for each (unit, dtype, pillar, description) lives in
pipeline/common/fields.py. This file is the subset check.
"""

from ...common.fields import FIELDS, fields_for_source

SOURCE = "S01"

EMITS = [
    "shares_outstanding",
    "cogs_usd",
    "energy_cost_usd",
    "revenue_usd",
    "ebit_usd",
    "ebitda_usd",
    "free_cash_flow_usd",
    "capex_usd",
    "rnd_expense_usd",
    "buybacks_usd",
    "dividends_paid_usd",
]

# Fails loudly at import time if someone adds a name that is not in the
# vocabulary, rather than at hour 20 when the join comes back half empty.
for _f in EMITS:
    assert _f in FIELDS, f"{_f} is not in common/fields.py -- add it there first"

SPECS = {f.name: f for f in fields_for_source(SOURCE)}
