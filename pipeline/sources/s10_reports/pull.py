"""S10 — corporate sustainability reports, via the responsibilityreports.com
aggregator.

The register is right that the hard part is finding 500 URLs, not reading them.
This does it in two phases, on purpose:

  --discover   fetch the index (one page, 4,400 companies) and each candidate's
               company page; record ticker -> PDF URL. Small pages, no PDFs.
  (default)    download the PDFs for whatever discovery found.

Discovery first because the PDFs are 60-150 pages each and 500 of them is
several GB. Knowing the match rate before spending that is worth one extra step.

MATCHING: a name match only PROPOSES a candidate. The aggregator embeds the
ticker in every PDF path (/HostedData/.../NYSE_MMM_2024.pdf), so the ticker in
the URL is what CONFIRMS it. A proposed match whose URL ticker disagrees is
discarded — name-only matching is how 'Delta' becomes three different companies.
"""

from __future__ import annotations

import argparse
import json
import re

from ...common import cache
from ...common.entities import normalise_name, tickers, universe
from ...common.http import PoliteSession
from ...common.paths import DATA

SOURCE = "S10"
BASE = "https://www.responsibilityreports.com"
INDEX = f"{BASE}/Companies"
MAP_PATH = DATA / "s10_report_urls.json"
UA = "ETH Hackathon sustainability research (academic, non-commercial)"

_SLUG = re.compile(r'href="(/Company/[^"]+)"[^>]*>([^<]{2,90})<', re.I)
_PDF = re.compile(r'href="(/HostedData/[^"]+?_(?P<tk>[A-Z.]{1,6})_(?P<yr>\d{4})\.pdf)"', re.I)


#: The aggregator tolerates a short burst then throttles: a 2 req/s run got
#: 9 pages and 388 refusals. One request every two seconds is slow (~13 min for
#: 400 pages) and finishes, which beats fast and blocked.
RATE = 0.5


def _session():
    return PoliteSession(SOURCE, UA, per_second=RATE, max_retries=4,
                         browser_headers=True)


def discover(ticker_list: list[str] | None = None, *, limit: int | None = None,
             verbose: bool = True) -> dict:
    sess = _session()
    wanted = set(ticker_list or tickers(limit))
    by_name = {normalise_name(r["company"]): r["ticker"] for r in universe()}

    html = sess.get_text(INDEX, key="index", suffix=".html")
    slugs = _SLUG.findall(html)
    if verbose:
        print(f"[S10] index lists {len(slugs)} companies")

    # Propose candidates by name; the ticker in the PDF URL confirms or rejects.
    candidates: dict[str, str] = {}
    for href, label in slugs:
        t = by_name.get(normalise_name(label))
        if t and t in wanted and t not in candidates:
            candidates[t] = href
    if verbose:
        print(f"[S10] {len(candidates)} name candidates among {len(wanted)} constituents")

    found: dict[str, dict] = {}
    rejected = []
    consecutive = 0
    for i, (t, href) in enumerate(sorted(candidates.items()), 1):
        try:
            page = sess.get_text(BASE + href, key=f"page-{t}", suffix=".html")
            consecutive = 0
        except Exception as e:                      # noqa: BLE001
            rejected.append((t, str(e)[:110]))
            consecutive += 1
            # Ten refusals in a row means we are blocked, not unlucky. Stopping
            # keeps the run resumable (cached pages are kept) and surfaces the
            # cause instead of burying it under 380 identical failures.
            if consecutive >= 10:
                print(f"\n[S10] STOPPING: {consecutive} consecutive failures — "
                      f"we are being throttled, not unlucky.\n"
                      f"      last error: {str(e)[:140]}\n"
                      f"      {len(found)} confirmed so far; pages already "
                      f"fetched are cached, so re-running resumes from here.")
                break
            continue
        hits = [m.groupdict() | {"url": m.group(1)} for m in _PDF.finditer(page)]
        ours = [h for h in hits if h["tk"].upper().replace(".", "-") ==
                t.upper().replace(".", "-")]
        if not ours:
            rejected.append((t, f"ticker mismatch (urls say "
                                f"{sorted({h['tk'] for h in hits})[:3]})"))
            continue
        latest = max(ours, key=lambda h: int(h["yr"]))
        found[t] = {"url": BASE + latest["url"], "year": int(latest["yr"]),
                    "page": BASE + href}
        if verbose and i % 25 == 0:
            print(f"  {i}/{len(candidates)}  confirmed={len(found)} "
                  f"rejected={len(rejected)}")

    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(found, indent=1, sort_keys=True))
    if verbose:
        print(f"[S10] confirmed {len(found)} report URLs -> {MAP_PATH}")
        print(f"      {len(rejected)} candidates rejected by the ticker check")
        for t, why in rejected[:6]:
            print(f"        {t}: {why}")
        yrs = {}
        for v in found.values():
            yrs[v["year"]] = yrs.get(v["year"], 0) + 1
        print(f"      report years: {dict(sorted(yrs.items(), reverse=True))}")
    return found


def pull(ticker_list: list[str] | None = None, *, limit: int | None = None,
         verbose: bool = True, priority_ghgrp: bool = True) -> dict:
    """Download the PDFs discovery found. Large: budget ~10-20 MB each."""
    if not MAP_PATH.exists():
        raise FileNotFoundError(
            f"{MAP_PATH} missing. Run discovery first:\n"
            f"  python -m pipeline.sources.s10_reports.pull --discover")
    urls = json.loads(MAP_PATH.read_text())
    want = set(ticker_list) if ticker_list else set(urls)
    order = sorted(want & set(urls))

    if priority_ghgrp:
        # Download the GHGRP-matched companies FIRST. The say-do gap needs both
        # a measured and a self-reported figure for the same company, so those
        # are worth more per megabyte than anything else in the list.
        import sqlite3
        from ...common.paths import DB_PATH
        try:
            conn = sqlite3.connect(DB_PATH)
            measured = {r[0] for r in conn.execute(
                "SELECT DISTINCT ticker FROM observations WHERE field='scope1_tco2e' "
                "AND status='structural'")}
            conn.close()
            order.sort(key=lambda t: (t not in measured, t))
        except sqlite3.Error:
            pass

    if limit:
        order = order[:limit]

    sess = _session()
    stats = {"requested": len(order), "cached": 0, "fetched": 0, "bytes": 0, "failed": {}}
    for i, t in enumerate(order, 1):
        if cache.has_raw(SOURCE, f"report-{t}", ".pdf"):
            stats["cached"] += 1
            continue
        try:
            data = sess.get(urls[t]["url"], key=f"report-{t}", suffix=".pdf")
            stats["fetched"] += 1
            stats["bytes"] += len(data)
        except Exception as e:                      # noqa: BLE001
            stats["failed"][t] = str(e)[:90]
        if verbose and i % 20 == 0:
            print(f"  {i}/{len(order)}  fetched={stats['fetched']} "
                  f"({stats['bytes']/1e6:.0f} MB) failed={len(stats['failed'])}")
    if verbose:
        print(f"[S10] {stats['fetched']} PDFs ({stats['bytes']/1e6:.0f} MB), "
              f"{stats['cached']} cached, {len(stats['failed'])} failed")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="S10 sustainability reports")
    ap.add_argument("--discover", action="store_true",
                    help="find report URLs only; no PDF downloads")
    ap.add_argument("--tickers"); ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    tl = a.tickers.split(",") if a.tickers else None
    if a.discover:
        discover(tl, limit=a.limit)
    else:
        pull(tl, limit=a.limit)


if __name__ == "__main__":
    main()
