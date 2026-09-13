// raw fields -> compute() -> sector percentile (polarity-adjusted) -> sub-score
//            -> weighted mean per pillar -> pillar score -> weighted mean -> composite
//
// Every step here is a pure function of (companies, weights). No fetch, no
// DOM, no randomness (rankSensitivity.ts is the one exception, and it takes
// an explicit seed for that reason). That purity is what makes it safe to
// call synchronously from a memoised selector on every slider tick.
//
// Three sub-scores don't fit the "compute one raw value, then rank it"
// shape above, and each gets its own dedicated handling below rather than
// forcing a generic compute()/percentileRank contract to cover cases it
// can't express:
//   - p1_input_efficiency (SubScoreDef.percentileComponents): the skip-null
//     MEAN of two independently sector-percentiled metrics.
//   - p2_sector_exposure, p2_transition_affordability
//     (SubScoreDef.crossCompanyCompute): a raw value that depends on more
//     than one company's own fields (a sector-level benchmark, a
//     counterfactual median) -- computed once per computeScores() call over
//     the whole company list, not per company.
// See registry.ts's own doc comments on those two fields for why.

import { coerceFieldValue, MEASURED_STATUSES, TRUSTED_STATUSES, type Company } from "./types";
import { median, percentileRank, universeRankPercentile, weightedMeanSkippingNulls } from "./percentile";
import {
  PYTHON_P2_WEIGHTS,
  PYTHON_P3_WEIGHTS,
  REGISTRY,
  SBTI_TARGET_TYPE_CODES,
  type GapKind,
  type OptionalInput,
  type Pillar,
  type RawInputs,
  type SubScoreDef,
} from "./registry";

// Re-exported so callers of defaultWeights() don't need a second import from
// registry.ts just to see what it used.
export { PYTHON_P2_WEIGHTS, PYTHON_P3_WEIGHTS };

export const PILLARS: Pillar[] = ["P1", "P2", "P3"];

export interface WeightsState {
  /** Raw (not necessarily normalised) pillar weights. Missing pillar = 1. */
  pillars: Partial<Record<Pillar, number>>;
  /** Raw sub-score weights, keyed by sub-score id, scoped within their
   * pillar. Missing sub-score id = 1 (equal weight among what's present). */
  subscores: Partial<Record<string, number>>;
}

/** Default (pre-slider) sub-score weights: P1 stays flat/equal here (true
 * per-sector, materiality-derived P1 weights need a sector to compute at
 * all -- see weights.ts's pythonDefaultWeights, which is what the app
 * actually defaults to once materiality.json has loaded). P2/P3 use
 * Python's own fixed WEIGHTS dicts even in this flat/manual form, since
 * those are NOT sector-varying in Python either. */
export function defaultWeights(): WeightsState {
  const pillars: Partial<Record<Pillar, number>> = { P1: 1, P2: 1, P3: 1 };
  const subscores: Partial<Record<string, number>> = {};
  for (const s of REGISTRY) {
    subscores[s.id] = PYTHON_P2_WEIGHTS[s.id] ?? PYTHON_P3_WEIGHTS[s.id] ?? 1;
  }
  return { pillars, subscores };
}

/** Weights normalised to sum to 1, for display next to a slider. Pillars and
 * sub-scores are normalised independently within their own scope. `registry`
 * defaults to the real REGISTRY; tests pass a synthetic one so nullPolicy
 * branches ('zero', 'sector_median') are reachable without touching the
 * production sub-score list. */
