# S06 — GLEIF — LEI Level 1 & 2

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** GLEIF  **Tier** 1 - Universal  **Priority** SHOULD  **Effort** Low
**Pillar** X  **Expected coverage** 500 / 500

## What it is
Global legal entity identifier registry with declared parent relationships.

## What you get from it
Legal entity names, addresses, direct parent and ultimate parent LEIs. Machine-readable corporate structure.

## Feeds
Entity resolution (second opinion on Exhibit 21)

## Access
| | |
|---|---|
| Method | REST API + bulk file |
| Endpoint | https://api.gleif.org/api/v1/lei-records |
| Auth | None required |
| Format | JSON / CSV |
| Packages | requests, pandas |

## Gotchas (from the register)
Level 2 parent data is self-declared and companies can claim exemptions, so child-to-parent links are patchier than the entity records themselves. Use ALONGSIDE Exhibit 21, not instead of it.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `legal_name` | — | str | Registrant legal name as filed |
| `lei` | — | str | Legal Entity Identifier |
| `ultimate_parent_lei` | — | str | GLEIF Level 2 ultimate parent |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s06_gleif.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not
