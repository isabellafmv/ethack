"""S08 — the frozen constituent list to Observation records. NO NETWORK.

Everything here is `structural`: a CSV column is a machine-readable fact with no
sentence to quote. All five fields are timeless (fiscal_year=0) -- they describe
the entity, not a period.
"""

from __future__ import annotations

import argparse
import csv
import re

from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.paths import UNIVERSE_PATH
from ...common.schema import Observation, Status, TIMELESS
from ...common.sec_client import pad_cik

from .fields import EMITS
from .pull import ENDPOINT

SOURCE = "S08"


def _state(hq: str) -> str | None:
    """'North Chicago, Illinois' -> 'Illinois'. Used to CONSTRAIN entity
    matching later -- matching on name alone is how 'Delta' becomes an airline,
    a faucet manufacturer and a dental plan at once."""
    if not hq or "," not in hq:
        return hq.strip() or None
    return re.sub(r"\s*\[.*\]$", "", hq.rsplit(",", 1)[-1]).strip() or None


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None) -> str:
    rows = list(csv.DictReader(UNIVERSE_PATH.open(encoding="utf-8")))
    wanted = set(ticker_list or tickers(limit))

    def rec(t, field, value, section):
        return Observation(
            ticker=t, field=field, value=value, unit=None, fiscal_year=TIMELESS,
            period_end=None, quote=None, source=SOURCE, source_url=ENDPOINT,
            source_section=section, extracted_by="rule:frozen_universe_csv",
            status=Status.STRUCTURAL,
        )

    with ObservationWriter(SOURCE) as w:
        for r in rows:
            t = r["ticker"]
            if t not in wanted:
                continue
            w.write(rec(t, "cik", pad_cik(r["cik"]), "CIK"))
            w.write(rec(t, "legal_name", r["company"].strip(), "Security"))
            w.write(rec(t, "gics_sector", r["sector"].strip(), "GICS Sector"))
            w.write(rec(t, "gics_sub_industry", r["sub_industry"].strip(), "GICS Sub-Industry"))
            st = _state(r.get("headquarters", ""))
            # A blank HQ is not_disclosed, not a skipped row. Silence is data.
            w.write(rec(t, "hq_state", st, "Headquarters Location") if st else
                    Observation(ticker=t, field="hq_state", value=None, unit=None,
                                fiscal_year=TIMELESS, period_end=None, quote=None,
                                source=SOURCE, source_url=ENDPOINT,
                                source_section="Headquarters Location",
                                extracted_by="rule:frozen_universe_csv",
                                status=Status.NOT_DISCLOSED))
        return w.summary()


def main() -> None:
    ap = argparse.ArgumentParser(description="S08 extract")
    ap.add_argument("--tickers")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None, limit=a.limit))


if __name__ == "__main__":
    main()
