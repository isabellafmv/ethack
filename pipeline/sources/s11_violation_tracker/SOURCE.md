# S11 — Violation Tracker

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** Good Jobs First  **Tier** 2 - Broad  **Priority** SHOULD  **Effort** Med
**Pillar** P3  **Expected coverage** 400 / 500

## What it is
Aggregated US enforcement actions across ~500 federal and state agencies.

## What you get from it
Penalties by company and parent: environmental, safety, labor, consumer, financial. Already mapped to parent company.

## Feeds
Controversy flag (built from records, not news sentiment)

## Access
| | |
|---|---|
| Method | Web UI; bulk on request |
| Endpoint | https://violationtracker.goodjobsfirst.org |
| Auth | Free account for some features |
| Format | HTML / CSV export |
| Packages | requests, BeautifulSoup |

## Gotchas (from the register)
NO public API — this is the friction. Broader than you expect (financial + labor + consumer, not just environmental), so it is your highest-coverage controversy source. Its parent mapping is also a free second opinion on your entity resolution. Check licence terms before redistributing.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `penalty_total_usd` | usd | float | Penalties from COURT AND AGENCY RECORDS, not news sentiment. News-based controversy scores measure media volume, which tracks company size. |
| `penalty_count` | count | int | Number of penalty records |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s11_violation_tracker.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 400/500 expectation above, or you can say why not

## ⚠ BLOCKED — not cleanly pullable

No public API. Web UI only; bulk data on request. Check licence terms before redistributing. Options: manual CSV export into cache/raw/S11/, or fall back to S18 (ECHO) for the environmental subset only.

`pull()` raises `NotImplementedError` on purpose. The folder exists so the
coverage manifest reports *why* this source is empty instead of showing a
silent gap. If you unblock it, delete this section.
