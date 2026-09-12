"""Why is this field empty? Show the tags these companies actually use.

The fix for a coverage gap is never to guess a tag — it is to look at what the
filers wrote. This reads the cached companyfacts (no network) and reports, for
every company missing a field, the annual us-gaap tags whose name matches a
pattern, ranked by how many companies use each.

    python -m pipeline.sources.s01_sec_xbrl.diagnose revenue_usd
    python -m pipeline.sources.s01_sec_xbrl.diagnose cogs_usd --pattern "cost"
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict

from ...common import cache
from ...common.entities import ticker_to_cik
from ...common.paths import DB_PATH

from .tags import TAG_CHAINS

DEFAULT_PATTERNS = {
    "revenue_usd": r"revenue|sales",
    "cogs_usd": r"cost.*(good|sales|revenue)|costofrevenue",
    "ebit_usd": r"operatingincome|incomeloss.*operat",
    "rnd_expense_usd": r"researchand",
    "capex_usd": r"paymentstoacquire.*(propert|productive|capital)",
    "buybacks_usd": r"repurchase",
    "dividends_paid_usd": r"dividend",
    "energy_cost_usd": r"fuel|utilit|energy|power",
    "shares_outstanding": r"sharesoutstanding",
}


def missing_tickers(field: str) -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM observations WHERE source='S01' AND field=? "
        "AND ticker NOT IN (SELECT ticker FROM observations WHERE source='S01' "
        "AND field=? AND status='structural')", (field, field)).fetchall()
    conn.close()
    return sorted(r[0] for r in rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="diagnose an S01 coverage gap")
    ap.add_argument("field")
    ap.add_argument("--pattern", help="regex over tag names; default per field")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()

    pat = re.compile(a.pattern or DEFAULT_PATTERNS.get(a.field, a.field.split("_")[0]), re.I)
    in_chain = set(TAG_CHAINS.get(a.field, []))
    cik_of = ticker_to_cik()
    missing = missing_tickers(a.field)
    print(f"{len(missing)} companies missing {a.field}: "
          f"{', '.join(missing[:20])}{'...' if len(missing) > 20 else ''}\n")

    users: Counter = Counter()
    examples: dict[str, list] = defaultdict(list)
    for t in missing:
        raw = cache.get_raw("SEC", f"facts-{cik_of.get(t)}", ".json")
        if raw is None:
            continue
        gaap = json.loads(raw).get("facts", {}).get("us-gaap", {})
        for tag, node in gaap.items():
            if not pat.search(tag):
                continue
            ann = [e for u in node.get("units", {}).values() for e in u
                   if e.get("form") in ("10-K", "10-K/A") and e.get("start")
                   and e["end"] >= "2023-01-01"]
            if ann:
                users[tag] += 1
                if len(examples[tag]) < 3:
                    latest = max(ann, key=lambda e: e["end"])
                    examples[tag].append(f"{t}={latest['val'] / 1e9:.2f}bn")

    if not users:
        print("No matching annual tags since 2023. These companies may genuinely "
              "not report this concept, or the pattern is too narrow.")
        return

    print(f"{'tag':<56} {'cos':>4}  in chain?  examples")
    print("-" * 104)
    for tag, n in users.most_common(a.top):
        mark = "yes" if tag in in_chain else " NO"
        print(f"{tag:<56} {n:>4}  {mark:^9}  {', '.join(examples[tag])}")
    print("\nAdd the winners to TAG_CHAINS in tags.py, then re-run extract "
          "(no network needed) and load.")


if __name__ == "__main__":
    main()
