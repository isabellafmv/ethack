# Claude Code prompt — build the 3D sustainability map (`web/`)

Rev 2. Paste everything below the line into Claude Code, run from the repo root (`ethack/ethack`).

Rev 1 specified a frontend that consumed a precomputed `data/scores.csv`. That contradicted the
architecture already written into `pipeline/` in three separate files. This rev reverses the
scoring boundary. See `## Why the browser scores` below — do not re-litigate it without reading
those comments first.

---

## Context

24h hackathon repo ranking the S&P 500 on three sustainability pillars. You own `web/` and
nothing else. Do not scrape. Do not touch `pipeline/` except where Task 0 explicitly says to.

### The architectural line (already decided, already in the code)

Read these four comments before you write anything:

- `pipeline/export_matrix.py:1-10` — *"DB -> one JSON blob for the browser. Ship it once, score
  client-side. What this file must NOT do: compute percentiles, weights or composite scores.
  Those are what the sliders move, and percentiles are sector-relative so they go stale on every
  filter change... the browser does percentile + weighted sum per tick."*
- `pipeline/common/units.py:3-4` — *"The line this file defends: percentiles, weights and
  composite scores are NOT computed before the database."*
- `pipeline/common/schema.py:47` — confidence weight per status → point opacity.
- `pipeline/load.py:65` — per-company evidence weight → point opacity.

So: **Python owns harmonised values and provenance. The browser owns percentiles, weights and
composite scores.** The pillar scores are computed in TypeScript, on every slider tick, from
`data/matrix.json`. There is no `scores.csv` on the input path.

### Data topology (get this right, it has already misled people)

- `data/matrix.json` — **the integration surface.** ~1.9 MB, in the repo, committed, therefore
  the only artifact actually shared between teammates. Shape:
  `{schema: {field: {unit, pillar, dtype, description}}, source_priority: [...], urls: [...],
  companies: [{ticker, name, sector, sub_industry, confidence, fields: {field: {v,u,fy,src,st,c,q,url}}, alternatives: {...}}]}`
  `st` = status enum, `c` = confidence, `q` = **verbatim quote**, `url` = index into `urls`.
- The SQLite DB is at **`~/.cache/ethack/scores.db`**, not in the repo — deliberately, because the
  repo sits in iCloud Drive and SQLite on a synced filesystem throws `disk I/O error`
  (`pipeline/common/paths.py`). It is per-machine and rebuildable. **It is not the integration
  surface and you must never read it from the frontend.**
- `data/scores.db` (12 KB, 0 rows, missing the `disagreements` and `company_confidence` views) is
  a **stale decoy** from an older path config. Anyone pointing at it concludes the pipeline is
  dead. Task 0 deletes it.
- `data/wide*.csv`, `data/emissions.csv` — flat exports for humans and for the scoring oracle.
  Not your input.

### Status enum and confidence (fixed — from `pipeline/common/schema.py`, do not invent values)

| status | meaning | confidence |
|---|---|---|
| `structural` | machine-readable API field, no sentence to quote | 1.00 |
| `quote_verified` | prose claim, quote validated as exact substring | 0.85 |
| `imputed` | sector median / counterfactual, never a null | 0.30 |
| `not_disclosed` | we looked, nothing there — **a finding, not a gap** | 0.00 |
| `quote_failed` | quote claimed, quote did not validate; value discarded | 0.00 |

### Field coverage is thin and that is the point

27 of 59 fields carry data. P1 has 4 of 13 fields and no Scope 2 or Scope 3 at all. `scope1_tco2e`
exists for ~110 companies and **only for FY2023**. Your scoring registry must degrade honestly
when inputs are missing — never silently substitute a sector mean and render it as a measurement.

---

## Task 0 — Two small pipeline changes, then stop touching pipeline/

Get these merged first; everything else depends on them.

