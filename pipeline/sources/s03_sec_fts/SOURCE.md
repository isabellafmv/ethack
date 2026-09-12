# S03 — SEC EDGAR full-text search

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** SEC  **Tier** 1 - Universal  **Priority** SHOULD  **Effort** Low
**Pillar** P2  **Expected coverage** 500 / 500

## What it is
Keyword search across all filings without downloading them.

## What you get from it
Hit counts and filing locations for any phrase, filterable by form type and date.

## Feeds
Structural risk hitwords; climate language prevalence

## Access
| | |
|---|---|
| Method | Undocumented JSON endpoint |
| Endpoint | https://efts.sec.gov/LATEST/search-index?q=%22phrase%22&forms=10-K  (JSON behind sec.gov/edgar/search) |
| Auth | None (UA required) |
| Format | JSON |
| Packages | requests |

## Gotchas (from the register)
Undocumented — confirm the endpoint shape by opening sec.gov/edgar/search in devtools before relying on it. Only covers 2001+. Gives hit counts, not context: you still need S02 for the surrounding sentence.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `risk_hitword_density` | index | float | Item 1A hitwords weighted by POSITION and proximity to intensifiers. Raw counts measure document length -- ship the text-vs-XBRL discrepancy, not the count. No negation handling: name that limit in the pitch. |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s03_sec_fts.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not
