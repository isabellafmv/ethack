// THE single declaration of what a score is. One object per sub-score.
//
// `inputs` must be canonical pipeline/common/fields.py names -- that shared
// vocabulary is what keeps Python and TypeScript from drifting into two
// hand-synced dictionaries. assertRegistryMatchesSchema() below is called on
// boot and throws BY NAME if a field was renamed or removed upstream; a
// renamed field must break the app loudly, never produce a silently empty
// axis on stage.
//
// `polarity` is declared, not inferred, because the diverging colour scale
// and "better/worse than reference" language downstream are meaningless
// without knowing which direction is good. `nullPolicy` is declared per
// sub-score for the same reason: defaulting a missing input to the sector
// median and plotting it as a solid point is "rewarding silence" -- the
// non-reporter bug live in score_calculation/transition/transition_score.py's
// _build_sector_intensity (a since-deleted file, category_score_utils.py,
// was the historical location; the pattern moved, the risk didn't). Most
// sub-scores below use nullPolicy 'not_disclosed'; 'sector_median' is used
// where the project has deliberately decided that silence itself is the
// finding; 'zero' exists for a sub-score with an honest reason to need it,
// not as a default.
//
// `scoringMode` says what happens to a sub-score's raw value on its way to
// a final 0-100 score -- see score_calculation/*/*.py, the Python oracle
// this file is built to numerically match:
//   - 'sector_percentile' (default): rank the raw metric against measured
//     peers in the same GICS sector. Most P1 indicators.
//   - 'absolute': compute() (or crossCompanyCompute/percentileComponents,
//     see below) already returns the final oriented 0-100 score -- do NOT
//     percentile-rank it again. Most of P2 and P3.
//   - 'sector_normalized': one constant value per sector (a cross-SECTOR,
//     not cross-company, min-max rank) -- p2_sector_exposure only.
//   - 'universe_percentile': percentile-ranked against every company in the
//     index, ignoring sector -- p3_controversy_flags only, matching
//     governance_score.py's universe-wide penalty ranking.

import { coerceFieldValue, MEASURED_STATUSES, TRUSTED_STATUSES, type Company } from "./types";
import { median } from "./percentile";

export type Pillar = "P1" | "P2" | "P3";
export type Polarity = "higher_is_better" | "lower_is_better";
export type NullPolicy = "not_disclosed" | "sector_median" | "zero";
export type ScoringMode = "sector_percentile" | "absolute" | "sector_normalized" | "universe_percentile";

/** 'pipeline_gap': null because the data source hasn't been pulled for
 * effectively the whole universe -- nobody's fault, so it's excluded from
 * the disclosure-coverage penalty in pipeline.ts (renormalizing around it
 * for free is already correct and this must not double-count that). Default
 * is 'disclosure_gap': a company-specific absence of otherwise-available
 * data counts against that pillar's disclosure coverage. Mirrors
 * score_calculation's PIPELINE_GAP_INDICATORS / disclosure-gap taxonomy. */
export type GapKind = "pipeline_gap" | "disclosure_gap";

/** Raw canonical-field values for one company, coerced to number (booleans
 * become 1/0). Only ever contains the inputs a sub-score declared, and only
 * once every one of them has a trustworthy value -- see pipeline.ts. */
export type RawInputs = Record<string, number>;

/** A field that participates in compute() but never gates availability --
 * an absent/untrusted optional field is substituted with `fillValue`
 * (mirrors the per-field `nullPolicy: 'zero'` convention, just scoped to one
 * field of a multi-input sub-score instead of the whole thing).
 * `fillValue: 0` is for a field whose absence is a genuine structural zero
 * (a company with no buyback program simply omits the XBRL tag -- see
 * p3_capital_stewardship). `fillValue: NaN` is for a field whose absence
 * should make compute() SKIP that component of a blend entirely rather than
 * silently score it as zero (see p2_regulatory_momentum's R&D blend,
 * p3_board_independence's lead-director/ratio blend) -- compute() must
 * Number.isFinite()-check before using an input with this fill value. */
export interface OptionalInput {
  field: string;
  fillValue: number;
}

/** For a sub-score whose score is the skip-null MEAN of two or more raw
 * metrics, each independently percentile-ranked against its OWN
 * measured-peer sector distribution before being averaged -- unlike a plain
 * `compute` (one raw value, one percentile step) or `optionalInputs` (a
 * single substituted value folded into one compute()). Only
 * p1_input_efficiency needs this today, mirroring
 * environmental_score.py's _input_efficiency_score exactly: COGS/revenue
 * and energy-cost/revenue are ranked SEPARATELY (each against companies
 * that disclose that one metric), then averaged over whichever exist.
 * pipeline.ts builds one distribution per component (keyed by
 * `${sub.id}::${component.id}`), percentile-ranks each company's present
 * components independently, and skip-null-means the results -- bypassing
 * the sub-score's own top-level `compute`/`polarity`/`inputs` entirely. */
export interface PercentileComponent {
  id: string;
  inputs: string[];
  polarity: Polarity;
  compute: (f: RawInputs) => number;
}