export function normalizedWeights(
  weights: WeightsState,
  registry: SubScoreDef[] = REGISTRY
): {
  pillars: Record<Pillar, number>;
  subscores: Record<string, number>;
} {
  const pillarVals = PILLARS.map((p) => Math.max(0, weights.pillars[p] ?? 1));
  const pillarSum = pillarVals.reduce((a, b) => a + b, 0) || 1;
  const pillars = Object.fromEntries(
    PILLARS.map((p, i) => [p, pillarVals[i] / pillarSum])
  ) as Record<Pillar, number>;

  const subscores: Record<string, number> = {};
  for (const pillar of PILLARS) {
    const ids = registry.filter((s) => s.pillar === pillar).map((s) => s.id);
    const vals = ids.map((id) => Math.max(0, weights.subscores[id] ?? 1));
    const sum = vals.reduce((a, b) => a + b, 0) || 1;
    ids.forEach((id, i) => (subscores[id] = vals[i] / sum));
  }
  return { pillars, subscores };
}

/** Resolves the weights to use for one company's sector. A bare WeightsState
 * applies to every sector alike (today's only real caller); a Map is one
 * per-sector WeightsState (materiality-weighted mode) -- a sector absent
 * from the map falls back to equal weighting rather than silently scoring
 * with nothing. */
export function weightsForSector(
  weights: WeightsState | Map<string, WeightsState>,
  sector: string
): WeightsState {
  return weights instanceof Map ? weights.get(sector) ?? defaultWeights() : weights;
}

export type StatusClass = "measured" | "imputed" | "unavailable";

/** sbti_target_type arrives as a category string, not a number --
 * coerceFieldValue (shared, numeric-only) returns NaN for it; this layers
 * registry.ts's small SBTI_TARGET_TYPE_CODES lookup on top for exactly that
 * one field, so RawInputs stays numeric everywhere else. */
function coerce(v: number | string | boolean | undefined): number {
  const n = coerceFieldValue(v);
  if (Number.isFinite(n)) return n;
  return typeof v === "string" ? SBTI_TARGET_TYPE_CODES[v] ?? NaN : NaN;
}

/** Resolves one set of fields (either a sub-score's own `inputs`, or a
 * PercentileComponent's `inputs`) off one company: `required` gates
 * availability (any missing/untrusted field makes the whole set
 * 'unavailable'), `optional` never does (an absent optional field is
 * substituted with its own fillValue, and its presence/absence is reported
 * separately via `anyOptionalPresent` for requiresAnyOf to use). Shared by
 * resolveInputs (below) and resolveAndBuildDistributions's
 * percentileComponents handling, so there's exactly one field-resolution
 * rule in the codebase regardless of which of the two calls it. */
function resolveFieldSet(
  company: Company,
  required: readonly string[],
  optional: readonly OptionalInput[]
): { worst: StatusClass; inputs: RawInputs; anyOptionalPresent: boolean } {
  let worst: StatusClass = "measured";
  const inputs: RawInputs = {};
  for (const field of required) {
    const rec = company.fields[field];
    if (!rec || !TRUSTED_STATUSES.has(rec.st)) {
      worst = "unavailable";
      continue;
    }
    if (!MEASURED_STATUSES.has(rec.st) && worst !== "unavailable") worst = "imputed";
    inputs[field] = coerce(rec.v);
  }
  let anyOptionalPresent = false;
  for (const opt of optional) {
    const rec = company.fields[opt.field];
    const present = !!rec && TRUSTED_STATUSES.has(rec.st);
    if (present) anyOptionalPresent = true;
    inputs[opt.field] = present ? coerce(rec!.v) : opt.fillValue;
  }
  return { worst, inputs, anyOptionalPresent };
}

/** Reads a sub-score's inputs off one company. Never invents a value: an
 * input that is not_disclosed, quote_failed, or simply absent from the
 * company's fields makes the whole sub-score 'unavailable' for that company,
 * regardless of whether other inputs happen to be present. */
