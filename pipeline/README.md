# pipeline/ — getting the data

`pipeline/` fetches and extracts. `score_calculation/` turns the result into
scores. They are separate because they have opposite properties: ingest is slow,
network-bound and run once; scoring is fast, offline, and re-run twenty times
tonight as the weights move.

## The rule this whole thing exists to enforce

**Every extracted number carries a verbatim quote, or it is null.** Validated
mechanically in `common/quotes.py`: if the quote is not a character-for-character
substring of the source, the record is downgraded to `quote_failed` and its value
discarded. *Not disclosed is a signal, not a gap* — a company that said nothing is
written as `not_disclosed`, never skipped.

## Data flow

```
  network → cache/raw/<source>/          pull.py     (idempotent, re-run is free)
          → data/observations/<source>/*.jsonl   extract.py  (NO network, append-only)
          → data/scores.db                load.py     (the ONLY writer)
          → data/matrix.json              export_matrix.py
          → browser                       percentiles + weights, client-side, per tick
```

`rm data/scores.db && python -m pipeline.load` must always work. If it ever
doesn't, the database has become load-bearing and someone wrote to it out of
band. Find that and delete it.

Scoring does **not** happen here. Percentiles are sector-relative, so they go
stale the moment a filter changes — and they are exactly what the sliders move.
Python round-trips are the only real source of slider latency; the maths itself
is ~10ms in JS. Shipping the matrix once also means the demo works with the
wifi off, which is why we rehearse that way.

## First run

**Run this from your own terminal.** The pulls need internet, and the agent
sandboxes do not have it — the container proxy returns 403 for `data.sec.gov`,
`en.wikipedia.org`, `query2.finance.yahoo.com` and `www.epa.gov`, and the device
shell has no egress at all. Extraction, loading and testing work anywhere.

```bash
pip install yfinance rapidfuzz pyxlsb        # conda: -c conda-forge
export SEC_USER_AGENT="ETH Hackathon Team you@example.com"   # EDGAR blocks you without a real address

python -m pipeline.test_pipeline             # prove the contract still holds (offline)
python -m pipeline.run_structural --limit 10 # smoke: S08, S01, S07, S14 on 10 companies
python -m pipeline.run_structural            # all 500 — S01 is ~2 min at 8 req/s
python -m pipeline.manifest --csv            # coverage, by field and by sector
python -m pipeline.export_matrix             # data/matrix.json for the dashboard
```

`--skip-pull` re-extracts from the existing cache with no network at all. That is
the path that must work at hour 20 with the wifi off.

### Where things live

| | |
|---|---|
| `data/observations/*.jsonl` | source of truth, append-only. **Commit these** — the team shares data without re-pulling. |
| `cache/` | raw fetches. Large, reproducible, gitignored. |
| `~/.cache/ethack/scores.db` | the database, **outside the repo on purpose** — this repo is in iCloud Drive and SQLite fails there with `disk I/O error`. Override with `$ETHACK_DB`. |
| `data/matrix.json` | the browser payload. Rebuilt, gitignored. |

### Verifying a source before you trust it

`test_pipeline.py` proves the shared contract. Each source should also prove its
own extraction rules against a fixture — see
`sources/s01_sec_xbrl/test_extract_fixture.py`, which plants the traps that
produce *plausible* wrong numbers (a quarterly fact read as annual, a
restatement ordered wrongly, a half-computed FCF) and checks each is caught.
Copy that pattern rather than trusting a source because it ran without error.

## Layout

```
common/
  schema.py     FROZEN record shape + write-time validation. Read this first.
  fields.py     THE CONTRACT: 59 canonical field names, units, dtypes, owning sources
  quotes.py     the substring rule, typography normalisation, negation flag
  cache.py      L1 raw (never deleted) / L2 extracted (cheap to delete)
  jsonl.py      append-only writer, validates before anything reaches disk
  sec_client.py ONE client for S01–S05. Do not write four fetchers.
  http.py       polite session + shared rate limiter for everything else
  units.py      unit harmonisation, currency, fiscal-year alignment
  entities.py   ticker ↔ CIK ↔ legal name; fuzzy match is last resort and always flagged
  paths.py      repo-root anchored, so cwd stops mattering
sources/sNN_*/  one package per source — SOURCE.md, fields.py, pull.py, extract.py, test_smoke.py
load.py         JSONL → SQLite. Sole writer.
manifest.py     coverage grid — the answer to silent partial failure
export_matrix.py  DB → one JSON for the browser
test_pipeline.py  end-to-end proof on fake records, no network
```

## Rules that keep sixteen parallel agents from colliding

1. **A source package imports only `common`.** Never another source package.
2. **`pull.py` does network→cache. `extract.py` does cache→JSONL.** Nothing else.
   `extract.py` must run with the wifi off, forever.
3. **Only names in `common/fields.py` may be emitted.** Need a new one? Add it
   there first. This is the contract; inventing names locally is how you get
   four incompatible pipelines and a half-empty join at hour 20.
4. **Only `load.py` writes to the database.**
5. **Nothing before the DB is peer-relative.** No percentiles, no weights, no
   composite scores. Deterministic transforms only.

## Status vocabulary

| status | meaning | confidence |
|---|---|---|
| `structural` | machine-readable fact (XBRL, CSV, JSON API). No quote possible. | 1.00 |
| `quote_verified` | prose claim whose quote validated as a substring | 0.85 |
| `imputed` | modelled / counterfactual (e.g. sector-median target). Never a null — nulls reward silence. | 0.30 |
| `not_disclosed` | we looked, there was nothing. **A finding.** | 0.00 |
| `quote_failed` | a quote was claimed and did not validate. Value discarded. | 0.00 |

`structural` and `imputed` are additions to the three-value enum in the plan doc.
Without `structural`, the entire XBRL layer would mark itself `not_disclosed`
(a JSON API field has no sentence to quote) and the confidence score would be
meaningless.

## Why `source` is in the primary key

`PRIMARY KEY (ticker, field, source, fiscal_year)` — so an EPA-measured, a
company-reported and a modelled value of the same number coexist rather than
overwrite. That coexistence *is* the say–do comparison, expressed at the storage
layer. The `disagreements` view in `load.py` reads it back out. Keep that view
working; it is the product.

## Known gaps, stated honestly

- `y02_patent_share_pct` is in the vocabulary but **no in-scope source emits it**
  (S24 PatentsView is Tier 3). `test_pipeline.py` prints this every run rather
  than letting it pass unnoticed.
- **S11** (Violation Tracker) has no public API and **S13** (CDP) is licence-gated.
  Both have folders whose `pull()` raises `NotImplementedError` with the reason,
  so the manifest reports *why* coverage is zero instead of showing a silent gap.
- Facility divestitures look identical to emissions cuts. `ghg_facility_count` is
  emitted every year so companies whose count moves YoY can be excluded from
  trajectory scoring. Do not skip this.
