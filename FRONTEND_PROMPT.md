# Claude Code prompt — build the 3D sustainability map (`web/`)

Paste everything below the line into Claude Code, run from the repo root (`ethack/ethack`).

---

## Context

This is a 24h hackathon repo that ranks the S&P 500 on three sustainability pillars. The data
pipeline (`pipeline/`) and the scoring layer (`score_calculation/` → `score.py`) are being built
**in parallel, by other people, right now**. `data/scores.csv` **does not exist yet**.

Your job is the frontend, and the single most important property of your work is that it is
**not blocked by, and does not block, the scoring lane**. You will build against a frozen data
contract and a fixture generator, and the real `data/scores.csv` will drop in later with zero
code changes.

Do not scrape anything. Do not compute a pillar score. Do not touch `pipeline/`,
`score_calculation/`, or anything in `data/` except reading. You own `web/` and nothing else.

### What already exists (read these before writing code)

- `data/wide.csv`, `data/wide_FY2023.csv`, `data/wide_FY2025.csv` — 500 rows, one per ticker,
  the raw field matrix. `wide_FY2023.csv` is the emissions-aligned export; `wide_FY2025.csv` is
  financial-only. Companion `*_status.csv` and `*_year.csv` carry per-cell provenance and fiscal year.
- `data/emissions.csv` — 500 rows: `ticker, company, sector, scope1_tco2e, emissions_source_tier,
  ghgrp_facility_count, sbti_tier, target_year`.
- `data/matrix.json` — ~1.9 MB. Shape:
  `{schema: {field: {unit, pillar, dtype, description}}, source_priority: [...], urls: [...],
  companies: [{ticker, name, sector, sub_industry, confidence, fields: {field: {v, u, fy, src, st, c, q, url}}, alternatives: {...}}]}`
  where `st` is the status enum, `c` the confidence, `q` the **verbatim quote**, and `url` an index
  into the top-level `urls` array. This is the audit trail. You will use it.
- `visualize_scores_3d.py` — a throwaway Plotly sketch. Read it for intent, then ignore it.
- `pipeline/common/fields.py` — 59 canonical field names with pillar tags (`P1`/`P2`/`P3`/`X`).
  Field names in the contract below must not drift from these.

### The status enum and confidence (fixed, do not invent values)

| status | meaning | confidence |
|---|---|---|
| `structural` | machine-readable API field, no sentence to quote | 1.00 |
| `quote_verified` | prose claim, quote validated as exact substring | 0.85 |
| `imputed` | sector median / counterfactual. Never a null. | 0.30 |
| `not_disclosed` | we looked, nothing was there — **this is a finding, not a gap** | 0.00 |
| `quote_failed` | quote claimed, quote did not validate; value discarded | 0.00 |

---

## Task 1 — Freeze the data contract (do this first, in one commit, before any UI)

Write `web/src/contract.ts` and `web/CONTRACT.md`. The contract is what the scoring lane will
target, so it has to be legible to a person who is not reading your TypeScript.

`data/scores.csv` — exactly **500 rows**, joined on `ticker`, missing data is a row with a status,
never an absent row:

```
ticker, company, sector, sub_industry, market_cap_usd, basis_year,

p1_environmental, p2_transition, p3_governance,            # pillar scores, 0–100

p1_carbon_intensity, p1_energy_mix, p1_resource_waste,
p2_carbon_price_exposure, p2_sector_exposure, p2_regulatory_momentum, p2_innovation,
p3_board_independence, p3_exec_compensation, p3_controversy_flags,   # sub-scores, 0–100

confidence_overall, confidence_p1, confidence_p2, confidence_p3,     # 0–1
<every score column above>_status                           # the enum, per cell
```

Rules the frontend enforces and displays:

1. Every score is **0–100, higher is better**, already sector-normalised by the scoring lane.
   The frontend never rescales a raw field into a score.
2. A `*_status` of `not_disclosed` or `quote_failed` means the accompanying score is
   **not a number you may plot as if measured**. Render it, but render it as visibly different
   (see Task 4).
3. `basis_year` per row. Emissions-derived columns are FY2023-anchored; financial-only columns
   are FY2025. Surface this in the UI rather than hiding it.

Write a loader that **validates on load** and fails loudly: 500 rows, no unknown columns, no
score outside 0–100, no status outside the enum, no ticker duplicated. Print a summary table of
coverage per column to the console on boot. If the file is malformed, show a red banner naming the
violated rule — do not silently drop rows.

## Task 2 — Fixture generator (so you are never blocked)

`web/scripts/make-fixture.ts` (or `.mjs`) writes `web/public/data/scores.fixture.csv`:

- Real tickers, company names, sectors and market caps read from `data/wide.csv` — so sector
  filters and bubble sizes look right from minute one.
- Synthetic scores with **deliberately realistic pathology**, because the real data has it:
  sector-clustered means, within-sector variance, ~110 rows with `structural` emissions status
  and ~390 `not_disclosed`, a long tail of `imputed`, and a handful of correlated columns.
- A `--degenerate` flag that produces the current known-bad state (one distinct value per sector,
  zero within-sector variance) so you can prove the UI *visibly exposes* that failure rather than
  drawing a pretty cloud over it.