export function resolveInputs(
  company: Company,
  sub: SubScoreDef
): { statusClass: StatusClass; inputs: RawInputs | null } {
  const { worst, inputs, anyOptionalPresent } = resolveFieldSet(company, sub.inputs, sub.optionalInputs ?? []);

  if (worst === "unavailable") {
    if (sub.nullPolicy !== "zero") return { statusClass: "unavailable", inputs: null };
    // 'zero': a missing required input is filled with a literal 0 (e.g. "no
    // penalty records found" reads the same as "zero penalties"), but the
    // point still renders hollow -- the data really is missing, only the
    // maths treats it as a true zero rather than refusing to compute.
    for (const field of sub.inputs) {
      if (!(field in inputs)) inputs[field] = 0;
    }
    return { statusClass: "unavailable", inputs };
  }

  // A sub-score with no required `inputs` at all (only ever-optional
  // components) would otherwise always read "measured" here, even when
  // literally none of its optionalInputs resolved -- requiresAnyOf is the
  // opt-in fix, only set where Python's own formula can truly go null this
  // way. See registry.ts's doc comment on requiresAnyOf.
  if (sub.requiresAnyOf && sub.inputs.length === 0 && !anyOptionalPresent) {
    return { statusClass: "unavailable", inputs: null };
  }

  return { statusClass: worst, inputs };
}

export interface SubScoreResult {
  id: string;
  statusClass: StatusClass;
  rawValue: number | null;
  /** 0-100, already polarity-adjusted so 100 is always "best". */
  score: number | null;
  /** Size of the distribution this was ranked against -- an axis reading
   * "0 / 41 companies" is a finding, and this is where it comes from. */
  coverageN: number;
}

export interface PillarResult {
  pillar: Pillar;
  /** Final score after the disclosure-coverage penalty below. */
  score: number | null;
  /** Pre-penalty weighted mean of available sub-scores -- kept for
   * auditability, matching score_calculation's own *_score_raw columns. */
  scoreRaw: number | null;
  /** 1.0 when every disclosure-gap sub-score in this pillar is present,
   * scaling down toward 0 as more of them are missing. Sub-scores tagged
   * 'pipeline_gap' are excluded from this ratio -- their absence isn't the
   * company's fault, so it isn't penalised (see GapKind in registry.ts). */
  disclosureCoverage: number;
  subScores: SubScoreResult[];
}

/** Floor/slope for the disclosure-coverage penalty below -- mirrors
 * score_calculation's DISCLOSURE_COVERAGE_FLOOR/_SLOPE exactly (every
 * pillar file there uses these same two constants). */
export const DISCLOSURE_COVERAGE_FLOOR = 0.6;
export const DISCLOSURE_COVERAGE_SLOPE = 0.4;

export interface AggregationEntry {
  id: string;
  /** The entry's own 0-100 score, or null if unavailable. */
  value: number | null;
  weight: number;
  /** Whether this entry counts as "disclosed" for coverage purposes --
   * independent of whether a nullPolicy substitution (e.g. 'sector_median')
   * produced a stand-in `value` anyway. A substituted stand-in is not real
   * disclosure. */
  disclosed: boolean;
  gapKind?: GapKind;
}

/**
 * Combines a pillar's sub-scores (or, in referenceColor.ts, a reference
 * point's pillar-level values) into one score, applying score_calculation's
 * disclosure-coverage penalty on top of the plain renormalized weighted
 * mean: `pillarScoreRaw` already renormalizes around whatever is missing for
 * free, which by itself rewards under-disclosure exactly as much as full
 * disclosure whenever the few present entries happen to score well.
 *
 *     score = scoreRaw * (DISCLOSURE_COVERAGE_FLOOR + DISCLOSURE_COVERAGE_SLOPE * disclosureCoverage)
 *
 * disclosureCoverage is the weight-share of disclosure-gap entries that are
 * actually present, so 1.0 when every one of them is, floor at 0.6 as more
 * go missing. Entries tagged 'pipeline_gap' (a data source not pulled for
 * the whole universe) are excluded from that ratio entirely.
 *
 * Deliberately NOT applied a second time across pillars into the composite
 * (matching final_score.py, which is a plain renormalized average of the
 * three already-penalized pillar scores) -- callers must use
 * weightedMeanSkippingNulls directly for that step, not this function.
 */
