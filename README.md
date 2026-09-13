# ethack — S&P 500 Sustainability Framework

ETH hackathon project: a data-driven framework that scores and ranks S&P 500
companies on sustainability, defined as **long-term business viability under
the energy transition**, not just low emissions. A company cannot fund
decarbonization if it cannot fund itself — so financial health (cash flow,
reinvestment, cost discipline) sits alongside environmental, transition and
governance signals in one composite score, the **Pragmatic Hybrid
Sustainability Index (PHSI)**.

The full philosophy, scoring formula and the $1B net-zero portfolio answer
to the bonus question live in `claude/master-plan.md`. This README documents
the repo: what each piece does and how they fit together.

## How the pieces fit together

```
pipeline/            → fetches & extracts raw data, one source per subfolder
        ↓
data/ (wide_*.csv,   → harmonised, joinable exports; data/matrix.json is the
matrix.json)           payload the web app ships to the browser
        ↓
score_calculation/   → Python scoring oracle: environmental / transition /
                        governance pillar scores + final_score.py combines them
        ↓
web/                 → React + Three.js app. Recomputes percentiles, weights
                        and the composite score client-side, per slider tick,
                        from data/matrix.json (Python owns harmonised values
                        and provenance; the browser owns the scoring math the
                        UI needs to be interactive)
        ↓
presentation/, bonus/, visualize_scores_3d.py → pitch-deck assets
```

`score_calculation/` (Python) and `web/src/scoring/` (TypeScript) implement
the *same* percentile + weighted-average logic independently — see
`web/scripts/verify-scoring-parity.ts`, which checks the two never drift
apart. `score_calculation/score.py` (invoked via `npm run oracle`) is the
reference implementation `web/scripts/verify-oracle.ts` checks the frontend
against.

## Repo layout

| Path | What it is |
|---|---|
| `claude/master-plan.md` | Sustainability definition, PHSI formula, architecture, and the bonus-question portfolio answer |
| `pipeline/` | Ingestion: pulls raw data per source, extracts it into append-only JSONL, loads it into SQLite, exports `data/matrix.json`. Has its own detailed [`pipeline/README.md`](pipeline/README.md) — read that before touching ingestion |
| `score_calculation/` | Python scoring: `environmental/`, `transition/`, `governance/` compute one pillar score each from `data/wide_FY2025_fallback.csv`; `final_score.py` combines the three (equal-weighted, renormalized over whichever pillars a company actually has); `coverage.py` holds the shared renormalized-average / disclosure-penalty math |
| `web/` | The interactive frontend — React + TypeScript + `@react-three/fiber`, a 3D scatter of companies over the three pillars with live-adjustable weights, sector filters, a portfolio allocator, and per-field provenance drill-down |
| `data/` | Everything the pipeline and scoring steps read/write — CSV exports, `matrix.json` (the browser payload), cached raw pulls. Mostly gitignored/regenerable; see `pipeline/README.md`'s table for what to actually commit |
| `S&P_scrape.py` | Standalone scraper: pulls the current S&P 500 constituent list (ticker, sector, sub-industry, CIK, ...) from Wikipedia |
| `visualize_scores_3d.py` | Builds a standalone Plotly 3D HTML scatter (`data/sp500_scores_3d.html`) from the three pillar-score CSVs, for offline viewing outside the web app |
| `presentation/3D_rotation.py` | Renders the bare, labeled 3D axes (no data) as a transparent PNG, for the "introduce the axes" beat of the pitch deck |
| `bonus/fundamentals.html` | Supporting material for the bonus $1B allocation question |
| `sp500_sustainability_data_sources.xlsx` | Data source inventory/notes |
| `FRONTEND_PROMPT.md` | The brief that specified `web/`'s architecture (why scoring happens client-side, the data topology, the status/confidence enum) — useful background if you're changing how `web/` consumes `matrix.json` |

## Data pipeline (`pipeline/`)

Fetches and extracts raw data from ~15 sources (SEC XBRL/10-K/DEF14A/EX-21
filings, GLEIF, market data, SBTi targets, sustainability report PDFs,
violation trackers, Senate lobbying disclosures, CDP, Kaggle ESG ratings, EPA
GHGRP/ECHO/eGRID). Its one hard rule: **every extracted number carries a
verbatim quote, or it is null** — a company that discloses nothing is
recorded as `not_disclosed` (a finding), never silently skipped.

```
network → cache/raw/<source>/        pull.py     (idempotent, re-run is free)
        → data/observations/*.jsonl  extract.py  (no network, append-only)
        → data/scores.db (SQLite)    load.py     (the only writer)
        → data/matrix.json           export_matrix.py
        → browser                    percentiles + weights computed per tick
```

See [`pipeline/README.md`](pipeline/README.md) for the full source layout,
the status/confidence vocabulary (`structural` / `quote_verified` /
`imputed` / `not_disclosed` / `quote_failed`), first-run instructions, and
the concurrency rules that keep multiple people editing sources without
colliding (a source package only imports `common`; only `load.py` writes to
the database; only names in `common/fields.py` may be emitted).