1. **Delete `data/scores.db`** and add it to `.gitignore`. It is a decoy.
2. **Split the payload.** `matrix.json` is 1.9 MB against a 2 MB budget, and `export_matrix.py`
   already warns about this. Since the browser now needs the payload *on boot* (it scores from
   it), split the exporter output:
   - `data/matrix.json` — values, units, fiscal years, source ids, status, confidence, url index.
     **No `q`.** Loads on boot. Target < 900 KB.
   - `data/quotes.json` — `{ticker: {field: quote}}`. Loads lazily on first point click.

   Add `schema_version` (integer, start at 1) and `generated_at` (ISO 8601) to both payloads.
   Keep the existing `schema` block — it comes from `fields.py` and is how the frontend validates
   that its scoring inputs exist.

## Task 1 — The scoring registry (the real contract; do this before any UI)

`web/src/scoring/registry.ts` is the single declaration of what a score is. One object per
sub-score:

```ts
{
  id: 'p1_carbon_intensity',
  pillar: 'P1',
  label: 'Carbon intensity',
  polarity: 'lower_is_better',        // stated, never assumed
  inputs: ['scope1_tco2e', 'revenue_usd'],   // canonical names from fields.py
  compute: (f) => f.scope1_tco2e / f.revenue_usd,
  nullPolicy: 'not_disclosed',        // 'not_disclosed' | 'sector_median' | 'zero'
  basis: 'FY2023',
}
```

Non-negotiable properties:

- **`inputs` are canonical `fields.py` names.** On boot, assert every input exists in
  `payload.schema` and **throw a visible error naming the missing field** if not. This is what
  keeps one vocabulary across Python and TS instead of two hand-synced ones. A renamed field must
  break the app loudly, not produce an empty axis on stage.
- **`polarity` is declared, not inferred.** Carbon-price exposure and carbon intensity are risk
  measures; board independence is not. The diverging colour scale and the "better/worse than
  reference" language are meaningless without it. Normalise to *higher is better* exactly once,
  in the percentile step, using `polarity`.
- **`nullPolicy` is declared per sub-score.** Defaulting a missing input to the sector median and
  plotting it as a solid point is the exact failure the project calls *rewarding silence* — it is
  live in `score_calculation/category_score_utils.py` right now (`_build_sector_intensity` gives
  non-reporting sectors the lowest observed intensity, so non-reporters score best). Do not
  reproduce it.

Pipeline (pure functions, each independently testable):

```
raw fields → compute() → sector percentile (polarity-adjusted) → sub-score 0–100
           → weighted mean per pillar → pillar score 0–100
           → weighted mean → composite
```

Percentiles are **within GICS sector**, computed over companies with a real value only —
`imputed`, `not_disclosed` and `quote_failed` are excluded from the distribution but still
rendered. Recompute on every weight change and every filter change; at 500×13 this is ~10 ms, so
do it synchronously in a memoised selector, not in a worker and not in the render loop.

Default sub-scores (from the pillar spec; all selectable, none hardcoded into a component):

- **P1 Environmental** — `p1_carbon_intensity`, `p1_energy_mix`, `p1_resource_waste`
- **P2 Transition** — `p2_carbon_price_exposure`, `p2_sector_exposure`, `p2_regulatory_momentum`,
  `p2_innovation`
- **P3 Governance** — `p3_board_independence`, `p3_exec_compensation`, `p3_controversy_flags`

Where a sub-score's inputs are not yet in `matrix.json` (most of P1 and P3), declare it anyway
with `nullPolicy: 'not_disclosed'` and let it render as an honest empty axis with a coverage
count. **An axis reading "0 / 500 companies" is a finding.** A fabricated axis is a lie that
survives until the Q&A.

## Task 2 — Weight sliders (this is what the architecture was built for)

Three pillar weight sliders plus per-sub-score weights within each pillar. Points move live as
weights change. Normalise weights to sum to 1 and show the normalised values.

Two things that make this a demo moment rather than a gimmick:

- **A "rank sensitivity" readout** — how far each company's rank moves across the plausible weight
  space. A ranking that collapses under a 10% weight change is not a ranking, and the project's
  own scope doc lists weight-sensitivity as an *output to protect*. Surface it.
- **Weight presets** — equal, environmental-led, transition-led, governance-led — so you can show
  the ranking's instability in three clicks instead of dragging on stage.

Persist weights to the URL hash so a specific view is shareable and reproducible.

## Task 3 — Fixture generator (so you are never blocked)

`web/scripts/make-fixture.ts` writes `web/public/data/matrix.fixture.json` in the **exact
`matrix.json` shape** — not a simplified stand-in, or you will debug the shape difference at
hour 20.

- Real tickers, names, sectors, market caps read from `data/wide.csv`.
- Realistic pathology: sector-clustered values, ~110 companies with `structural` Scope 1 and ~390
  `not_disclosed`, a long `imputed` tail, correlated columns, a few `alternatives` entries so the
  say-do panel has something to show.
- `--degenerate` reproduces the current known-bad state — one distinct value per GICS sector, zero
  within-sector variance — so you can prove the UI **exposes** a sector-dummy ranking rather than
  drawing a pretty cloud over it. Check this. It is the most likely way the real scores fail.

App loads `matrix.json` if present, else the fixture, with a persistent amber **FIXTURE DATA**
badge. Not optional — someone will demo this by accident.

## Task 4 — The map

Vite + React + TypeScript + `three` via `@react-three/fiber` + `@react-three/drei`, in `web/`.

**Install every dependency in the first ten minutes.** Final rehearsal is with wifi off: no CDN,
no Google Fonts, no runtime network call. `npm run build`, then serve the build with the network
disabled and confirm. Verify it, don't assume it.

Four views = four axis triples over one renderer and one config object, not four components:

| view | X | Y | Z |
|---|---|---|---|
| Global | `p1_environmental` | `p2_transition` | `p3_governance` |
| Environmental | `p1_carbon_intensity` | `p1_energy_mix` | `p1_resource_waste` |
| Transition | `p2_carbon_price_exposure` | `p2_sector_exposure` | `p2_regulatory_momentum` |
| Governance | `p3_board_independence` | `p3_exec_compensation` | `p3_controversy_flags` |

**Transition has four sub-scores and three axes.** Do not silently drop `p2_innovation`. Every
view gets three axis dropdowns bound to that pillar's registry entries; the table is the default.
New sub-scores then need no new code.

Encodings:

- **Colour** — reference-relative value, diverging scale. Not sector; sector is the filter.
- **Size** — `market_cap_usd`, sqrt-scaled, clamped so mega-caps don't eclipse the cloud.
- **Opacity** — the per-company `confidence` already in `matrix.json` (pillar-specific mean in a
  pillar view). A bright point in the good corner with low confidence is claiming to be good
  without evidence — that reading has to be legible from the back of a room.

## Task 5 — Reference point

Sets what "better/worse" is measured against: sector median (default), sector best-in-class,
index median, or **a named company** (searchable — "show me everything relative to Nvidia").

- Everything downstream recentres: diverging scale, optional delta axes centred on zero, the
  reference company pinned and marked.
- When the reference is a named company, *raw* and *sector-adjusted* are different claims. Put the
  mode in the label ("vs NVDA, raw" / "vs NVDA, sector-adjusted"). Never pick silently.
- Because scoring is client-side, the reference statistics come from the **same percentile
  machinery** as the scores. Do not write a second median implementation — that is how the map
  ends up contradicting the table.
- `not_disclosed` and `imputed` points render hollow/wireframe, are excluded from the reference
  calculation, and get a legend count: *"390 companies do not disclose Scope 1."* That count is a
  headline finding and belongs on screen.

## Task 6 — Click a point → the audit trail

