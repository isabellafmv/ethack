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

## Notes from implementation
`filter[entity.legalName]` is NOT an exact-match filter despite its name --
confirmed live: it returns hundreds of loosely related candidates (foreign
subsidiaries, pension trusts, look-alike names), often NOT led by the real
match. A generous page size (200) plus exact matching on
`entities.normalise_name()` client-side, in extract.py, is what actually
selects the right record.

Two confirmed failure modes, both resolved as `not_disclosed` rather than a
guess:
  * **No LEI exists under a matchable name.** Chevron Corporation does not
    turn up under any name/fulltext search tried (verified directly against
    the API) -- plausibly it has genuinely never self-registered one under
    its own top-level name. GLEIF coverage is not free of gaps just because
    the company is large.
  * **A company collides with its own named financing/holding subsidiary.**
    JPMorgan Chase normalises identically to both "JPMORGAN CHASE & CO."
    (the real parent) and "JPMORGAN CHASE HOLDINGS LLC" (an internal
    entity) once `normalise_name()` strips "holdings"/"llc"/"co". Same
    country, so the tie-break can't help either. A wrong LEI would poison
    any later join on it, so this is written not_disclosed rather than
    picked by a coin flip or a "shortest name wins" heuristic -- both
    considered and rejected as unreliable in general.

`ultimate_parent_lei` will legitimately be empty for the large majority of
S&P 500 constituents: they ARE the top of their own corporate structure, so
"no ultimate parent recorded" is the expected, correct answer, not a gap.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `legal_name` | — | str | Registrant legal name as filed |
| `lei` | — | str | Legal Entity Identifier |
| `ultimate_parent_lei` | — | str | GLEIF Level 2 ultimate parent |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [x] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [x] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring — N/A, nothing here is prose-derived
- [x] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified` — used for a confirmed exact-normalised-name match; ambiguous or absent matches are `not_disclosed` instead (see notes above)
- [x] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [x] `python -m pipeline.sources.s06_gleif.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not — see run results; expect noticeably under 500/500 given the two failure modes above are common, not edge cases
