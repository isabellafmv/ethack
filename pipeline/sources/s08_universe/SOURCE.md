# S08 — S&P 500 constituent list

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** Wikipedia / datahub  **Tier** 1 - Universal  **Priority** MUST  **Effort** Low
**Pillar** X  **Expected coverage** 500 / 500

## What it is
The index membership itself, with tickers, CIK and GICS sector.

## What you get from it
Ticker, company name, CIK (the join key to everything SEC), GICS sector and sub-industry.

## Feeds
Universe definition; sector normalisation buckets

## Access
| | |
|---|---|
| Method | HTML table scrape |
| Endpoint | https://en.wikipedia.org/wiki/List_of_S%26P_500_companies |
| Auth | None required |
| Format | HTML table |
| Packages | pandas.read_html |

## Gotchas (from the register)
Includes CIK directly, which saves a lookup step. Freeze the list at one date and commit it to the repo — membership changes mid-build will silently break joins. Note ~503 tickers for 500 companies (dual share classes).

## Notes from the planning session
FREEZE the list at one date and commit it. Membership changes mid-build
silently break every join. ~503 tickers for 500 companies (dual class).
Already implemented at repo root as S&P_scrape.py -- port it here.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `cik` | — | str | SEC Central Index Key, zero-padded to 10 |
| `legal_name` | — | str | Registrant legal name as filed |
| `gics_sector` | — | str | One of 11 GICS sectors; the normalisation bucket |
| `gics_sub_industry` | — | str | GICS sub-industry |
| `hq_state` | — | str | HQ state, used to constrain entity matching |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s08_universe.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not
