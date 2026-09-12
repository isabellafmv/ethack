// Pure percentile maths. No knowledge of companies, payloads or weights --
// that's what makes it independently testable and safe to call synchronously
// on every slider tick and every filter change (500 x 13 is ~10ms, per the
// architecture note; there is no reason to push this to a worker).

import type { Polarity } from "./registry";

/**
 * Percentile rank of `value` within `distribution`, normalised so 0 is the
 * worst performer in the group and 100 is the best, regardless of polarity
 * -- that normalisation happens exactly once, here, so nothing downstream
 * ever has to remember which direction a field points.
 *
 * Uses the (rank - 1) / (n - 1) convention (the worst value maps to exactly
 * 0, the best to exactly 100) rather than a fractional mid-rank, because a
 * sub-score axis where nobody ever hits the ends of their own sector's range
 * reads as broken on stage. Ties share the average rank of their block, so a
 * value tied with the whole distribution lands at 50. A lone company in a
 * sector (n = 1) is trivially both its own best and worst: scores 100.
 * Returns null if the distribution is empty -- there is nothing to rank
 * against, which is itself a finding, not a zero.
 */
export function percentileRank(
  value: number,
  distribution: readonly number[],
  polarity: Polarity
): number | null {
  const n = distribution.length;
  if (n === 0 || !Number.isFinite(value)) return null;
  if (n === 1) return 100;

  let below = 0;
  let equal = 0;
  for (const v of distribution) {
    if (v < value) below++;
    else if (v === value) equal++;
  }
  const avgRank = below + (equal + 1) / 2; // 1-indexed average rank of the tied block
  const raw = ((avgRank - 1) / (n - 1)) * 100;
  return polarity === "lower_is_better" ? 100 - raw : raw;
}

export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/** Weighted mean over only the defined (non-null) entries, with weights
 * renormalised across just those entries. A missing sub-score does not drag
 * a pillar score down -- that would penalise disclosure gaps twice, once on
 * the axis itself and once again in every aggregate above it. Returns null
 * when nothing is available to average. */
export function weightedMeanSkippingNulls(
  entries: readonly { value: number | null; weight: number }[]
): number | null {
  let weightSum = 0;
  let acc = 0;
  for (const { value, weight } of entries) {
    if (value === null || !Number.isFinite(value) || weight <= 0) continue;
    acc += value * weight;
    weightSum += weight;
  }
  return weightSum > 0 ? acc / weightSum : null;
}
