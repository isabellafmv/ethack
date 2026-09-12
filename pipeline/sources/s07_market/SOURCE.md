# S07 — Market data (prices, market cap)

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** Yahoo / other  **Tier** 1 - Universal  **Priority** MUST  **Effort** Low
**Pillar** X  **Expected coverage** 500 / 500

## What it is
Price and share-count feed for the constituent list.

## What you get from it
Market cap (bubble size on the 3D map), sector/industry labels, price history for the portfolio work.

## Feeds
Visual encoding; bonus-question portfolio construction

## Access
| | |
|---|---|
| Method | Python library |
| Endpoint | https://pypi.org/project/yfinance/ |
| Auth | None required |
| Format | DataFrame |
| Packages | yfinance |

## Gotchas (from the register)
Unofficial and rate-limited; it breaks periodically. Cache to disk on first pull. The sustainability/ESG field is thin and vendor-sourced — fine as a fallback controversy flag, NOT as a primary indicator.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `market_cap_usd` | usd | float | Market cap; bubble size on the 3D map |
| `shares_outstanding` | count | float | Shares outstanding |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s07_market.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 500/500 expectation above, or you can say why not