export interface SubScoreDef {
  id: string;
  pillar: Pillar;
  label: string;
  polarity: Polarity;
  inputs: string[];
  optionalInputs?: OptionalInput[];
  /** For a sub-score with NO required `inputs` (an empty array) whose score
   * is a skip-null mean of only-ever-optional components: without this,
   * resolveInputs would call every such sub-score "measured" unconditionally
   * (nothing in `inputs` can ever fail), even when literally every one of
   * its optionalInputs is absent -- wrong whenever Python's own formula CAN
   * go null in that case (a plain pandas `.mean(skipna=True)` over an
   * all-NaN row IS NaN). Declares which fields must have at least ONE
   * genuinely present before this sub-score counts as available/disclosed.
   * Only set where Python's formula can truly go null this way (see
   * p3_board_independence, p3_climate_governance); p2_regulatory_momentum
   * deliberately has none, matching transition_score.py's own documented
   * caveat that its tier function never actually returns null. */
  requiresAnyOf?: string[];
  compute: (f: RawInputs) => number;
  /** For a sub-score whose raw value needs more than one company's own
   * fields -- a sector-level aggregate, a cross-sector benchmark, a
   * counterfactual median across peers -- `compute` cannot do it (it only
   * ever sees one company's already-resolved inputs). When set, pipeline.ts
   * calls this ONCE per computeScores() call with the full company list and
   * uses its per-ticker result (already a final, oriented 0-100 value, or
   * null when that company can't be scored) instead of calling
   * `compute`/`inputs`/percentileRank for this sub-score at all. Only
   * p2_sector_exposure (a sector-level GHGRP intensity benchmark) and
   * p2_transition_affordability (needs that same benchmark PLUS a
   * sector-median counterfactual SBTi target) need this today -- both
   * mirror a whole-DataFrame computation in transition_score.py that has no
   * single-company equivalent. */
  crossCompanyCompute?: (companies: readonly Company[]) => Map<string, number | null>;
  /** See PercentileComponent -- only p1_input_efficiency uses this. */
  percentileComponents?: PercentileComponent[];
  nullPolicy: NullPolicy;
  /** Defaults to 'sector_percentile' when omitted. */
  scoringMode?: ScoringMode;
  /** Defaults to 'disclosure_gap' when omitted -- see GapKind. */
  gapKind?: GapKind;
  basis: string;
  /** Plain-language explanation for the axis-picker info popover (Task 7).
   * Written for a viewer with zero pipeline/Python context -- covers what it
   * measures, where the number comes from and its real coverage, any caveat
   * that would otherwise mislead, and how the raw value becomes the 0-100
   * shown on the axis (naming its scoringMode). Deliberately NOT the
   * developer comments above: those assume source-reading context a viewer
   * of the deployed site never has. */
  description: string;
}

/** Fields that must never enter a pillar score (mirrors fields.py
 * VALIDATION_ONLY). Enforced in assertRegistryMatchesSchema so nobody wires
 * the thing we're trying to beat into the thing that beats it. */
export const VALIDATION_ONLY_FIELDS = new Set([
  "esg_risk_score_external",
  "esg_controversy_level_external",
]);

const pct = (n: number, d: number): number => (d === 0 ? NaN : (n / d) * 100);

/** sbti_target_type arrives as a category string ("near-term" | "net-zero" |
 * "commitment"), not a number -- RawInputs stays numeric-only by design
 * (every arithmetic compute() in this registry relies on that), so
 * pipeline.ts's coerce() encodes it to one of these small integers before it
 * ever reaches compute(). An unrecognised/absent value coerces to NaN there,
 * same as any other malformed input. Exported so pipeline.ts's coerce() and
 * this file's SBTI_TIER_SCORE agree on the same three codes. */
export const SBTI_TARGET_TYPE_CODES: Readonly<Record<string, number>> = {
  "near-term": 1,
  "net-zero": 2,
  commitment: 3,
};

/** transition_score.py's COMMITMENT_SCORES, keyed by SBTI_TARGET_TYPE_CODES
 * instead of the raw strings. "no_target" (validated=false, or an
 * unrecognised type) is the implicit 0 -- not a key here, same as Python's
 * dict, which also maps "no_target" to 0. */
const SBTI_TIER_SCORE: Readonly<Record<number, number>> = {
  [SBTI_TARGET_TYPE_CODES["near-term"]]: 75,
  [SBTI_TARGET_TYPE_CODES["net-zero"]]: 100,
  [SBTI_TARGET_TYPE_CODES.commitment]: 25,
};

const RND_INTENSITY_CAP_PCT = 15.0;

/** Ported from score_calculation/transition/sector_assumptions.py verbatim
 * -- illustrative marginal abatement cost per tCO2e, by GICS sector. See
 * that file's own docstring for the literature this is loosely based on;
 * it's an order-of-magnitude estimate, not a per-company figure. */
export const SECTOR_ABATEMENT_COST_USD_PER_TCO2E: Readonly<Record<string, number>> = {
  Utilities: 30,
  Energy: 100,
  Materials: 120,
  Industrials: 75,
  "Consumer Staples": 60,
  "Consumer Discretionary": 50,
  "Health Care": 50,
  "Information Technology": 40,
  Financials: 40,
  "Real Estate": 45,
  "Communication Services": 40,
};
export const DEFAULT_ABATEMENT_COST_USD_PER_TCO2E = 60;

const CURRENT_YEAR = 2024; // anchor for "years to target" -- matches transition_score.py's own constant
const AFFORDABILITY_COST_CEILING_PCT = 100.0;

/** Fixed default sub-score weights for P2, mirroring transition_score.py's
 * WEIGHTS dict exactly. NOT materiality-derived and NOT per-sector (unlike
 * P1 -- see materiality.ts/weights.ts's pythonDefaultWeights): Python
 * applies these same four numbers to every company regardless of sector. */
export const PYTHON_P2_WEIGHTS: Readonly<Record<string, number>> = {
  p2_carbon_price_exposure: 0.32,
  p2_sector_exposure: 0.08,
  p2_regulatory_momentum: 0.25,
  p2_transition_affordability: 0.35,
};

/** Fixed default sub-score weights for P3, mirroring governance_score.py's
 * WEIGHTS dict exactly -- see PYTHON_P2_WEIGHTS's own note. */
export const PYTHON_P3_WEIGHTS: Readonly<Record<string, number>> = {
  p3_capital_stewardship: 0.25,
  p3_climate_governance: 0.3,
  p3_exec_compensation: 0.15,
  p3_board_independence: 0.05,
  p3_controversy_flags: 0.25,
};

