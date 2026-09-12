# S10 — Corporate sustainability reports

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** Companies / responsibilityreports.com  **Tier** 2 - Broad  **Priority** SHOULD  **Effort** High
**Pillar** P1  **Expected coverage** 400 / 500

## What it is
The self-published PDF. Aggregator indexes them by ticker.

## What you get from it
Scope 1/2/3, renewable %, water, waste, targets, assurance statements. Everything not in the 10-K.

## Feeds
Scope 3; energy mix; water/waste; stated targets

## Access
| | |
|---|---|
| Method | Scrape aggregator, then fetch PDFs |
| Endpoint | https://www.responsibilityreports.com |
| Auth | None required |
| Format | PDF |
| Packages | requests, pdfplumber, PyMuPDF |

## Gotchas (from the register)
The hard part is finding 500 URLs, not reading them — the aggregator solves exactly that. PDFs are 60-150pp; pre-filter to the data-table pages before extraction. Self-reported: treat every number as a CLAIM with a quote attached, never as a fact.

## Notes from the planning session
Self-reported: every number is a CLAIM with a quote attached, never a
fact. PDFs are 60-150pp; pre-filter to the data-table pages first.
A renewable claim that moves market-based Scope 2 but NOT the
location-based figure is an unbundled REC purchase -- flag, don't credit.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `scope1_tco2e` | tco2e | float | Scope 1. EPA-measured (S15) and self-reported (S10) coexist by design -- the gap between them is the say-do signal. |
| `scope2_location_tco2e` | tco2e | float | Scope 2, location-based |
| `scope2_market_tco2e` | tco2e | float | Scope 2, market-based. A renewable claim that moves this but NOT the location-based figure is an unbundled REC purchase -- flag, do not credit. |
| `scope3_tco2e` | tco2e | float | Scope 3, as disclosed |
| `renewable_electricity_mwh` | mwh | float | Renewable electricity procured/generated |
| `total_electricity_mwh` | mwh | float | Total electricity consumed |
| `water_withdrawal_m3` | m3 | float | Total water withdrawn |
| `waste_total_tonnes` | tonnes | float | Total waste generated |
| `waste_diverted_pct` | pct | float | Share of waste diverted from landfill |
| `target_year` | year | int | Stated target year |
| `target_baseline_year` | year | int | Baseline year for the target |
| `target_reduction_pct` | pct | float | Stated reduction vs baseline |
| `target_scope_coverage` | — | str | Which scopes the target covers |
| `has_climate_oversight_committee` | — | bool | Named board committee with explicit climate oversight |
| `comp_tied_to_emissions_target` | — | bool | Executive comp linked to an emissions metric |
| `has_third_party_assurance` | — | bool | Emissions externally assured |
| `assurance_level` | — | str | limited | reasonable | none |
| `emissions_boundary_stated` | — | bool | Reporting boundary explicitly stated (operational/equity control) |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s10_reports.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 400/500 expectation above, or you can say why not
