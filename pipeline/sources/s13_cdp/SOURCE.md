# S13 — CDP disclosure data

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** CDP  **Tier** 2 - Broad  **Priority** STRETCH  **Effort** Low
**Pillar** P1  **Expected coverage** 400 / 500

## What it is
The dominant voluntary climate-disclosure questionnaire.

## What you get from it
Scope 1/2/3, water, targets, governance responses, CDP letter score.

## Feeds
Scope 3; disclosure completeness

## Access
| | |
|---|---|
| Method | Registration; bulk mostly licensed |
| Endpoint | https://www.cdp.net/en/data |
| Auth | Free registration; full data licensed |
| Format | XLSX / portal |
| Packages | requests |

## Gotchas (from the register)
Response rate among S&P 500 is high, but the useful bulk data is behind licensing — this is why the plan doc cut it. Scores sometimes available free. Do not build a required indicator on it; use S10 (company PDFs) as the free substitute.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `scope3_tco2e` | tco2e | float | Scope 3, as disclosed |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s13_cdp.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 400/500 expectation above, or you can say why not

## ⚠ BLOCKED — not cleanly pullable

Useful bulk data is licence-gated. Free registration exposes some scores. Do NOT build a required indicator on this -- S10 (company sustainability PDFs) is the free substitute.

`pull()` raises `NotImplementedError` on purpose. The folder exists so the
coverage manifest reports *why* this source is empty instead of showing a
silent gap. If you unblock it, delete this section.