export function aggregateWithDisclosurePenalty(
  entries: readonly AggregationEntry[]
): { score: number | null; scoreRaw: number | null; disclosureCoverage: number } {
  const scoreRaw = weightedMeanSkippingNulls(entries.map((e) => ({ value: e.value, weight: e.weight })));

  let coverageWeightTotal = 0;
  let coverageWeightPresent = 0;
  for (const e of entries) {
    if (e.gapKind === "pipeline_gap") continue;
    coverageWeightTotal += e.weight;
    if (e.disclosed) coverageWeightPresent += e.weight;
  }
  const disclosureCoverage = coverageWeightTotal > 0 ? coverageWeightPresent / coverageWeightTotal : 1;

  const score =
    scoreRaw === null ? null : scoreRaw * (DISCLOSURE_COVERAGE_FLOOR + DISCLOSURE_COVERAGE_SLOPE * disclosureCoverage);
  return { score, scoreRaw, disclosureCoverage };
}

export interface CompanyScoreResult {
  ticker: string;
  sector: string;
  pillars: Record<Pillar, PillarResult>;
  composite: number | null;
}

export type ResolvedInputs = Map<string, Map<string, { statusClass: StatusClass; inputs: RawInputs | null }>>;
/** sector -> sub-score id (or, for a percentileComponents sub-score,
 * `${subId}::${componentId}`) -> sorted-ascending list of MEASURED-only raw
 * values. */
export type SectorDistributions = Map<string, Map<string, number[]>>;

/**
 * Pass 1 of the pipeline, exposed on its own so reference.ts can rank a
 * reference point (sector median, sector best, a named company's own value)
 * against the exact same distribution the scores themselves use. There must
 * be only one distribution-builder and one percentile function in this
 * codebase -- a second implementation is how the map ends up contradicting
 * the table.
 *
 * `crossCompanyRaw` (sub-score id -> ticker -> raw value) is exposed
 * alongside `resolved`/`distributions` for computeScores' own convenience --
 * a crossCompanyCompute sub-score's `resolved` entry never carries `inputs`
 * (there's nothing to hand to a per-company `compute()`, since the value
 * was computed once for every company already), so the raw number itself
 * has to be looked up here instead.
 */
export function resolveAndBuildDistributions(
  companies: readonly Company[],
  registry: SubScoreDef[] = REGISTRY
): { resolved: ResolvedInputs; distributions: SectorDistributions; crossCompanyRaw: Map<string, Map<string, number | null>> } {
  const resolved: ResolvedInputs = new Map();
  const distributions: SectorDistributions = new Map();
  for (const c of companies) {
    resolved.set(c.ticker, new Map());
    if (!distributions.has(c.sector)) distributions.set(c.sector, new Map());
  }

  function pushDistribution(sector: string, key: string, value: number) {
    const subDist = distributions.get(sector)!;
    const arr = subDist.get(key);
    if (arr) arr.push(value);
    else subDist.set(key, [value]);
  }

  const crossCompanyRaw = new Map<string, Map<string, number | null>>();

  for (const sub of registry) {
    if (sub.crossCompanyCompute) {
      const raw = sub.crossCompanyCompute(companies);
      crossCompanyRaw.set(sub.id, raw);
      for (const company of companies) {
        const v = raw.get(company.ticker) ?? null;
        resolved.get(company.ticker)!.set(sub.id, { statusClass: v !== null ? "measured" : "unavailable", inputs: null });
        if (v !== null) pushDistribution(company.sector, sub.id, v);
      }
      continue;
    }

    if (sub.percentileComponents) {
      for (const company of companies) {
        for (const comp of sub.percentileComponents) {
          const key = `${sub.id}::${comp.id}`;
          const { worst, inputs } = resolveFieldSet(company, comp.inputs, []);
          resolved.get(company.ticker)!.set(key, worst === "unavailable" ? { statusClass: worst, inputs: null } : { statusClass: worst, inputs });
          if (worst === "measured") {
            const v = comp.compute(inputs);
            if (Number.isFinite(v)) pushDistribution(company.sector, key, v);
          }
        }
      }
      continue;
    }

    for (const company of companies) {
      const r = resolveInputs(company, sub);
      resolved.get(company.ticker)!.set(sub.id, r);
      if (r.statusClass === "measured" && r.inputs) {
        const rawValue = sub.compute(r.inputs);
        if (Number.isFinite(rawValue)) pushDistribution(company.sector, sub.id, rawValue);
      }
    }
  }

  for (const subDist of distributions.values()) {
    for (const [id, values] of subDist) subDist.set(id, values.sort((a, b) => a - b));
  }
  return { resolved, distributions, crossCompanyRaw };
}