App reads `scores.csv` if present, else the fixture, and shows a persistent amber "FIXTURE DATA"
badge in the corner whenever it is on the fixture. That badge is not optional — someone will
demo this by accident.

## Task 3 — The map

Vite + React + TypeScript + `three` via `@react-three/fiber` and `@react-three/drei`.
Live in `web/`, a sibling of `pipeline/` and `score_calculation/`.

**Install every dependency now, in the first ten minutes.** The final rehearsal happens with wifi
off: no CDN, no Google Fonts, no runtime network call. `npm run build` must produce something that
runs from a local static server with the network disabled. Verify that, don't assume it.

Four views. Each view is nothing but a different triple of axis columns — one renderer, one config
object, not four components:

| view | X | Y | Z |
|---|---|---|---|
| Global | `p1_environmental` | `p2_transition` | `p3_governance` |
| Environmental | `p1_carbon_intensity` | `p1_energy_mix` | `p1_resource_waste` |
| Transition | `p2_carbon_price_exposure` | `p2_sector_exposure` | `p2_regulatory_momentum` |
| Governance | `p3_board_independence` | `p3_exec_compensation` | `p3_controversy_flags` |

**Transition has four sub-scores and three axes.** Do not quietly drop `p2_innovation`. Give every
view three axis dropdowns bound to that pillar's available columns; the table above is the default,
and the unused fourth stays selectable. This also means new sub-scores need no new code.

Encodings:

- **Colour** — the median-relative value on a diverging scale. Not sector. Sector is the filter.
- **Size** — `market_cap_usd`, sqrt-scaled, clamped so mega-caps don't eclipse the cloud.
- **Opacity** — `confidence_overall` (or the pillar-specific confidence in a pillar view).
  Low-confidence points are ghosts. This is a load-bearing claim of the project, so make it
  obvious enough to read from the back of a room.

## Task 4 — Reference point (the interesting part)

A control that sets what "better/worse" is measured against:

- Sector median (default)
- Sector best-in-class
- Index median
- **A specific named company** — searchable ticker/name picker, e.g. "show me everything relative
  to Nvidia"

Everything downstream recomputes against that reference: the diverging colour scale centres on it,
axes optionally switch to a delta scale centred on zero, and the reference company itself is
pinned and visually marked. Recompute must be instant at 500 points — do it in a memoised
selector, not in the render loop.

Two things that are easy to get wrong and matter:

- When the reference is a named company, a **sector median comparison across sectors is a
  different claim** than within-sector. Make the mode explicit in the label ("vs NVDA, raw" /
  "vs NVDA, sector-adjusted"), don't pick silently.
- Points whose status is `not_disclosed` or `imputed` must not look like measured points sitting
  at the median. Render them as hollow/wireframe markers, exclude them from the reference
  calculation, and give the legend a count: *"390 companies do not disclose Scope 1."* That count
  is one of the project's headline findings — it belongs on screen, not in a footnote.

## Task 5 — Click a point → the audit trail

The best demo moment available, per the project's own scope doc: **click any number, see the
sentence the company wrote.**

Clicking a point opens a detail panel: company header, the three pillar scores with their
sub-scores, and for each underlying field pulled from `data/matrix.json` — the value, the fiscal
year, the source id, the status badge, and where `q` is non-null the **verbatim quote**, with the
resolved `url` as a link. Where status is `not_disclosed`, say so in plain words instead of
showing a blank.

`matrix.json` is ~1.9 MB. Lazy-load it on first point click, not on boot.

## Task 6 — Everything else in the shell

- Sector filter (11 GICS sectors), multi-select, with company counts.
- Search / jump-to-company.
- Legend explaining all three encodings, permanently visible.
- A coverage strip: per selected view, how many of the 500 companies have measured vs imputed vs
  not-disclosed values on those three axes. Honest coverage on screen is a differentiator here,
  not an admission.
- Basis-year note: "Emissions FY2023 (latest GHGRP); financials FY2025. Fiscal year-ends span
  Jan–Dec, which is standard practice."
- Camera: orbit + zoom, a reset button, and four preset angles that actually read well — a 3D
  scatter you cannot orient is worse than a 2D one. Axis labels must stay legible while rotating.

## Order of work

1. Contract + validating loader + fixture generator. Commit. **Tell the scoring lane the contract
   is frozen before you write any UI.**
2. Global view rendering the fixture, with sector filter and legend.
3. Reference-point machinery with the diverging scale.
4. The other three views (which should be almost free if the config is right).
5. Detail panel on `matrix.json`.
6. Coverage strip, presets, polish.

Commit after each. Don't build feature 7 before 1–6 are real — the marginal hour is worth more
proving what's there.

## Checks before you say you're done

- `npm run build`, then serve the build **with the network disabled** and confirm it works.
- Load the `--degenerate` fixture and confirm the UI makes the sector-dummy pathology visible.
- Load a truncated / malformed CSV and confirm the red banner appears instead of a silent render.
- Rotate every view and confirm the axis labels are readable at every angle.
- Confirm the fixture badge appears on fixture data and disappears on the real file.

Ask me before adding any dependency not needed for the above, and before changing anything outside
`web/`.
