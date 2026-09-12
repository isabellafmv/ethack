# S05 — SEC Exhibit 21 — subsidiary lists

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** SEC  **Tier** 1 - Universal  **Priority** MUST  **Effort** Med
**Pillar** X  **Expected coverage** 490 / 500

## What it is
Company's own declared list of subsidiaries, filed with the 10-K.

## What you get from it
Subsidiary legal names + jurisdiction, per parent. Ground truth for rolling facility data up to the listed entity.

## Feeds
Entity resolution (prerequisite for every facility-based source)

## Access
| | |
|---|---|
| Method | Parse from 10-K exhibits |
| Endpoint | Filed as EX-21 alongside the 10-K (see S02) |
| Auth | None (UA required) |
| Format | HTML / text |
| Packages | sec-edgar-downloader, rapidfuzz |

## Gotchas (from the register)
Companies may omit subsidiaries deemed immaterial, so a short list does NOT mean a simple company. Format is wildly inconsistent (tables, lists, paragraphs). No ownership percentages — get those from S15.

## Notes from the planning session
Companies may omit subsidiaries deemed immaterial -- a short list does
NOT mean a simple company. Format is wildly inconsistent (tables,
lists, paragraphs). No ownership percentages here; those come from S15.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `legal_name` | — | str | Registrant legal name as filed |
| `subsidiary_count` | count | int | Subsidiaries listed in Exhibit 21 |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s05_sec_ex21.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 490/500 expectation above, or you can say why not
