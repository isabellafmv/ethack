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
- [x] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [x] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring — N/A, subsidiary_count is a mechanical count, not a prose claim
- [x] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [x] Companies that disclosed nothing are written as `not_disclosed` — never skipped (no CIK, no 10-K, or no EX-21.x exhibit filed)
- [x] `python -m pipeline.sources.s05_sec_ex21.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 490/500 expectation above, or you can say why not — pending full run

## Implementation notes
Locating EX-21 required a fix to the shared `common/sec_client.py`:
`filing_files()`'s index.json URL had an extra `{accession}-` prefix that
404s (fixed — the real path is plain `index.json`), and even fixed,
index.json's per-file "type" is a generic viewer icon (e.g. "text.gif"),
not the exhibit type. Added `filing_documents()`, which parses the filing's
human `-index.html` Seq/Description/Document/Type/Size table instead —
that Type column is where "EX-21.1" actually lives. Filename-guessing
(`ex21*.htm` etc.) was considered and rejected: EDGAR filers name these
files however they like (Apple's is `a10-kexhibit21109272025.htm`).

subsidiary_count tries a table-row count first (the common EX-21 format),
falling back to counting list/paragraph lines for filers who write it as
prose. `extracted_by` records which heuristic fired (`ex21_table_rows` vs
`ex21_list_lines`) so a suspiciously low or high count can be traced back
to "was this actually a table" rather than treated as gospel.