/** Sums a {sector -> (numerator, denominator)} GHGRP-measured aggregate,
 * over MEASURED-tier scope1_tco2e and revenue_usd only (mirrors
 * transition_score.py's _build_sector_intensity: `df.dropna(subset=
 * ["scope1_tco2e", "revenue_usd"])` reads the pipeline's already-clean
 * numeric columns, which in this payload means "trustworthy, not merely
 * present" -- an imputed value doesn't get to define the sector benchmark
 * any more than it widens an ordinary percentile distribution). Shared by
 * p2_sector_exposure and p2_transition_affordability's crossCompanyCompute,
 * since both need the exact same sector intensity table Python builds once
 * and reuses for both of its own sub-scores. */
function buildSectorIntensityTable(companies: readonly Company[]): Map<string, number> {
  const sums = new Map<string, { emissions: number; revenue: number }>();
  for (const c of companies) {
    const scope1 = c.fields["scope1_tco2e"];
    const revenue = c.fields["revenue_usd"];
    if (!scope1 || !revenue) continue;
    if (!MEASURED_STATUSES.has(scope1.st) || !MEASURED_STATUSES.has(revenue.st)) continue;
    const e = coerceFieldValue(scope1.v);
    const r = coerceFieldValue(revenue.v);
    if (!Number.isFinite(e) || !Number.isFinite(r)) continue;
    const entry = sums.get(c.sector) ?? { emissions: 0, revenue: 0 };
    entry.emissions += e;
    entry.revenue += r;
    sums.set(c.sector, entry);
  }
  const intensity = new Map<string, number>();
  for (const [sector, { emissions, revenue }] of sums) {
    if (revenue > 0) intensity.set(sector, emissions / (revenue / 1e6));
  }
  // Sectors with zero GHGRP-measured companies (e.g. Financials, Info Tech)
  // get the lowest observed intensity's floor, matching
  // transition_score.py's own "give them the floor rather than no data"
  // fallback -- so every sector present in `companies` ends up with a value.
  const floor = intensity.size ? Math.min(...intensity.values()) : 0;
  for (const sector of new Set(companies.map((c) => c.sector))) {
    if (!intensity.has(sector)) intensity.set(sector, floor);
  }
  return intensity;
}

/** p2_sector_exposure's crossCompanyCompute: min-max normalizes
 * buildSectorIntensityTable's per-sector intensity across every sector
 * present, inverted so lower structural exposure -> higher score. Every
 * company in the same sector gets the identical value, by construction --
 * mirrors transition_score.py's sector_exposure_score exactly. */
function computeSectorExposure(companies: readonly Company[]): Map<string, number | null> {
  const intensity = buildSectorIntensityTable(companies);
  const values = [...intensity.values()];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const scoreBySector = new Map<string, number>();
  for (const [sector, v] of intensity) {
    scoreBySector.set(sector, hi === lo ? 100 : 100 * (1 - (v - lo) / (hi - lo)));
  }
  const out = new Map<string, number | null>();
  for (const c of companies) out.set(c.ticker, scoreBySector.get(c.sector) ?? null);
  return out;
}

/** Median (reduction fraction, target year) among each sector's
 * SBTi-quantified peers, with a global-median fallback for a sector with
 * none -- mirrors transition_score.py's _sector_counterfactual_target:
 * "no target still carries the liability, it just isn't acknowledged". */
function buildCounterfactualTargets(companies: readonly Company[]): {
  bySector: Map<string, { reductionPct: number; targetYear: number }>;
  global: { reductionPct: number; targetYear: number } | null;
} {
  const bySector = new Map<string, { reductions: number[]; years: number[] }>();
  const allReductions: number[] = [];
  const allYears: number[] = [];
  for (const c of companies) {
    const reductionRec = c.fields["target_reduction_pct"];
    const yearRec = c.fields["target_year"];
    if (!reductionRec || !yearRec) continue;
    if (!TRUSTED_STATUSES.has(reductionRec.st) || !TRUSTED_STATUSES.has(yearRec.st)) continue;
    const r = coerceFieldValue(reductionRec.v);
    const y = coerceFieldValue(yearRec.v);
    if (!Number.isFinite(r) || !Number.isFinite(y)) continue;
    const entry = bySector.get(c.sector) ?? { reductions: [], years: [] };
    entry.reductions.push(r);
    entry.years.push(y);
    bySector.set(c.sector, entry);
    allReductions.push(r);
    allYears.push(y);
  }
  const global = allReductions.length
    ? { reductionPct: median(allReductions)!, targetYear: median(allYears)! }
    : null;
  const out = new Map<string, { reductionPct: number; targetYear: number }>();
  for (const [sector, { reductions, years }] of bySector) {
    out.set(sector, { reductionPct: median(reductions)!, targetYear: median(years)! });
  }
  return { bySector: out, global };
}

/** p2_transition_affordability's crossCompanyCompute -- mirrors
 * transition_score.py's transition_affordability_score end to end: an
 * estimated-emissions figure (real scope1_tco2e when measured, else the
 * sector intensity benchmark x this company's own revenue -- the one place
 * in this registry that deliberately DOES use the modelled-tier fallback
 * p2_carbon_price_exposure deliberately does NOT, because Python's own
 * transition_affordability_score formula is defined in terms of
 * estimated_emissions_tco2e and matching it exactly requires the same
 * fallback), a target (disclosed, or a sector/global counterfactual median),
 * a sector abatement cost, and free cash flow. */
