# S02 — SEC EDGAR — 10-K full text

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** SEC  **Tier** 1 - Universal  **Priority** MUST  **Effort** Med
**Pillar** P1/P2  **Expected coverage** 500 / 500

## What it is
The annual report itself. Item 1A risk factors, Item 7 MD&A.

## What you get from it
Risk-factor language, climate/transition discussion, green capex mentions, segment narrative, hitword counts.

## Feeds
Green revenue share; clean capex; structural risk hitwords; emissions targets

## Access
| | |
|---|---|
| Method | Bulk download + parse |
| Endpoint | https://www.sec.gov/cgi-bin/browse-edgar  /  https://data.sec.gov/submissions/CIK##########.json |
| Auth | None (UA required) |
| Format | HTML / iXBRL |
| Packages | sec-edgar-downloader, edgartools, BeautifulSoup |

## Gotchas (from the register)
75k-200k tokens per filing — DO NOT send whole filings to an agent. Strip HTML, locate the section by heading, keep +/-2-3k chars around keyword hits, send 5-15k tokens. ~15x cheaper and more accurate. Cache every filing on first fetch.

## Notes from the planning session
DO NOT send whole filings to an agent (75k-200k tokens). Strip HTML,
locate the section by heading, keep +/-2-3k chars around keyword hits,
send 5-15k tokens. ~15x cheaper and MORE accurate.
For risk_hitword_density: position beats frequency. Every company
mentions litigation; what comes FIRST in Item 1A is what management
fears. Naive counting has no negation handling -- name that limit.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `energy_cost_usd` | usd | float | Energy cost where separately disclosed |
| `clean_capex_usd` | usd | float | Low-carbon portion of capex, from Item 7 MD&A. Expect ~1/3 hit rate -- the low rate is itself a finding, report it. |
| `green_revenue_share_pct` | pct | float | Revenue from low-carbon segments. The classification is OURS, not the company's -- per-segment rationale must be published alongside. |
| `target_year` | year | int | Stated target year |
| `risk_hitword_density` | index | float | Item 1A hitwords weighted by POSITION and proximity to intensifiers. Raw counts measure document length -- ship the text-vs-XBRL discrepancy, not the count. No negation handling: name that limit in the pitch. |
| `risk_first_factor_topic` | — | str | Topic of the FIRST risk factor. What comes first is what management fears. |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s02_sec_10k.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not
