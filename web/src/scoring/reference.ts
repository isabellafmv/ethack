// Sets what "better/worse" is measured against. Reuses computeScores'
// distribution builder and percentile.ts's median/percentileRank -- there is
// exactly one median implementation and one percentile implementation in
// this codebase, or the map and the table would eventually disagree.

import { median, percentileRank } from "./percentile";
import { REGISTRY, type Polarity } from "./registry";
import { resolveAndBuildDistributions, type SectorDistributions } from "./pipeline";
import type { Company } from "./types";

export type ReferenceMode = "sector_median" | "sector_best" | "index_median" | "company";

export interface ReferenceSpec {
  mode: ReferenceMode;
  /** Required, and only meaningful, when mode === 'company'. */
  companyTicker?: string;
}

export function referenceLabel(spec: ReferenceSpec, deltaMode: "raw" | "sector_adjusted"): string {
  switch (spec.mode) {
    case "sector_median":
      return "vs sector median";
    case "sector_best":
      return "vs sector best-in-class";
    case "index_median":
      return "vs index median";
    case "company":
      return `vs ${spec.companyTicker ?? "?"}, ${deltaMode === "raw" ? "raw" : "sector-adjusted"}`;
  }
}

function bestInDistribution(distribution: readonly number[], polarity: Polarity): number | null {
  if (distribution.length === 0) return null;
  return polarity === "higher_is_better" ? Math.max(...distribution) : Math.min(...distribution);
}

/** One resolved reference value per sub-score id, for one company's sector
 * (sector-scoped modes need to know which sector they're being read into). */
export type ReferenceValues = Map<string, { raw: number | null; score: number | null }>;

/**
 * Resolves the reference point for every sub-score, scoped to `sector`
 * (irrelevant for index_median and company modes, but sector_median/
 * sector_best need it). Call once per (spec, sector) pair -- typically once
 * per visible sector per render, not per company.
 */
export function resolveReference(
  companies: readonly Company[],
  spec: ReferenceSpec,
  sector: string
): ReferenceValues {
  const { distributions } = resolveAndBuildDistributions(companies);
  const sectorDist = distributions.get(sector) ?? new Map<string, number[]>();
  const out: ReferenceValues = new Map();

  for (const sub of REGISTRY) {
    let raw: number | null = null;
    let distributionForScore = sectorDist.get(sub.id) ?? [];

    if (spec.mode === "sector_median") {
      raw = median(distributionForScore);
    } else if (spec.mode === "sector_best") {
      raw = bestInDistribution(distributionForScore, sub.polarity);
    } else if (spec.mode === "index_median") {
      const all = mergeAllSectors(distributions, sub.id);
      raw = median(all);
      distributionForScore = all; // index-wide reference is scored against the index-wide pool
    } else if (spec.mode === "company") {
      const refCompany = companies.find((c) => c.ticker === spec.companyTicker);
      const refSectorDist = refCompany ? distributions.get(refCompany.sector)?.get(sub.id) ?? [] : [];
      if (refCompany) {
        const { resolved } = resolveAndBuildDistributions([refCompany]);
        const r = resolved.get(refCompany.ticker)?.get(sub.id);
        if (r && r.inputs && r.statusClass !== "unavailable") raw = sub.compute(r.inputs);
      }
      distributionForScore = refSectorDist;
    }

    const score = raw === null ? null : percentileRank(raw, distributionForScore, sub.polarity);
    out.set(sub.id, { raw, score });
  }
  return out;
}

function mergeAllSectors(distributions: SectorDistributions, subId: string): number[] {
  const merged: number[] = [];
  for (const bySub of distributions.values()) {
    const values = bySub.get(subId);
    if (values) merged.push(...values);
  }
  return merged.sort((a, b) => a - b);
}

/**
 * Signed delta for the diverging colour scale. 'sector_adjusted' compares
 * percentile SCORES (unit-free, comparable across every sub-score) -- this
 * answers "does this company rank better than the reference within its own
 * sector". 'raw' compares the underlying values directly, in the sub-score's
 * native units -- meaningful for "vs a named company" where the viewer wants
 * the literal gap, not a re-normalised one. Positive always means "better",
 * regardless of polarity.
 */
export function referenceDelta(
  companyRaw: number | null,
  companyScore: number | null,
  reference: { raw: number | null; score: number | null },
  polarity: Polarity,
  mode: "raw" | "sector_adjusted"
): number | null {
  if (mode === "sector_adjusted") {
    if (companyScore === null || reference.score === null) return null;
    return companyScore - reference.score;
  }
  if (companyRaw === null || reference.raw === null) return null;
  const diff = companyRaw - reference.raw;
  return polarity === "higher_is_better" ? diff : -diff;
}