function computeTransitionAffordability(companies: readonly Company[]): Map<string, number | null> {
  const intensity = buildSectorIntensityTable(companies);
  const { bySector: counterfactualBySector, global: globalCounterfactual } = buildCounterfactualTargets(companies);

  const out = new Map<string, number | null>();
  for (const c of companies) {
    const scope1Rec = c.fields["scope1_tco2e"];
    const revenueRec = c.fields["revenue_usd"];
    const fcfRec = c.fields["free_cash_flow_usd"];

    let estimatedEmissions: number | null = null;
    if (revenueRec && TRUSTED_STATUSES.has(revenueRec.st)) {
      const revenue = coerceFieldValue(revenueRec.v);
      if (scope1Rec && TRUSTED_STATUSES.has(scope1Rec.st)) {
        const measured = coerceFieldValue(scope1Rec.v);
        if (Number.isFinite(measured)) estimatedEmissions = measured;
      }
      if (estimatedEmissions === null && Number.isFinite(revenue)) {
        const sectorIntensity = intensity.get(c.sector);
        if (sectorIntensity !== undefined) estimatedEmissions = sectorIntensity * (revenue / 1e6);
      }
    }

    const reductionRec = c.fields["target_reduction_pct"];
    const yearRec = c.fields["target_year"];
    let reductionFraction: number | null = null;
    let targetYear: number | null = null;
    if (reductionRec && yearRec && TRUSTED_STATUSES.has(reductionRec.st) && TRUSTED_STATUSES.has(yearRec.st)) {
      const r = coerceFieldValue(reductionRec.v);
      const y = coerceFieldValue(yearRec.v);
      if (Number.isFinite(r) && Number.isFinite(y)) {
        reductionFraction = r / 100;
        targetYear = y;
      }
    }
    if (reductionFraction === null || targetYear === null) {
      const fallback = counterfactualBySector.get(c.sector) ?? globalCounterfactual;
      if (fallback) {
        reductionFraction = fallback.reductionPct / 100;
        targetYear = fallback.targetYear;
      }
    }

    const fcf = fcfRec && TRUSTED_STATUSES.has(fcfRec.st) ? coerceFieldValue(fcfRec.v) : NaN;

    let rawValue: number | null = null;
    if (
      estimatedEmissions !== null &&
      reductionFraction !== null &&
      targetYear !== null &&
      Number.isFinite(fcf) &&
      fcf > 0
    ) {
      const yearsToTarget = Math.max(1, targetYear - CURRENT_YEAR);
      const abatementCost = SECTOR_ABATEMENT_COST_USD_PER_TCO2E[c.sector] ?? DEFAULT_ABATEMENT_COST_USD_PER_TCO2E;
      const reductionNeededTco2e = estimatedEmissions * reductionFraction;
      const annualizedCostUsd = (reductionNeededTco2e * abatementCost) / yearsToTarget;
      const pctFcfCommitted = (100 * annualizedCostUsd) / fcf;
      const clipped = Math.max(0, Math.min(pctFcfCommitted, AFFORDABILITY_COST_CEILING_PCT));
      rawValue = 100 * (1 - clipped / AFFORDABILITY_COST_CEILING_PCT);
    }
    out.set(c.ticker, rawValue);
  }
  return out;
}

