// raw fields -> compute() -> sector percentile (polarity-adjusted) -> sub-score
//            -> weighted mean per pillar -> pillar score -> weighted mean -> composite
//
// Every step here is a pure function of (companies, weights). No fetch, no
// DOM, no randomness (rankSensitivity.ts is the one exception, and it takes
// an explicit seed for that reason). That purity is what makes it safe to
// call synchronously from a memoised selector on every slider tick.

import { percentileRank, weightedMeanSkippingNulls, median } from "./percentile";
import { REGISTRY, type Pillar, type RawInputs, type SubScoreDef } from "./registry";
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
  score: number | null;
  subScores: SubScoreResult[];
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
 */
export function computeScores(
  companies: readonly Company[],
  weights: WeightsState,
  registry: SubScoreDef[] = REGISTRY
): Map<string, CompanyScoreResult> {
  const { pillars: pillarW, subscores: subW } = normalizedWeights(weights, registry);
  const { resolved, distributions } = resolveAndBuildDistributions(companies, registry);

  // Pass 2: percentile + aggregate.
  const out = new Map<string, CompanyScoreResult>();
  for (const company of companies) {
    const perCompany = resolved.get(company.ticker)!;
    const subDist = distributions.get(company.sector) ?? new Map();
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

      const pillarScore = weightedMeanSkippingNulls(
        subResults.map((r) => ({ value: r.score, weight: subW[r.id] ?? 1 }))
      );
      pillarResults[pillar] = { pillar, score: pillarScore, subScores: subResults };
    }

    const composite = weightedMeanSkippingNulls(
      PILLARS.map((p) => ({ value: pillarResults[p].score, weight: pillarW[p] }))
    );

    out.set(company.ticker, { ticker: company.ticker, sector: company.sector, pillars: pillarResults, composite });
  }

  return out;
}
