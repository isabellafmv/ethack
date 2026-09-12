# S09 — SBTi target list

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** Science Based Targets initiative  **Tier** 2 - Broad  **Priority** MUST  **Effort** Low
**Pillar** P2  **Expected coverage** 275 / 500

## What it is
Public register of validated emission-reduction targets.

## What you get from it
Target type (near-term / net-zero), target year, baseline year, ambition, validation date, sector.

## Feeds
Regulatory momentum; affordability numerator; target credibility

## Access
| | |
|---|---|
| Method | CSV download |
| Endpoint | https://sciencebasedtargets.org/companies-taking-action |
| Auth | None required |
| Format | CSV / XLSX |
| Packages | pandas |

## Gotchas (from the register)
Name matching to tickers is the only real work — match on normalised legal name within country. Gives you the target YEAR and AMBITION, which are the two inputs to the affordability calculation. Companies with no SBTi target still need a counterfactual target, not a null.

## Notes from the planning session
Name matching to tickers is the only real work: match on normalised
legal name WITHIN COUNTRY. Companies with no SBTi target still need a
counterfactual (sector median commitment) written with status=imputed --
never a null, because nulls reward silence.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `sbti_target_validated` | — | bool | Has an SBTi-validated target |
| `sbti_target_type` | — | str | near-term | net-zero | commitment |
| `target_year` | year | int | Stated target year |
| `target_baseline_year` | year | int | Baseline year for the target |
| `target_reduction_pct` | pct | float | Stated reduction vs baseline |
| `target_scope_coverage` | — | str | Which scopes the target covers |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s09_sbti.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 275/500 expectation above, or you can say why not
