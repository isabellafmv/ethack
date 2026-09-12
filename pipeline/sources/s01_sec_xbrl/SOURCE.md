# S01 — SEC EDGAR — XBRL company facts

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** SEC  **Tier** 1 - Universal  **Priority** MUST  **Effort** Low
**Pillar** P1/P2/P3  **Expected coverage** 500 / 500

## What it is
Structured financial-statement data tagged in every filing.

## What you get from it
Revenue, EBIT, EBITDA inputs, FCF components, capex, R&D, buybacks, dividends, total assets.

## Feeds
Carbon intensity denominator; carbon-price exposure; affordability; capital stewardship

## Access
| | |
|---|---|
| Method | REST JSON API |
| Endpoint | https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json |
| Auth | None (UA required) |
| Format | JSON |
| Packages | requests, pandas, edgartools |

## Gotchas (from the register)
User-Agent MUST contain a real contact address or you are blocked. Max 10 req/s. Revenue splits across 4+ tags — write the fallback chain (RevenueFromContractWithCustomerExcludingAssessedTax, Revenues, SalesRevenueNet, RevenueFromContractWithCustomerIncludingAssessedTax).

## Notes from the planning session
Revenue splits across 4+ XBRL tags. The fallback chain lives in
this package's fields.py, as data, not scattered through caller code.
FCF = NetCashProvidedByUsedInOperatingActivities - capex; if either leg
is missing, emit not_disclosed rather than a partial number.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `shares_outstanding` | count | float | Shares outstanding |
| `cogs_usd` | usd | float | Cost of goods sold; input efficiency numerator |
| `energy_cost_usd` | usd | float | Energy cost where separately disclosed |
| `revenue_usd` | usd | float | Revenue. Splits across 4+ XBRL tags -- the fallback chain lives in sources/s01_sec_xbrl/fields.py, not in caller code. |
| `ebit_usd` | usd | float | Operating income |
| `ebitda_usd` | usd | float | EBIT + D&A; carbon-price exposure denominator |
| `free_cash_flow_usd` | usd | float | CFO - capex. The affordability denominator: can they pay for what they promised. |
| `capex_usd` | usd | float | PaymentsToAcquirePropertyPlantAndEquipment |
| `rnd_expense_usd` | usd | float | R&D expense |
| `buybacks_usd` | usd | float | Share repurchases |
| `dividends_paid_usd` | usd | float | Dividends paid |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s01_sec_xbrl.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not
