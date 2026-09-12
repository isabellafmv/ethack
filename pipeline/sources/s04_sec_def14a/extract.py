"""S04 — DEF 14A proxies to Observations. NO NETWORK.

Every value here is `quote_verified`: the quote is the sentence the pattern
matched in, so it is a substring of the source by construction — and the writer
still checks it mechanically against the document text, so a bug in the
sentence splitter shows up as quote_failed rather than as a silent pass.

Absence is recorded, and the two kinds of absence are kept apart:

  * The proxy was read and the phrase is not in it -> the boolean is FALSE with
    no quote. Proxies are exhaustive about committee structure and pay design,
    so a missing clawback mention really does mean no clawback policy.
  * No proxy on file, or it would not parse -> not_disclosed. We did not look.
"""

from __future__ import annotations

import argparse

from ...common import cache
from ...common.entities import tickers
from ...common.jsonl import ObservationWriter
from ...common.schema import Observation, Status

from . import parse
from .fields import EMITS

SOURCE = "S04"
BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=DEF+14A"


def extract(ticker_list: list[str] | None = None, *, limit: int | None = None,
            year: int | None = None, verbose: bool = True) -> str:
    from datetime import date
    ticker_list = ticker_list or tickers(limit)
    fy = year or date.today().year - 1
    missing, parsed = [], 0

    import sys as _sys
    import time as _time
    t0 = _time.monotonic()

    with ObservationWriter(SOURCE) as w:
        for i, t in enumerate(ticker_list, 1):
            # Proxies are 3-6 MB each and parsing all 500 takes minutes. Without
            # progress there is no way to tell running from hung, and a silent
            # long job gets killed by whoever is watching it.
            if verbose and (i % 25 == 0 or i == len(ticker_list)):
                el = _time.monotonic() - t0
                rate = i / el if el else 0
                left = (len(ticker_list) - i) / rate if rate else 0
                print(f"  {i}/{len(ticker_list)} proxies  {el:5.0f}s elapsed, "
                      f"~{left:.0f}s left", file=_sys.stderr, flush=True)
            raw = cache.get_raw(SOURCE, f"proxy-{t}", ".html")

            def rec(field, value, unit, quote, status, by, section="DEF 14A"):
                return Observation(
                    ticker=t, field=field, value=value, unit=unit, fiscal_year=fy,
                    period_end=None, quote=quote, source=SOURCE,
                    source_url=BASE_URL, source_section=section,
                    extracted_by=by, status=status)

            if raw is None:
                missing.append(t)
                for f in EMITS:
                    w.write(rec(f, None, None, None, Status.NOT_DISCLOSED,
                                "rule:no_proxy_cached"))
                continue

            text = parse.html_to_text(raw)
            parsed += 1

            for field in parse.BOOLEANS:
                if field not in EMITS or field.startswith("_"):
                    continue
                val, quote, neg = parse.find_boolean(text, field)
                if val is None:
                    if parse.BOOLEANS[field]["absence_is_false"]:
                        # High-recall term of art: any proxy with the concept
                        # states it, so absence is a real False (no quote, so
                        # structural rather than quote_verified).
                        w.write(rec(field, False, None, None, Status.STRUCTURAL,
                                    "rule:phrase_absent_in_proxy"))
                    else:
                        # Low-recall concept detector. Absence means we did not
                        # find it, NOT that it is absent. Asserting False here
                        # would invent a majority.
                        w.write(rec(field, None, None, None, Status.NOT_DISCLOSED,
                                    "rule:concept_not_found_low_recall"))
                else:
                    w.write(rec(field, val, None, quote, Status.QUOTE_VERIFIED,
                                "rule:phrase_negated" if neg else "rule:phrase_match"),
                            source_text=text)

            ind, size, q = parse.find_board(text)
            if ind is not None:
                w.write(rec("independent_director_count", ind, "count", q,
                            Status.QUOTE_VERIFIED, "rule:board_sentence"),
                        source_text=text)
                w.write(rec("board_size", size, "count", q,
                            Status.QUOTE_VERIFIED, "rule:board_sentence"),
                        source_text=text)
            else:
                w.write(rec("independent_director_count", None, None, None,
                            Status.NOT_DISCLOSED, "rule:board_sentence_not_found"))
                w.write(rec("board_size", None, None, None, Status.NOT_DISCLOSED,
                            "rule:board_sentence_not_found"))

            lvl, q = parse.find_assurance_level(text)
            w.write(rec("assurance_level", lvl, None, q, Status.QUOTE_VERIFIED,
                        "rule:assurance_sentence") if lvl else
                    rec("assurance_level", None, None, None, Status.NOT_DISCLOSED,
                        "rule:assurance_not_found"), source_text=text)

            per, q = parse.find_performance_period(text)
            w.write(rec("performance_period_years", per, "years", q,
                        Status.QUOTE_VERIFIED, "rule:performance_period") if per else
                    rec("performance_period_years", None, None, None,
                        Status.NOT_DISCLOSED, "rule:performance_period_not_found"),
                    source_text=text)

        out = w.summary()

    return (f"{out}\n  parsed {parsed} proxies; {len(missing)} had none cached"
            f"{' -> run pull.py' if missing else ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description="S04 extract")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    ap.add_argument("--year", type=int)
    a = ap.parse_args()
    print(extract(a.tickers.split(",") if a.tickers else None,
                  limit=a.limit, year=a.year))


if __name__ == "__main__":
    main()
