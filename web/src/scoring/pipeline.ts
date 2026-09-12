// raw fields -> compute() -> sector percentile (polarity-adjusted) -> sub-score
//            -> weighted mean per pillar -> pillar score -> weighted mean -> composite
//
// Every step here is a pure function of (companies, weights). No fetch, no
// DOM, no randomness (rankSensitivity.ts is the one exception, and it takes
// an explicit seed for that reason). That purity is what makes it safe to
// call synchronously from a memoised selector on every slider tick.

import { percentileRank, weightedMeanSkippingNulls, median } from "./percentile";
import { REGISTRY, type GapKind, type Pillar, type RawInputs, type SubScoreDef } from "./registry";
import { MEASURED_STATUSES, TRUSTED_STATUSES, type Company } from "./types";

export const PILLARS: Pillar[] = ["P1", "P2", "P3"];

export interface WeightsState {
  /** Raw (not necessarily normalised) pillar weights. Missing pillar = 1. */
  pillars: Partial<Record<Pillar, number>>;
  /** Raw sub-score weights, keyed by sub-score id, scoped within their
   * pillar. Missing sub-score id = 1 (equal weight among what's present). */
  subscores: Partial<Record<string, number>>;
}

export function defaultWeights(): WeightsState {
  const pillars: Partial<Record<Pillar, number>> = { P1: 1, P2: 1, P3: 1 };
  const subscores: Partial<Record<string, number>> = {};
  for (const s of REGISTRY) subscores[s.id] = 1;
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

function coerce(v: number | string | boolean | undefined): number {
  if (v === undefined) return NaN;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "number") return v;
  const n = Number(v);
  return Number.isFinite(n) ? n : NaN;
}

/** Reads a sub-score's inputs off one company. Never invents a value: an
 * input that is not_disclosed, quote_failed, or simply absent from the
 * company's fields makes the whole sub-score 'unavailable' for that company,
 * regardless of whether other inputs happen to be present. */
export function resolveInputs(
  company: Company,
  sub: SubScoreDef
): { statusClass: StatusClass; inputs: RawInputs | null } {
  let worst: StatusClass = "measured";
  const inputs: RawInputs = {};
  for (const field of sub.inputs) {
    const rec = company.fields[field];
    if (!rec || !TRUSTED_STATUSES.has(rec.st)) {
      worst = "unavailable";
      continue;
    }
    if (!MEASURED_STATUSES.has(rec.st) && worst !== "unavailable") worst = "imputed";
    inputs[field] = coerce(rec.v);
  }
  // Optional inputs never gate availability, unlike required ones above: an
  // absent/untrusted optional field is always zero-filled, independent of
  // whatever the required inputs decided. This runs regardless of `worst` so
  // a sub-score with optionalInputs still gets them zero-filled even in the
  // nullPolicy: 'zero' branch below (which only ever touches `sub.inputs`).
  for (const field of sub.optionalInputs ?? []) {
    const rec = company.fields[field];
    inputs[field] = rec && TRUSTED_STATUSES.has(rec.st) ? coerce(rec.v) : 0;
  }
  if (worst === "unavailable") {
    if (sub.nullPolicy !== "zero") return { statusClass: "unavailable", inputs: null };
    // 'zero': a missing input is filled with a literal 0 (e.g. "no penalty
    // records found" reads the same as "zero penalties"), but the point
    // still renders hollow -- the data really is missing, only the maths
    // treats it as a true zero rather than refusing to compute.
    for (const field of sub.inputs) {
      if (!(field in inputs)) inputs[field] = 0;
    }
    return { statusClass: "unavailable", inputs };
  }
  return { statusClass: worst, inputs };
}

export interface SubScoreResult {
  id: string;
  statusClass: StatusClass;
  rawValue: number | null;
  /** 0-100, already polarity-adjusted so 100 is always "best". */
  score: number | null;
  /** Size of the sector distribution this was ranked against -- an axis
   * reading "0 / 41 companies" is a finding, and this is where it comes from. */
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
/** sector -> sub-score id -> sorted-ascending list of MEASURED-only raw values. */
export type SectorDistributions = Map<string, Map<string, number[]>>;

/**
 * Pass 1 of the pipeline, exposed on its own so reference.ts can rank a
 * reference point (sector median, sector best, a named company's own value)
 * against the exact same distribution the scores themselves use. There must
 * be only one distribution-builder and one percentile function in this
 * codebase -- a second implementation is how the map ends up contradicting
 * the table.
 */
export function resolveAndBuildDistributions(
  companies: readonly Company[],
  registry: SubScoreDef[] = REGISTRY
): { resolved: ResolvedInputs; distributions: SectorDistributions } {
  const bySector = new Map<string, Company[]>();
  for (const c of companies) {
    const arr = bySector.get(c.sector);
    if (arr) arr.push(c);
    else bySector.set(c.sector, [c]);
  }

  const resolved: ResolvedInputs = new Map();
  const distributions: SectorDistributions = new Map();

  for (const [sector, group] of bySector) {
    const subDist = new Map<string, number[]>();
    distributions.set(sector, subDist);
    for (const company of group) {
      const perCompany = new Map<string, { statusClass: StatusClass; inputs: RawInputs | null }>();
      resolved.set(company.ticker, perCompany);
      for (const sub of registry) {
        const r = resolveInputs(company, sub);
        perCompany.set(sub.id, r);
        if (r.statusClass === "measured" && r.inputs) {
          const rawValue = sub.compute(r.inputs);
          if (Number.isFinite(rawValue)) {
            const arr = subDist.get(sub.id);
            if (arr) arr.push(rawValue);
            else subDist.set(sub.id, [rawValue]);
          }
        }
      }
    }
  }
  for (const subDist of distributions.values()) {
    for (const [id, values] of subDist) subDist.set(id, values.sort((a, b) => a - b));
  }
  return { resolved, distributions };
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

  const { resolved, distributions } = resolveAndBuildDistributions(companies, registry);

  // Pass 2: percentile + aggregate.
  const out = new Map<string, CompanyScoreResult>();
  for (const company of companies) {
    const perCompany = resolved.get(company.ticker)!;
    const subDist = distributions.get(company.sector) ?? new Map();
    const { pillars: pillarW, subscores: subW } = normalizedFor(company.sector);
    const pillarResults = {} as Record<Pillar, PillarResult>;

    for (const pillar of PILLARS) {
      const subs = registry.filter((s) => s.pillar === pillar);
      const subResults: SubScoreResult[] = subs.map((sub) => {
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

        const score = rawValue === null ? null : percentileRank(rawValue, distribution, sub.polarity);
        return { id: sub.id, statusClass: r.statusClass, rawValue, score, coverageN: distribution.length };
      });

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
