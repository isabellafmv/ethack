# S19 — EPA eGRID

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** US EPA  **Tier** 3 - Narrow  **Priority** SHOULD  **Effort** Low
**Pillar** P1  **Expected coverage** 150 / 500

## What it is
Regional grid average emission factors for US electricity.

## What you get from it
kg CO2e per MWh by eGRID subregion, plus regional generation fuel mix.

## Feeds
Location-based Scope 2; renewable-claim check

## Access
| | |
|---|---|
| Method | Direct download |
| Endpoint | https://www.epa.gov/egrid/download-data |
| Auth | None required |
| Format | XLSX |
| Packages | pandas |

## Gotchas (from the register)
A factor table, not a company dataset — coverage means 'companies with US facility locations you can join it to'. Its real value: location-based Scope 2 is independent of company claims, so it catches renewable claims that are unbundled REC purchases rather than a change in what the grid actually burns.

## Notes from the planning session
Feeds location-based Scope 2 via the subregion intensity of a company's
facility footprint. Depends on entity resolution (S05/S15) being done
first -- without a facility list there is nothing to weight.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `scope2_location_tco2e` | tco2e | float | Scope 2, location-based |
| `grid_intensity_kgco2e_per_mwh` | kgco2e_per_mwh | float | eGRID subregion intensity for the company's facility footprint |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s19_epa_egrid.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 150/500 expectation above, or you can say why not
