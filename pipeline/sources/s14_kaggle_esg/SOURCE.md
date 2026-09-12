# S14 — Kaggle S&P 500 ESG Risk Ratings

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** Kaggle (Sustainalytics-derived)  **Tier** 2 - Broad  **Priority** VALIDATION  **Effort** Low
**Pillar** X  **Expected coverage** 450 / 500

## What it is
Pre-scraped commercial ESG ratings for the index.

## What you get from it
Total ESG risk score, E/S/G component scores, controversy level, by ticker.

## Feeds
VALIDATION ONLY — rank correlation against your own score

## Access
| | |
|---|---|
| Method | Kaggle download |
| Endpoint | https://www.kaggle.com/datasets (search 'S&P 500 ESG Risk Ratings') |
| Auth | Free Kaggle account |
| Format | CSV |
| Packages | kagglehub, pandas |

## Gotchas (from the register)
NEVER use as an input — it is the thing you are trying to beat. Use it for the validation slide: expect modest rank correlation and investigate the disagreements. The three biggest disagreements, each explained, is a better demo than any chart.

## Notes from the planning session
VALIDATION ONLY. Never an input to any pillar score -- it is the thing
we are trying to beat. Expect modest rank correlation and investigate
the disagreements; three explained disagreements beat any chart.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `esg_risk_score_external` | index | float | Sustainalytics-derived risk score. VALIDATION ONLY: this is the thing we are trying to beat. Must never enter a pillar score. |
| `esg_controversy_level_external` | — | str | External controversy band. VALIDATION ONLY. |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [ ] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [ ] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified`
- [ ] Companies that disclosed nothing are written as `not_disclosed` — never skipped
- [ ] `python -m pipeline.sources.s14_kaggle_esg.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 450/500 expectation above, or you can say why not
