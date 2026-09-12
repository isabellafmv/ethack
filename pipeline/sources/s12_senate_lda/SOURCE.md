# S12 — Senate LDA lobbying disclosures

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** US Senate  **Tier** 2 - Broad  **Priority** STRETCH  **Effort** Med
**Pillar** P2  **Expected coverage** 350 / 500

## What it is
Mandatory quarterly lobbying registration and spend reports.

## What you get from it
Registrant, client, spend, and specific issues/bills lobbied on. Climate-relevant filings are extractable.

## Feeds
Say-do gap: pledges vs. political spending

## Access
| | |
|---|---|
| Method | REST API + bulk XML |
| Endpoint | https://lda.senate.gov/api/ |
| Auth | Free API key |
| Format | JSON / XML |
| Packages | requests, pandas |

## Gotchas (from the register)
This is the purest say-do signal available for free: net-zero pledge next to membership in a trade group litigating against emissions rules. Attribution to parent is messy (firms lobby via associations). High payoff, medium reliability — treat as a flag, not a score.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `lobbying_spend_usd` | usd | float | Senate LDA reported spend |
| `lobbying_climate_flag` | — | bool | Lobbied on a climate-relevant issue code. A flag, not a score -- attribution via trade associations is messy. |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s12_senate_lda.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 350/500 expectation above, or you can say why not
