# S15 — EPA GHGRP / FLIGHT

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** US EPA  **Tier** 3 - Narrow  **Priority** MUST  **Effort** Med
**Pillar** P1  **Expected coverage** 69 / 500

## What it is
Mandatory facility-level GHG reporting for US emitters over 25k tCO2e.

## What you get from it
Measured Scope 1 by facility and gas, 2010-present, plus 'Reported Parent Companies' with ownership %.

## Feeds
Carbon intensity (measured); say-do gap vs. self-reported; trajectory

## Access
| | |
|---|---|
| Method | Bulk download + Envirofacts API |
| Endpoint | https://www.epa.gov/ghgreporting/data-sets  \|  https://data.epa.gov/efservice/ |
| Auth | None required |
| Format | XLSB / CSV / JSON |
| Packages | pandas, pyxlsb, requests |

## Gotchas (from the register)
Parent file is XLSB — needs pyxlsb, install hour 1. Only ~69 constituents match directly, BUT they carry ~82% of the index's reported Scope 1. Deep, not broad. 2010+ history makes it your only real trajectory source. FACILITY DIVESTITURES LOOK IDENTICAL TO EMISSIONS CUTS — flag companies whose facility count moves YoY.

## Notes from the planning session
The 'Reported Parent Companies' file is XLSB -- needs `pyxlsb`.
Matches ~69 constituents but those carry ~82% of index Scope 1:
deep, not broad. Emit ghg_facility_count every year -- a divestiture
looks identical to an emissions cut, and companies whose facility
count moves YoY must be excluded from trajectory scoring.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `scope1_tco2e` | tco2e | float | Scope 1. EPA-measured (S15) and self-reported (S10) coexist by design -- the gap between them is the say-do signal. |
| `ghg_facility_count` | count | int | Reporting facilities in GHGRP. Track YoY: a divestiture looks identical to an emissions cut. Movement excludes the company from trajectory scoring. |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s15_epa_ghgrp.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 69/500 expectation above, or you can say why not