export const REGISTRY: SubScoreDef[] = [
  // === P1 Environmental =====================================================
  {
    id: "p1_carbon_intensity",
    pillar: "P1",
    label: "Carbon intensity",
    polarity: "lower_is_better",
    inputs: ["scope1_tco2e", "revenue_usd"],
    // tCO2e per $M revenue -- Scope 2/3 aren't in the payload yet (see the
    // pillar spec note), so this reads Scope 1 only. Renamed to say so
    // wherever it's labelled in the UI, not just here.
    compute: (f) => (f.revenue_usd === 0 ? NaN : (f.scope1_tco2e / f.revenue_usd) * 1e6),
    scoringMode: "sector_percentile",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "How much Scope 1 (direct) carbon a company emits per dollar of revenue it makes, " +
      "compared to other companies in its sector. This only counts Scope 1 -- emissions " +
      "from sources the company directly owns or controls -- not Scope 2 (purchased " +
      "electricity) or Scope 3 (its supply chain and customers), which aren't in this " +
      "dataset. A company missing reported emissions or revenue is left out of this axis " +
      "rather than guessed at. Shown as a percentile: 0 = most carbon-intensive in its " +
      "sector, 100 = least.",
  },
  {
    id: "p1_energy_mix",
    pillar: "P1",
    label: "Grid carbon intensity",
    polarity: "lower_is_better",
    // Modelled on score_calculation/environmental/environmental_score.py's
    // _energy_mix_score. The spec's own fields (renewable/total electricity,
    // S10/S21) have never been pulled -- 0/500 real coverage -- so this is a
    // REGIONAL PROXY instead, from S19 (EPA eGRID): the carbon intensity of
    // the electricity grid where a company is headquartered. Every company
    // in the same US state shares the identical value, by construction --
    // coarser than the spec's own indicator would be, but a real published
    // government number, not a reconstruction of something else. ~475/500
    // covered; the rest are non-US-headquartered companies with no US grid
    // to map to.
    inputs: ["grid_intensity_kgco2e_per_mwh"],
    compute: (f) => f.grid_intensity_kgco2e_per_mwh,
    scoringMode: "sector_percentile",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "How dirty or clean the electricity grid is where a company is headquartered. " +
      "This is NOT something the company controls directly -- it's a government-published " +
      "regional stat (EPA eGRID), and every company headquartered in the same US state gets " +
      "the identical value, by construction. It stands in for the company's actual energy " +
      "mix, which this dataset doesn't have (0 of 500 companies have that measured " +
      "directly); ~475 of 500 are covered by the state-grid proxy, and non-US-headquartered " +
      "companies are excluded since there's no US grid to map them to. Shown as a " +
      "percentile: 0 = dirtiest grid in its sector, 100 = cleanest.",
  },
  {
    id: "p1_resource_waste",
    pillar: "P1",
    label: "Waste diverted from landfill",
    polarity: "higher_is_better",
    inputs: ["waste_diverted_pct"],
    compute: (f) => f.waste_diverted_pct,
    scoringMode: "sector_percentile",
    nullPolicy: "not_disclosed",
    // Matches environmental_score.py's PIPELINE_GAP_INDICATORS: the real
    // spec indicator here needs S16 (EPA TRI), S17 (EPA RSEI), or S26 (WRI
    // Aqueduct) -- none pulled. Confirmed 0/500 real coverage in the current
    // payload (payload.schema still lists waste_diverted_pct as a canonical
    // field, but no company has a trusted value for it), matching Python's
    // own unconditional-null _resource_waste_score exactly as-is. If this
    // field ever gains real coverage, the two will diverge and this comment
    // -- not just the gapKind -- needs revisiting.
    gapKind: "pipeline_gap",
    basis: "FY2023",
    description:
      "What share of a company's waste is diverted from landfill (recycled, composted, " +
      "reused) rather than dumped. The data source this indicator actually needs hasn't " +
      "been pulled into this dataset at all -- it's 0 of 500 companies, for every company, " +
      "not a per-company gap -- so this axis is empty right now, matching the underlying " +
      "model's own formula for this indicator (which also never produces a value). It " +
      "doesn't count against any company's disclosure-coverage penalty. Shown as a " +
      "percentile: 0 = lowest diversion rate in its sector, 100 = highest, whenever data " +
      "does exist.",
  },
  {
    id: "p1_input_efficiency",
    pillar: "P1",
    label: "Input efficiency",
    polarity: "lower_is_better", // orientation only -- see percentileComponents below, which each declare their own
    // Union of every component's inputs, for assertRegistryMatchesSchema and
    // DetailPanel display only -- gating happens per component (see
    // percentileComponents), not on this list, and `compute` below is never
    // called.
    inputs: ["cogs_usd", "revenue_usd", "energy_cost_usd"],
    compute: () => NaN, // unused -- see percentileComponents
    scoringMode: "absolute", // the blended result below is already a final 0-100 score
    // Modelled on environmental_score.py's _input_efficiency_score: TWO
    // independently-sector-percentiled components -- COGS/revenue and
    // energy-cost/revenue -- averaged over whichever exist (energy_cost_usd
    // is ~16/500 covered, so most companies are scored on COGS alone; that's
    // a narrower basis, not a penalty, same as governance_score.py's
    // mean-of-available-components pattern).
    percentileComponents: [
      {
        id: "cogs",
        inputs: ["cogs_usd", "revenue_usd"],
        polarity: "lower_is_better",
        compute: (f) => (f.revenue_usd === 0 ? NaN : (f.cogs_usd / f.revenue_usd) * 100),
      },
      {
        id: "energy_cost",
        inputs: ["energy_cost_usd", "revenue_usd"],
        polarity: "lower_is_better",
        compute: (f) => (f.revenue_usd === 0 ? NaN : (f.energy_cost_usd / f.revenue_usd) * 100),
      },
    ],
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "A proxy for how input-intensive a company's business is, blending two signals: cost " +
      "of goods sold as a share of revenue, and (when disclosed) energy cost as a share of " +
      "revenue. Each is independently ranked against sector peers on its own, then averaged " +
      "over whichever of the two a company actually has -- energy cost is only disclosed by " +
      "about 16 of 500 companies, so most companies are scored on the cost-of-goods signal " +
      "alone, which is a narrower basis, not a penalty. This is NOT a direct emissions or " +
      "efficiency measure -- read it as \"how much of every revenue dollar goes into " +
      "inputs,\" not as an environmental score on its own. The averaged result is already a " +
      "0-100 score (0 = most input-intensive in its sector, 100 = least) and isn't ranked " +
      "against peers a second time.",
  },

  // === P2 Transition =========================================================
  {
    id: "p2_carbon_price_exposure",
    pillar: "P2",
    label: "Carbon-price exposure",
    polarity: "higher_is_better",
    inputs: ["scope1_tco2e", "ebitda_usd"],
    // Ceiling-mapped, modelled on transition_score.py's _ceiling_score: an
    // assumed $100/ton carbon price (ASSUMED_CARBON_PRICE_USD_PER_TON) against
    // Scope 1 emissions, as a share of EBITDA, clipped to 0-50% erosion and
    // mapped so 0% erosion -> 100 (best) and >=50% erosion -> 0 (worst).
    // compute() already returns an oriented 0-100 value here -- scoringMode
    // 'absolute' below stops it from being percentile-ranked a second time.
    //
    // Two deliberate divergences from transition_score.py's
    // carbon_price_exposure_score:
    // 1. Scope 1 only, not Scope 1+2 -- matches what GHGRP actually
    //    publishes (facility-level Scope 1 combustion emissions; GHGRP
    //    doesn't report Scope 2) and matches Python's own
    //    estimated_emissions_tco2e, which is scope1_tco2e alone.
    //    scope2_location_tco2e has 0/500 real coverage in this pipeline --
    //    requiring it (as an earlier version of this sub-score did) made
    //    this whole sub-score permanently unavailable for every company,
    //    a real bug, not a design choice.
    // 2. NOT using transition_score.py's sector-benchmark fallback for
    //    non-reporters (estimated_emissions_tco2e's "modelled" tier) --
    //    that's the exact "reward silence" pattern this project exists to
    //    avoid. A company missing scope1_tco2e stays honestly excluded via
    //    nullPolicy below, same stance as p1_carbon_intensity. (Contrast
    //    p2_transition_affordability below, which DOES use the modelled
    //    tier -- Python's own formula for that one is defined in terms of
    //    estimated_emissions_tco2e, and matching it exactly requires the
    //    same fallback there.)
    compute: (f) => {
      if (f.ebitda_usd <= 0) return NaN; // <=0, not ===0: negative EBITDA
      const carbonCostUsd = f.scope1_tco2e * 100; // ASSUMED_CARBON_PRICE_USD_PER_TON
      const pctErosion = (carbonCostUsd * 100) / f.ebitda_usd;
      const clipped = Math.max(0, Math.min(50, pctErosion));
      return 100 * (1 - clipped / 50);
    },
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    // Matches transition_score.py's PIPELINE_GAP_INDICATORS: null here comes
    // from missing/non-positive EBITDA (a financial-statement pull gap) or a
    // missing scope1_tco2e, never a company choosing not to disclose.
    gapKind: "pipeline_gap",
    basis: "FY2023",
    description:
      "How exposed a company's profits are to a hypothetical carbon price, assuming " +
      "$100 per ton on its Scope 1 (direct) emissions only -- not Scope 2 or 3, since " +
      "Scope 1 is what's actually available here. The erosion of EBITDA that would cause " +
      "is capped at 50% (beyond that, more erosion no longer changes the score) and then " +
      "flipped so a low-exposure company scores highest. A company missing emissions or " +
      "EBITDA data is excluded rather than estimated from sector averages -- unlike some " +
      "other measures on this dataset, silence here is not filled in. This is already a " +
      "direct 0-100 score, not ranked against sector peers a second time -- 0 = most " +
      "exposed, 100 = least, comparable across every sector.",
  },
  {
    id: "p2_sector_exposure",
    pillar: "P2",
    label: "Sector carbon intensity",
    polarity: "higher_is_better", // crossCompanyCompute below already returns an oriented, final 0-100 value
    // Ingredients of the sector-level aggregate (see
    // computeSectorExposure/buildSectorIntensityTable above), listed here
    // for assertRegistryMatchesSchema/UI display only -- this sub-score
    // does NOT gate on this company's own scope1_tco2e/revenue_usd the way
    // a normal sub-score gates on `inputs`; a company with neither still
    // gets its sector's value, because the benchmark is built from OTHER
    // companies in the same sector, not this one.
    inputs: ["scope1_tco2e", "revenue_usd"],
    compute: () => NaN, // unused -- see crossCompanyCompute
    crossCompanyCompute: computeSectorExposure,
    scoringMode: "sector_normalized",
    nullPolicy: "not_disclosed",
    // A sector-level fact, never a company-specific disclosure choice --
    // matches transition_score.py's PIPELINE_GAP_INDICATORS.
    gapKind: "pipeline_gap",
    basis: "FY2023",
    description:
      "How carbon-intensive a company's SECTOR is, structurally -- not this company's own " +
      "emissions. It's built by pooling every company in the sector that has directly " +
      "measured Scope 1 emissions and revenue, taking the sector-wide total emissions per " +
      "dollar of revenue, then comparing that ONE number across all sectors. Every company " +
      "in the same sector gets the identical value, by construction, regardless of its own " +
      "individual performance -- this measures the sector you're in, not what you " +
      "personally do about it. A sector with zero measured companies is given the least-" +
      "intensive sector's own value as a floor, rather than being left blank. Not ranked " +
      "against sector peers (there's only one value per sector to rank): shown as a direct " +
      "0-100 score, min-max normalized across sectors -- 0 = most carbon-intensive sector, " +
      "100 = least.",
  },
  {
    id: "p2_regulatory_momentum",
    pillar: "P2",
    label: "Regulatory commitment",
    polarity: "higher_is_better",
    // Every input here is optional, on purpose -- see requiresAnyOf's own
    // doc comment for why this one deliberately has none: this mirrors
    // transition_score.py's documented caveat that _commitment_tier()
    // treats an unknown/undisclosed SBTi status identically to a disclosed
    // "no target" (both -> tier 0, never null), so regulatory_commitment_
    // score is never actually unavailable in Python, and shouldn't be here
    // either.
    inputs: [],
    optionalInputs: [
      { field: "sbti_target_validated", fillValue: 0 },
      { field: "sbti_target_type", fillValue: 0 },
      { field: "rnd_expense_usd", fillValue: NaN },
      { field: "revenue_usd", fillValue: NaN },
    ],
    // Modelled on transition_score.py's regulatory_commitment_score: an SBTi
    // ambition tier (no_target=0, committed=25, near_term_set=75,
    // net_zero_validated=100) blended 0.7/0.3 with an R&D-intensity signal
    // (capped at 15% of revenue) when R&D is disclosed, else the tier score
    // alone -- rnd_expense_usd/revenue_usd fill with NaN when absent
    // (Number.isFinite()-checked below) specifically so their absence SKIPS
    // the blend rather than scoring "spends nothing on R&D".
    compute: (f) => {
      const validated = f.sbti_target_validated === 1;
      const tierScore = validated ? SBTI_TIER_SCORE[f.sbti_target_type] ?? 0 : 0;
      const rndIntensityPct = f.revenue_usd > 0 ? (100 * f.rnd_expense_usd) / f.revenue_usd : NaN;
      if (!Number.isFinite(rndIntensityPct)) return tierScore;
      const rndScore = (100 * Math.max(0, Math.min(rndIntensityPct, RND_INTENSITY_CAP_PCT))) / RND_INTENSITY_CAP_PCT;
      return 0.7 * tierScore + 0.3 * rndScore;
    },
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    // Default (disclosure_gap), matching Python's own classification --
    // note Python's own caveat (see compute() above) that this is currently
    // a no-op, since this sub-score is never actually unavailable.
    basis: "FY2023",
    description:
      "How strong a company's stated emissions-reduction commitment is: an SBTi ambition " +
      "tier (no stated target = 0, a bare commitment = 25, a validated near-term target = " +
      "75, a validated net-zero target = 100), blended with an R&D-spending signal " +
      "(capped at 15% of revenue) when R&D is disclosed. A company with NO stated target " +
      "at all is not excluded from this axis -- it scores the \"no target\" tier (0) plus " +
      "whatever its R&D signal contributes, on the view that having no target is itself a " +
      "real, scoreable signal rather than missing data. Already a direct 0-100 score, not " +
      "ranked against sector peers: 0 = weakest commitment, 100 = strongest, comparable " +
      "across every sector.",
  },
  {
    id: "p2_transition_affordability",
    pillar: "P2",
    label: "Transition affordability",
    polarity: "higher_is_better", // crossCompanyCompute below already returns an oriented, final 0-100 value
    // Ingredients of the cross-company computation, for
    // assertRegistryMatchesSchema/UI display only -- see
    // computeTransitionAffordability's own doc comment.
    inputs: ["scope1_tco2e", "revenue_usd", "target_reduction_pct", "target_year", "free_cash_flow_usd"],
    compute: () => NaN, // unused -- see crossCompanyCompute
    crossCompanyCompute: computeTransitionAffordability,
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    // Null here comes from missing/non-positive free cash flow or an
    // unresolvable emissions estimate -- a financial-statement pull gap,
    // not a company's own disclosure choice. Matches transition_score.py's
    // PIPELINE_GAP_INDICATORS.
    gapKind: "pipeline_gap",
    basis: "FY2023",
    description:
      "Whether a company can plausibly afford to hit its own emissions-reduction target " +
      "(or, if it hasn't stated one, its sector's typical target) out of its free cash " +
      "flow, using an illustrative per-sector abatement cost estimate. Unlike most other " +
      "axes here, a company with no measured Scope 1 emissions is NOT excluded -- its " +
      "emissions are modelled from its sector's typical carbon intensity times its own " +
      "revenue, and a company with no stated target is scored against its sector's (or, " +
      "failing that, the whole index's) median target instead. It IS excluded when free " +
      "cash flow itself is missing or negative, since the underlying math needs a positive " +
      "number to divide by. Already a direct 0-100 score, not ranked against sector peers: " +
      "0 = least affordable, 100 = most, comparable across every sector.",
  },

  // === P3 Governance ==========================================================
  {
    id: "p3_board_independence",
    pillar: "P3",
    label: "Board independence",
    polarity: "higher_is_better",
    // governance_score.py's _board_independence_score blends this ratio with
    // whether a lead independent director is named (lead_independent_director,
    // 495/500 covered vs the ratio's 135/500) -- both entirely optional, so
    // requiresAnyOf below is what stops "neither disclosed" from being
    // misread as "measured, score 0".
    inputs: [],
    optionalInputs: [
      { field: "independent_director_count", fillValue: NaN },
      { field: "board_size", fillValue: NaN },
      { field: "lead_independent_director", fillValue: NaN },
    ],
    requiresAnyOf: ["independent_director_count", "board_size", "lead_independent_director"],
    compute: (f) => {
      const ratioComponent = f.board_size > 0 ? pct(f.independent_director_count, f.board_size) : NaN;
      const leadComponent = Number.isFinite(f.lead_independent_director) ? f.lead_independent_director * 100 : NaN;
      const components = [ratioComponent, leadComponent].filter((x) => Number.isFinite(x));
      if (components.length === 0) return NaN;
      return components.reduce((a, b) => a + b, 0) / components.length;
    },
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "How independent a company's board is, blending two signals when available: the " +
      "share of directors who are independent, and whether the company names a lead " +
      "independent director (a governance role that offsets a combined chair/CEO). Only " +
      "about 135 of 500 companies disclose enough detail to compute the ratio directly, " +
      "while about 495 of 500 disclose the lead-director flag -- a company is scored on " +
      "the mean of whichever of the two it actually discloses, and excluded only when it " +
      "discloses NEITHER. Already a direct 0-100 score, not ranked against sector peers: " +
      "0 = least independent, 100 = most, comparable across every sector.",
  },
  {
    id: "p3_exec_compensation",
    pillar: "P3",
    label: "Compensation alignment",
    polarity: "higher_is_better",
    inputs: ["has_clawback_policy", "has_psu_plan", "performance_period_years"],
    // Modelled on governance_score.py's _compensation_alignment_score: mean
    // of the two booleans and the LTI performance period, capped at 3 years
    // (longer periods reward long-term thinking; 3+ years is already a
    // strong signal, more isn't better). Replaces comp_tied_to_emissions_target,
    // which is in the pillar spec's four booleans but S04 doesn't actually
    // emit it -- 0/500, structurally, not a temporary gap -- so requiring it
    // made this sub-score permanently unavailable for the whole universe, a
    // real bug rather than an honest data gap. Relabelled from "Climate-linked
    // pay design" to "Compensation alignment" since none of its three real
    // components are climate-specific -- this measures general pay-governance
    // structure, and the label should say so honestly.
    compute: (f) => {
      const performanceComponent = (Math.min(f.performance_period_years, 3) / 3) * 100;
      return (f.has_clawback_policy * 100 + f.has_psu_plan * 100 + performanceComponent) / 3;
    },
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "How well executive pay structure is set up to reward long-term performance: an " +
      "even mix of whether the company has a clawback policy (can claw back bonuses after " +
      "misconduct or a restatement), whether it uses performance-based stock units, and " +
      "how long the performance measurement period is (capped at 3+ years, since longer " +
      "isn't scored as better beyond that). This is a general pay-governance structure " +
      "measure, not specifically about climate or sustainability -- none of its three " +
      "components tie executive pay to emissions or ESG targets. Already a direct 0-100 " +
      "score, not ranked against sector peers: 0 = weakest pay alignment, 100 = strongest, " +
      "comparable across every sector.",
  },
  {
    id: "p3_climate_governance",
    pillar: "P3",
    label: "Climate governance",
    polarity: "higher_is_better",
    // Modelled on governance_score.py's _climate_governance_score: mean of
    // whichever of the 3 available booleans a company has (S04 doesn't emit
    // comp_tied_to_emissions_target, the spec's fourth boolean, at all --
    // structurally missing, not a gap). Coverage of each is low (~45-60/500
    // -- a low-recall extraction rule), so requiresAnyOf below is what
    // distinguishes "none of the three resolved" from "measured, score 0".
    inputs: [],
    optionalInputs: [
      { field: "has_climate_oversight_committee", fillValue: NaN },
      { field: "has_third_party_assurance", fillValue: NaN },
      { field: "emissions_boundary_stated", fillValue: NaN },
    ],
    requiresAnyOf: ["has_climate_oversight_committee", "has_third_party_assurance", "emissions_boundary_stated"],
    compute: (f) => {
      const components = [f.has_climate_oversight_committee, f.has_third_party_assurance, f.emissions_boundary_stated]
        .filter((x) => Number.isFinite(x));
      if (components.length === 0) return NaN;
      return (components.reduce((a, b) => a + b, 0) / components.length) * 100;
    },
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "How formally a company governs its own climate disclosures: the mean of up to three " +
      "yes/no signals -- whether it has a board-level climate oversight committee, whether " +
      "its emissions data has third-party assurance, and whether it clearly states the " +
      "boundary/scope of what it's reporting. Each of the three is thinly and independently " +
      "disclosed (roughly 45-60 of 500 companies per signal, extracted from filings text), " +
      "so a company is scored on the mean of whichever signals it actually discloses, and " +
      "excluded only when it discloses NONE of the three. Already a direct 0-100 score, not " +
      "ranked against sector peers: 0 = weakest climate governance, 100 = strongest, " +
      "comparable across every sector.",
  },
  {
    id: "p3_controversy_flags",
    pillar: "P3",
    label: "Penalty record",
    polarity: "lower_is_better",
    inputs: ["penalty_total_usd"],
    // Modelled on governance_score.py's _controversy_score: a dollar total
    // of EPA ECHO penalties, not a raw count -- the spec's own note is that
    // penalty COUNT correlates with facility count and should really be
    // normalised per facility, which this pipeline doesn't have a reliable
    // figure for either; a dollar total is at least an absolute magnitude,
    // not an artifact of how many facilities happen to file separately.
    // Ranked UNIVERSE-WIDE (scoringMode below), matching Python exactly:
    // most companies genuinely have $0 in penalties, and that tie shouldn't
    // be split arbitrarily by sector.
    compute: (f) => f.penalty_total_usd,
    scoringMode: "universe_percentile",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "Total dollar value of EPA enforcement penalties on record for the company. This is a " +
      "TOTAL, not normalized per facility -- a large single-site company and a large multi-" +
      "site company with the same total penalty amount look identical here, even though the " +
      "multi-site one may actually have a better per-facility record. Data coverage is thin: " +
      "penalty records exist for very few of the 500 companies, so most companies show as " +
      "not disclosed rather than as having a clean record. Unlike every other axis on this " +
      "map, this one is ranked against every company in the INDEX, not just sector peers -- " +
      "most companies genuinely have $0 in penalties, and that tie shouldn't be split " +
      "arbitrarily by sector. Shown as a percentile: 0 = highest total penalties " +
      "index-wide, 100 = lowest (including $0).",
  },
  {
    id: "p3_capital_stewardship",
    pillar: "P3",
    label: "Capital stewardship",
    polarity: "higher_is_better",
    // capex_usd is the one REQUIRED input -- its absence is a real data gap.
    // Modelled on governance_score.py's _capital_stewardship_score, which
    // treats rnd/buybacks/dividends absence differently: those XBRL tags
    // are optional, so a company that simply doesn't emit them gets a true
    // zero there, not an excluded sub-score. optionalInputs is what lets
    // this registry express that asymmetry without collapsing coverage to
    // the intersection of four independently-thin fields.
    inputs: ["capex_usd"],
    optionalInputs: [
      { field: "rnd_expense_usd", fillValue: 0 },
      { field: "buybacks_usd", fillValue: 0 },
      { field: "dividends_paid_usd", fillValue: 0 },
    ],
    compute: (f) => {
      const reinvestment = f.capex_usd + f.rnd_expense_usd;
      const total = reinvestment + f.buybacks_usd + f.dividends_paid_usd;
      return total <= 0 ? NaN : (reinvestment / total) * 100;
    },
    scoringMode: "absolute",
    nullPolicy: "not_disclosed",
    basis: "FY2023",
    description:
      "What share of a company's capital allocation goes toward reinvestment (capital " +
      "expenditure plus R&D) rather than shareholder returns (buybacks and dividends). A " +
      "higher share reads as more long-term-oriented capital stewardship; a company that " +
      "returns most of its capital to shareholders scores lower here regardless of whether " +
      "that's a sound strategy for its business. Capex is required data -- its absence is a " +
      "real disclosure gap -- but R&D, buybacks, and dividends are each zero-filled when a " +
      "company simply doesn't report them, rather than excluding the company outright. " +
      "Already a direct 0-100 score, not ranked against sector peers: 0 = lowest " +
      "reinvestment share, 100 = highest, comparable across every sector.",
  },
];