**Note:** pulls need real internet access (SEC EDGAR, EPA, Yahoo Finance,
Wikipedia) and must be run from your own terminal, not from a sandboxed
agent environment — see the "First run" section of `pipeline/README.md`.
Extraction, loading, testing and everything downstream work offline.

## Scoring (`score_calculation/`)

Three pillar scores, each documented in its own module docstring (worth
reading — they're candid about what's real data vs. modelled/proxy data and
why):

- **Environmental** (`environmental/environmental_score.py`) — carbon
  intensity, energy mix, resource/waste and input efficiency, weighted by a
  SASB-inspired per-GICS-sector materiality matrix.
- **Transition** (`transition/transition_score.py`) — carbon-price exposure,
  sector structural exposure, regulatory commitment (SBTi target tier + R&D
  intensity), and transition affordability.
- **Governance** (`governance/governance_score.py`) — capital stewardship
  (reinvestment share from XBRL), climate governance, board structure, and
  controversy/enforcement record.

`final_score.py` combines the three pillars (equal weight, renormalized over
whichever pillars a company has data for) into the single PHSI-style
`final_score`, plus `n_pillars_available` and `data_confidence_pct` so a
company's score is never presented as more certain than the underlying data
supports.

Every score module reads `data/wide_FY2025_fallback.csv` (see
`pipeline/export_wide.py`) independently — re-run the relevant pillar script
after the underlying data changes; nothing recomputes automatically.

## Frontend (`web/`)

React + TypeScript + Vite + `@react-three/fiber`/`drei`, rendering companies
as a 3D scatter over the three pillars. Percentiles, weights and the
composite score are computed **client-side, per slider tick**, from
`data/matrix.json` — not precomputed in Python — because they're exactly
what the interactive controls (sector filter, weight sliders, portfolio
allocator) need to recompute live. See `FRONTEND_PROMPT.md` for the full
rationale and `web/src/scoring/` for the TypeScript implementation
(percentile.ts, weights.ts, materiality.ts, pipeline.ts, registry.ts,
rankSensitivity.ts — each has a matching `.test.ts`).

```bash
cd web
npm install
npm run data              # regenerate data/matrix.json + quotes.json from the DB
npm run dev                # local dev server
npm run build               # production build
npm run test                # vitest
npm run oracle               # run the Python scoring oracle for comparison
npm run verify:oracle         # check frontend scores match the Python oracle
npm run verify:scoring-parity # check TS scoring math matches score_calculation/
```

Key components: `SectorFilter`, `WeightPanel`, `PortfolioAllocator`,
`DetailPanel` (per-company, per-field provenance and quotes),
`CoverageStrip`, `ReferencePicker`, `ProvenanceFooter`.

## Quick start

```bash
# 1. Ingest data (from a terminal with real internet access)
pip install yfinance rapidfuzz pyxlsb --break-system-packages
export SEC_USER_AGENT="ETH Hackathon Team you@example.com"
python -m pipeline.test_pipeline
python -m pipeline.run_structural
python -m pipeline.export_matrix

# 2. Compute pillar + final scores
python -m score_calculation.environmental.environmental_score
python -m score_calculation.transition.transition_score
python -m score_calculation.governance.governance_score
python -m score_calculation.final_score

# 3. Run the frontend
cd web && npm install && npm run dev
```

## Status vocabulary (used throughout pipeline, scoring and the UI)

| status | meaning | confidence |
|---|---|---|
| `structural` | machine-readable fact (XBRL, CSV, JSON API) — no quote possible | 1.00 |
| `quote_verified` | prose claim whose quote validated as an exact substring | 0.85 |
| `imputed` | modelled / counterfactual (e.g. sector-median target) — never null | 0.30 |
| `not_disclosed` | looked, found nothing — a finding, not a gap | 0.00 |
| `quote_failed` | a quote was claimed and did not validate; value discarded | 0.00 |

## Known gaps (stated honestly, not hidden)

- `y02_patent_share_pct` has no in-scope source (PatentsView needs an API key
  not reachable from this environment) — flagged explicitly by
  `test_pipeline.py` rather than silently passing.
- **S11** (Violation Tracker) has no public API; **S13** (CDP) is
  licence-gated. Both fail loudly with `NotImplementedError` so the coverage
  manifest reports *why* rather than showing a silent zero.
- Environmental pillar's `carbon_intensity_score` only scores the ~126
  companies with a real measured `scope1_tco2e` value, ranked within-sector —
  deliberately not extended to modelled-tier companies (see the module
  docstring for why that extension doesn't actually differentiate anything).
- Governance's climate-governance sub-score has low coverage (~45–60/500)
  because it comes from a low-recall proxy-statement extraction rule; this is
  a different kind of null than the pipeline's usual "not_disclosed is a
  real finding" and is reflected in `data_confidence_pct`, not the score
  itself.