The best demo moment available. Clicking opens a detail panel: company header, pillar scores with
their sub-scores, and **the full derivation** — for each sub-score, the raw input values, their
fiscal years, source ids, status badges, the computed value, the sector percentile, and the
weight applied. Then the verbatim quote from `quotes.json` (lazy-loaded on first click) with the
resolved `urls[url]` as a link.

Where `alternatives` exists, show it as **"EPA says X, the company says Y"** — that is the
say–do gap, and `export_matrix.py` already carries the data for it.

Where status is `not_disclosed`, say so in plain words. Never render a blank.

## Task 7 — Shell

- Sector filter (11 GICS sectors), multi-select, with counts. Filter changes recompute percentiles.
- Search / jump-to-company.
- Permanent legend covering all three encodings.
- **Coverage strip** per view: of 500 companies, how many have measured / imputed / not-disclosed
  values on the three visible axes. Honest coverage on screen is a differentiator, not an
  admission.
- **Provenance footer**: `generated_at` from the payload, `schema_version`, and a basis-year note —
  "Emissions FY2023 (latest GHGRP); financials FY2025. Fiscal year-ends span Jan–Dec, which is
  standard practice." Go amber if `generated_at` is more than 2 hours old. *"The map is showing
  yesterday's numbers"* is a classic 2 a.m. hour lost.
- Camera: orbit + zoom, reset, four presets that actually read well. Axis labels legible at every
  angle — a 3D scatter you cannot orient is worse than a 2D one.

## Task 8 — `npm run data` and the Python oracle

**`npm run data`** shells out to the exporter and writes straight into `web/public/data/`:
`python -m pipeline.export_matrix --out web/public/data/matrix.json`. One command. Nobody should
ever wonder whether the map is showing stale scores, and no symlink or manual copy step should
exist to go wrong.

**The oracle.** Scoring now has exactly one runtime implementation (TypeScript). That is correct —
two implementations drift — but it means a formula bug is invisible. So Lane A's Python
`score.py` becomes a **checker, not a producer**: it computes the same sub-scores at default
weights from the same `matrix.json` and writes `data/scores_oracle.csv`. Then:

```
npm run verify:oracle    # asserts TS and Python agree within 1e-6 on all 500 rows × all sub-scores
```

Print the worst disagreements by ticker and field. This is the project's own instinct — *load a
second opinion as a separate source rather than merging it* — applied to our own scoring layer.
It is also the only thing standing between you and a confidently wrong number on a slide.

**Tell Lane A this is the interface** before you write UI: they write `score.py` as a pure
function `matrix.json → scores_oracle.csv`, not as the map's data source. If they have already
started the other way, the work is not wasted — the formulas port directly into the registry.

## Order of work

1. Task 0 (pipeline split + decoy deletion). Commit. **Tell the team the payload shape is frozen.**
2. Registry + percentile/weight pipeline + unit tests on synthetic input. Commit.
3. Fixture generator. Commit.
4. Global view over the fixture: sector filter, legend, weight sliders.
5. Reference-point machinery + diverging scale.
6. The other three views (nearly free if the config is right).
7. Detail panel + `quotes.json`.
8. Coverage strip, provenance footer, presets, `verify:oracle`.

Commit after each. Don't build feature 9 before 1–8 are real.

## Checks before you say you're done

- `npm run build`, serve **with the network disabled**, confirm it works.
- `--degenerate` fixture: confirm the UI makes the sector-dummy pathology visible.
- Truncated / malformed payload: confirm a red banner naming the violated rule, not a silent render.
- A registry entry referencing a field absent from `payload.schema`: confirm it throws by name.
- `npm run verify:oracle` passes, or prints exactly where TS and Python disagree.
- Rotate every view; axis labels readable at every angle.
- Fixture badge appears on fixture data, disappears on the real payload.

Ask me before adding any dependency not needed for the above, and before changing anything in
`pipeline/` beyond Task 0.
