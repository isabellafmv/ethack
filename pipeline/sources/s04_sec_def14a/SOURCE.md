# S04 — SEC EDGAR — DEF 14A proxy statements

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** SEC  **Tier** 1 - Universal  **Priority** MUST  **Effort** Med
**Pillar** P3  **Expected coverage** 498 / 500

## What it is
Annual proxy. Governance and compensation disclosure.

## What you get from it
Board independence, committee structure, climate-oversight committee, ESG-linked pay, PSU/clawback terms, say-on-pay.

## Feeds
Climate governance booleans; comp alignment; board independence

## Access
| | |
|---|---|
| Method | Bulk download + parse |
| Endpoint | Same as S02, form type DEF 14A |
| Auth | None (UA required) |
| Format | HTML |
| Packages | sec-edgar-downloader, edgartools |

## Gotchas (from the register)
Prose-heavy and inconsistently structured. Extract BOOLEANS with verbatim quotes, not graded scores — graded scores over prose is where hallucination lives. This is your only near-complete pillar, so it deserves the best extraction.

## Notes from the planning session
Extract BOOLEANS with verbatim quotes, never graded scores. Graded
scores over prose is where hallucination lives. This is the only
near-complete pillar, so it deserves the best extraction.
NEGATION TRAP: 'we do not maintain a clawback policy' contains the
keyword and means the opposite. Use quotes.looks_negated() as a flag.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `has_climate_oversight_committee` | — | bool | Named board committee with explicit climate oversight |
| `comp_tied_to_emissions_target` | — | bool | Executive comp linked to an emissions metric |
| `has_third_party_assurance` | — | bool | Emissions externally assured |
| `assurance_level` | — | str | limited | reasonable | none |
| `emissions_boundary_stated` | — | bool | Reporting boundary explicitly stated (operational/equity control) |
| `has_clawback_policy` | — | bool | Clawback provision. WATCH NEGATION: 'we do not maintain a clawback policy' contains the keyword and means the opposite. |
| `has_psu_plan` | — | bool | Performance share units in the LTI plan |
| `performance_period_years` | years | float | LTI performance period |
| `independent_director_count` | count | int | Independent directors |
| `board_size` | count | int | Total directors |
| `lead_independent_director` | — | bool | Lead independent director present |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s04_sec_def14a.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 498/500 expectation above, or you can say why not
