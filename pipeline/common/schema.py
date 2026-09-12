"""FROZEN record shape. Do not change without telling everyone on the team.

One Observation = one claim about one company, from one source, for one year.

The rule this file exists to enforce:
    every extracted number carries a verbatim quote, or it is null.

`quote` must be a character-for-character substring of the source text it came
from. If it is not, the record is marked `quote_failed` and its value is
discarded. "Not disclosed" is a signal, not a gap -- never silently drop a
company because it said nothing.

Two statuses exist that the original three-value enum did not have:

  structural  A machine-readable fact (XBRL, a CSV column, a JSON API field).
              There is no sentence to quote. Highest trust, quote is None.
              Without this, the whole SEC XBRL layer would mark itself
              not_disclosed and the confidence score would be meaningless.

  imputed     A modelled or counterfactual value (e.g. the sector-median
              target for a company that has stated none). Never a null,
              because nulls reward silence -- but confidence is penalised.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field as _field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0.0"


class Status(str, Enum):
    QUOTE_VERIFIED = "quote_verified"   # prose claim, quote validated as substring
    STRUCTURAL = "structural"           # machine-readable fact, no quote possible
    NOT_DISCLOSED = "not_disclosed"     # looked, found nothing -- this is a finding
    QUOTE_FAILED = "quote_failed"       # claimed a quote, quote did not validate
    IMPUTED = "imputed"                 # modelled / counterfactual, confidence penalised


#: Statuses whose `value` may be trusted downstream.
TRUSTED = {Status.QUOTE_VERIFIED, Status.STRUCTURAL, Status.IMPUTED}

#: Confidence weight per status, consumed by export_matrix -> point opacity.
CONFIDENCE = {
    Status.STRUCTURAL: 1.00,
    Status.QUOTE_VERIFIED: 0.85,
    Status.IMPUTED: 0.30,
    Status.NOT_DISCLOSED: 0.00,
    Status.QUOTE_FAILED: 0.00,
}

#: Sentinel fiscal year for timeless entity attributes (sector, LEI, CIK).
TIMELESS = 0


class SchemaError(ValueError):
    """Raised at WRITE time, not load time. A bad record never reaches disk."""


@dataclass(slots=True)
class Observation:
    ticker: str            # S&P universe key, from S08. Join key for everything.
    field: str             # must exist in common.fields.FIELDS
    value: Any             # float | int | bool | str | None
    unit: str | None       # canonical unit token; None for bool/str fields
    fiscal_year: int       # year the value describes; 0 = timeless attribute
    period_end: str | None # ISO date; disambiguates non-calendar fiscal years
    quote: str | None      # verbatim substring of the source text
    source: str            # "S01".."S19", or "imputed"
    source_url: str        # where a human can go and check
    source_section: str | None  # "Item 1A", "EX-21", "xbrl:Revenues"
    extracted_by: str      # "xbrl:Revenues" | "agent:claude-opus-5" | "rule:ex21_parser"
    status: Status
    retrieved_at: str = _field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    def to_json(self) -> str:
        d = asdict(self)
        d["status"] = self.status.value
        return json.dumps(d, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict) -> "Observation":
        d = dict(d)
        d["status"] = Status(d["status"])
        d.pop("schema_version", None)
        return cls(**d)

    @property
    def key(self) -> tuple[str, str, str, int]:
        """The primary key. `source` is in it deliberately: it is what lets an
        EPA-measured, a company-reported and a modelled value of the same number
        coexist in one table. That coexistence IS the say-do comparison."""
        return (self.ticker, self.field, self.source, self.fiscal_year)


def validate(obs: Observation, *, source_text: str | None = None) -> Observation:
    """Validate at WRITE time. Returns a (possibly downgraded) Observation.

    Pass `source_text` and the quote is checked against it mechanically. A quote
    that is not a character-for-character substring downgrades the record to
    quote_failed and nulls the value -- it does not raise, because one bad
    extraction must not kill a 500-company run.
    """
    from .fields import FIELDS  # local import: fields.py imports nothing from here

    if not obs.ticker or not isinstance(obs.ticker, str):
        raise SchemaError(f"ticker must be a non-empty string, got {obs.ticker!r}")

    spec = FIELDS.get(obs.field)
    if spec is None:
        raise SchemaError(
            f"unknown field {obs.field!r}. Add it to common/fields.py first -- "
            f"the vocabulary is the contract, do not invent names locally."
        )

    if not isinstance(obs.status, Status):
        raise SchemaError(f"status must be a Status enum, got {obs.status!r}")

    if not isinstance(obs.fiscal_year, int):
        raise SchemaError(f"fiscal_year must be int (0 for timeless), got {obs.fiscal_year!r}")

    if obs.status in (Status.NOT_DISCLOSED, Status.QUOTE_FAILED):
        obs.value = None
        obs.unit = None
        return obs

    if obs.value is None:
        raise SchemaError(
            f"{obs.ticker}/{obs.field}: status={obs.status.value} but value is None. "
            f"A missing value must be recorded as not_disclosed, never as a silent null."
        )

    spec.check(obs)

    if obs.status is Status.QUOTE_VERIFIED:
        if not obs.quote:
            raise SchemaError(
                f"{obs.ticker}/{obs.field}: quote_verified with no quote. "
                f"Use STRUCTURAL for machine-readable facts."
            )
        if source_text is not None and obs.quote not in source_text:
            obs.status = Status.QUOTE_FAILED
            obs.value = None
            obs.unit = None

    if obs.status is Status.STRUCTURAL and obs.quote:
        raise SchemaError(
            f"{obs.ticker}/{obs.field}: structural records carry no quote "
            f"(got {obs.quote[:60]!r}). Did you mean quote_verified?"
        )

    if not obs.source_url:
        raise SchemaError(f"{obs.ticker}/{obs.field}: source_url is required -- "
                          f"every number must be clickable back to its origin.")

    return obs
