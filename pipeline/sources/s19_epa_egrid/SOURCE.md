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

## Scope actually shipped (read before changing either field)
The facility-weighted version above needs a source package to consume S05's
or S15's parsed facility list, and the repo's own rule ("a source package
imports only common") blocks that short of a shared `data/` artifact
neither currently publishes. Rather than block on it:

* `grid_intensity_kgco2e_per_mwh` is the eGRID **state** factor (STC2ERTA,
  the standard location-based total-output rate) for the ticker's
  **headquarters state**, not its facility footprint. Written as `IMPUTED`
  -- a company's plants are not its HQ. Non-US headquarters (Ireland,
  Switzerland, Bermuda, ...) get `not_disclosed`; eGRID only covers the US
  grid.
* `scope2_location_tco2e` is **not emitted**. It needs an electricity
  consumption figure (`total_electricity_mwh`, an S10 field) to multiply
  the rate by, and S10's `extract()` doesn't exist yet. Revisit both fields
  once S05/S15 publish a joinable facility/state list, or S10 lands.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `scope2_location_tco2e` | tco2e | float | Scope 2, location-based |
| `grid_intensity_kgco2e_per_mwh` | kgco2e_per_mwh | float | eGRID subregion intensity for the company's facility footprint |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [x] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [x] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring — N/A
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified` — deliberately `IMPUTED` instead; see "Scope actually shipped" above
- [x] Companies that disclosed nothing are written as `not_disclosed` — never skipped (non-US headquarters)
- [x] `python -m pipeline.sources.s19_epa_egrid.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 150/500 expectation above, or you can say why not — expect close to 500/500 for `grid_intensity_kgco2e_per_mwh` (every US-HQ'd ticker gets one), well above the register's 150 estimate, but at HQ-state resolution rather than the facility-weighted subregion figure originally scoped. `scope2_location_tco2e` is 0/500 on purpose (see above).