/**
 * Scores every company in `companies` against sector peers drawn from that
 * same array. Callers should generally pass the FULL loaded universe here,
 * not a sector-filtered subset: a company's percentile is a property of its
 * sector, and should not shift just because a viewer hid an unrelated
 * sector from the 3D view. Sector filtering is a display concern (see
 * state/useMatrix.ts); this function is not the place to fold it in.
 *
 * `weights` is either one WeightsState applied to every company (today's
 * manual/preset sliders), or a per-sector Map (materiality-weighted mode --
 * each sector scores its own companies by its own importance weights, while
 * every company is still percentile-ranked against the exact same
 * sector-scoped distribution either way; only the AGGREGATION step differs).
 * The bare-WeightsState path normalises weights exactly once, identically to
 * before this Map support existed; the Map path normalises once per distinct
 * sector actually present (at most 11), cached, never per company.
 */
export function computeScores(
  companies: readonly Company[],
  weights: WeightsState | Map<string, WeightsState>,
  registry: SubScoreDef[] = REGISTRY
): Map<string, CompanyScoreResult> {
  const bareNormalized = weights instanceof Map ? null : normalizedWeights(weights, registry);
  const normalizedCache = new Map<string, ReturnType<typeof normalizedWeights>>();
  function normalizedFor(sector: string) {
    if (bareNormalized) return bareNormalized;
    let n = normalizedCache.get(sector);
    if (!n) {
      n = normalizedWeights(weightsForSector(weights, sector), registry);
      normalizedCache.set(sector, n);
    }
    return n;
  }

  const { resolved, distributions, crossCompanyRaw } = resolveAndBuildDistributions(companies, registry);

  // Built once per call (not per company): a flat, universe-wide,
  // MEASURED-only distribution for every 'universe_percentile' sub-score,
  // by merging that sub-score's per-sector distributions -- those already
  // contain exactly the measured-tier values this needs, just partitioned
  // by sector. Matches governance_score.py's universe-wide controversy rank.
  const universeDistributions = new Map<string, number[]>();
  for (const sub of registry) {
    if ((sub.scoringMode ?? "sector_percentile") !== "universe_percentile") continue;
    const merged: number[] = [];
    for (const subDist of distributions.values()) {
      const v = subDist.get(sub.id);
      if (v) merged.push(...v);
    }
    universeDistributions.set(sub.id, merged.sort((a, b) => a - b));
  }

  // Pass 2: percentile + aggregate.
  const out = new Map<string, CompanyScoreResult>();
  for (const company of companies) {
    const perCompany = resolved.get(company.ticker)!;
    const subDist = distributions.get(company.sector) ?? new Map();
    const { pillars: pillarW, subscores: subW } = normalizedFor(company.sector);
    const pillarResults = {} as Record<Pillar, PillarResult>;

    for (const pillar of PILLARS) {
      const subs = registry.filter((s) => s.pillar === pillar);
      const subResults: SubScoreResult[] = subs.map((sub) => computeSubScore(sub, company, perCompany, subDist, universeDistributions, crossCompanyRaw));

      const { score, scoreRaw, disclosureCoverage } = aggregateWithDisclosurePenalty(
        subResults.map((r) => {
          const sub = subs.find((s) => s.id === r.id)!;
          return {
            id: r.id,
            value: r.score,
            weight: subW[r.id] ?? 1,
            disclosed: r.statusClass !== "unavailable",
            gapKind: sub.gapKind,
          };
        })
      );
      pillarResults[pillar] = { pillar, score, scoreRaw, disclosureCoverage, subScores: subResults };
    }

    const composite = weightedMeanSkippingNulls(
      PILLARS.map((p) => ({ value: pillarResults[p].score, weight: pillarW[p] }))
    );

    out.set(company.ticker, { ticker: company.ticker, sector: company.sector, pillars: pillarResults, composite });
  }

  return out;
}