export function registryForPillar(pillar: Pillar): SubScoreDef[] {
  return REGISTRY.filter((s) => s.pillar === pillar);
}

export function subScoreById(id: string): SubScoreDef {
  const s = REGISTRY.find((r) => r.id === id);
  if (!s) throw new Error(`unknown sub-score id ${JSON.stringify(id)}`);
  return s;
}

/**
 * Boot-time contract check. Every registry input must exist in the payload's
 * own field vocabulary (payload.schema, which mirrors fields.py in full --
 * it lists the whole 59-field vocabulary regardless of which fields any
 * company actually has data for). A field missing here means someone
 * renamed or dropped it upstream without telling the frontend: fail loudly,
 * by name, rather than silently rendering an empty axis that looks like a
 * data problem instead of a code problem.
 */
export function assertRegistryMatchesSchema(schema: Record<string, unknown>): void {
  const missing: string[] = [];
  const forbidden: string[] = [];
  for (const sub of REGISTRY) {
    const fields = [...sub.inputs, ...(sub.optionalInputs ?? []).map((o) => o.field)];
    for (const field of fields) {
      if (!(field in schema)) missing.push(`${sub.id} -> ${field}`);
      if (VALIDATION_ONLY_FIELDS.has(field)) forbidden.push(`${sub.id} -> ${field}`);
    }
  }
  if (missing.length) {
    throw new Error(
      `Registry/schema mismatch: field(s) not in payload.schema -- ` +
        `renamed or removed upstream? ${missing.join(", ")}`
    );
  }
  if (forbidden.length) {
    throw new Error(
      `Registry uses a VALIDATION_ONLY field, which must never enter a ` +
        `pillar score: ${forbidden.join(", ")}`
    );
  }
}
