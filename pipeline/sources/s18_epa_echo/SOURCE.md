# S18 — EPA ECHO

> Auto-generated from `sp500_sustainability_data_sources.xlsx`. This file is the
> brief for whoever (or whatever) builds this package. Edit freely once claimed.

**Owner** US EPA  **Tier** 3 - Narrow  **Priority** SHOULD  **Effort** Low
**Pillar** P3  **Expected coverage** 200 / 500

## What it is
Compliance and enforcement history for permitted facilities.

## What you get from it
Inspections, violations, penalties, compliance status by facility, across Clean Air / Clean Water / RCRA.

## Feeds
Controversy flag (environmental, hard-edged)

## Access
| | |
|---|---|
| Method | REST API |
| Endpoint | https://echo.epa.gov/tools/web-services |
| Auth | None required |
| Format | JSON / CSV |
| Packages | requests, pandas |

## Gotchas (from the register)
Joins directly to the GHGRP/TRI facilities you already matched, so the marginal cost is low once entity resolution exists. Broader than GHGRP because water and waste permits catch non-emitters. Violation COUNT correlates with facility count — normalise per facility.

## Notes from the planning session
The fallback for S11 (Violation Tracker), which is licence-gated for bulk
export. ECHO's own REST API IS freely pullable (echodata.epa.gov, no
auth, no ToS restriction on automation) -- confirmed live, unlike S11's
Cloudflare-protected site.

BUT: entity resolution here is name-matching on facility records
(echo_rest_services.get_facilities, p_fn/p_fntype=BEGINS), not a
curated parent mapping like Violation Tracker's. Confirmed live against
the real API: for a company with owned-and-operated sites only
(LOCKHEED MARTIN) this returns ~500 plausible facilities. For a company
with a franchised/branded retail footprint (EXXON MOBIL, CHEVRON) it
also pulls in thousands of independently-owned gas stations that merely
license the brand -- CHEVRON matched 8,059 facilities this way, versus
496 for Lockheed Martin, which is not a real difference in EPA
enforcement exposure, just brand-name noise.

Given that, penalty_total_usd/penalty_count from S18 are written as
status=IMPUTED (confidence 0.30), never STRUCTURAL -- the numbers are
real EPA data but the company match under a plain name search is not
verified the way S01-S07's CIK/ticker join is. Do not silently upgrade
this to STRUCTURAL without adding real entity resolution (e.g. joining
through the FRS bulk parent-company file, not text search).

There is also no per-year breakdown available from get_facilities --
TotalPenalties is EPA's own cumulative total since it started tracking
(~2000), not an annual figure. fiscal_year is set to the year the pull
ran, representing 'as observed on this date', not a single year's
penalties. This is a real mismatch with S11's per-case-per-year
granularity -- flag it if the two sources are ever compared directly.

penalty_count is FEARows + InfFEARows (facilities with a formal or
informal enforcement action) from the same call, not a count of
individual penalty transactions -- cheaper than paginating every
matched facility, and precision does not matter more than the name
match noise already does.

case_rest_services.get_cases (the endpoint that would give real
per-case, per-year penalty amounts) does NOT filter by company/case
name at all, verified directly against the API and against ECHO's own
public case-search page -- both ignore the name filter and return
unrelated cases. Do not build on p_name for that endpoint; it is a
dead end as of this writing.

## Fields this package may emit
| field | unit | type | what it is |
|---|---|---|---|
| `penalty_total_usd` | usd | float | Penalties from COURT AND AGENCY RECORDS, not news sentiment. News-based controversy scores measure media volume, which tracks company size. |
| `penalty_count` | count | int | Number of penalty records |

Emitting any other field name is a bug. If you need a new one, add it to
`pipeline/common/fields.py` first — the vocabulary is the contract.

## Definition of done
- [x] `pull(tickers)` fetches to the L1 raw cache and is idempotent; a second run makes no network calls
- [x] `extract(tickers)` runs with the network OFF and writes JSONL only
- [ ] Every prose-derived number carries a verbatim quote that validates as a substring — N/A, nothing here is prose-derived
- [ ] Machine-readable facts use `Status.STRUCTURAL` (no quote), not `quote_verified` — deliberately NOT done: written as `Status.IMPUTED` instead, because the facility-name match is unverified (see notes above). Do not "fix" this to STRUCTURAL without adding real entity resolution.
- [x] Companies that disclosed nothing are written as `not_disclosed` — never skipped (used for names too short/ambiguous to search, or a query ECHO rejects as too broad even at EXACT)
- [x] `python -m pipeline.sources.s18_epa_echo.test_smoke` passes on 10 tickers
- [ ] Coverage matches the 200/500 expectation above, or you can say why not — untested at 500; expect close to 500/500 responding (ECHO answers for almost any name), but a meaningful share of that is brand-name noise on retail/franchise companies, not clean 200-company coverage the way the register's estimate implies