/** One sub-score's SubScoreResult for one company, dispatching on which of
 * the three computation shapes it declared (percentileComponents,
 * crossCompanyCompute, or the default compute()+scoringMode path). */
function computeSubScore(
  sub: SubScoreDef,
  company: Company,
  perCompany: Map<string, { statusClass: StatusClass; inputs: RawInputs | null }>,
  subDist: Map<string, number[]>,
  universeDistributions: Map<string, number[]>,
  crossCompanyRaw: Map<string, Map<string, number | null>>
): SubScoreResult {
  if (sub.percentileComponents) {
    const componentScores: number[] = [];
    let anyMeasured = false;
    let coverageN = 0;
    for (const comp of sub.percentileComponents) {
      const key = `${sub.id}::${comp.id}`;
      const r = perCompany.get(key);
      const compDistribution = subDist.get(key) ?? [];
      if (compDistribution.length > coverageN) coverageN = compDistribution.length;
      if (r && r.statusClass !== "unavailable" && r.inputs) {
        const v = comp.compute(r.inputs);
        if (Number.isFinite(v)) {
          const s = percentileRank(v, compDistribution, comp.polarity);
          if (s !== null) {
            componentScores.push(s);
            if (r.statusClass === "measured") anyMeasured = true;
          }
        }
      }
    }
    const score = componentScores.length ? componentScores.reduce((a, b) => a + b, 0) / componentScores.length : null;
    return {
      id: sub.id,
      statusClass: score === null ? "unavailable" : anyMeasured ? "measured" : "imputed",
      rawValue: null, // no single meaningful raw value -- see PercentileComponent's doc comment
      score,
      coverageN,
    };
  }

  if (sub.crossCompanyCompute) {
    const r = perCompany.get(sub.id)!;
    const rawValue = r.statusClass !== "unavailable" ? crossCompanyRaw.get(sub.id)?.get(company.ticker) ?? null : null;
    return { id: sub.id, statusClass: r.statusClass, rawValue, score: rawValue, coverageN: (subDist.get(sub.id) ?? []).length };
  }

  const scoringMode = sub.scoringMode ?? "sector_percentile";
  const r = perCompany.get(sub.id)!;
  const distribution = subDist.get(sub.id) ?? [];
  let rawValue: number | null = null;

  if (r.statusClass !== "unavailable" && r.inputs) {
    const v = sub.compute(r.inputs);
    rawValue = Number.isFinite(v) ? v : null;
  } else if (r.statusClass === "unavailable" && sub.nullPolicy === "zero" && r.inputs) {
    const v = sub.compute(r.inputs);
    rawValue = Number.isFinite(v) ? v : null;
  } else if (r.statusClass === "unavailable" && sub.nullPolicy === "sector_median") {
    rawValue = median(distribution);
  }
  // nullPolicy 'not_disclosed' (the default): rawValue stays null.

  const isUniverseRanked = scoringMode === "universe_percentile";
  const rankingDistribution = isUniverseRanked ? universeDistributions.get(sub.id) ?? [] : distribution;

  let score: number | null;
  if (rawValue === null) score = null;
  else if (scoringMode === "absolute" || scoringMode === "sector_normalized") score = rawValue;
  else if (scoringMode === "universe_percentile") score = universeRankPercentile(rawValue, rankingDistribution, sub.polarity);
  else score = percentileRank(rawValue, rankingDistribution, sub.polarity);

  return { id: sub.id, statusClass: r.statusClass, rawValue, score, coverageN: rankingDistribution.length };
}
