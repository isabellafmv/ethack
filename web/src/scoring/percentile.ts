// Pure percentile maths. No knowledge of companies, payloads or weights --
// that's what makes it independently testable and safe to call synchronously
// on every slider tick and every filter change (500 x 13 is ~10ms, per the
// architecture note; there is no reason to push this to a worker).

import type { Polarity } from "./registry";

/**
 * Percentile rank of `value` within `distribution`, oriented so a higher
 * score is always "better" regardless of polarity -- that orientation
 * happens exactly once, here, so nothing downstream ever has to remember
 * which direction a field points.
 *
 * Mirrors environmental_score.py's `_sector_percentile_vs_measured` (and
 * transition_score.py's identical shape) EXACTLY, not a generic rank
 * convention invented here: `percentile = count(v' in distribution : v' <=
 * value) / n` -- equivalent to `np.searchsorted(sorted_ref, value,
 * side="right") / len(sorted_ref)`. A tied block therefore all shares the
 * same percentile (the block's own upper edge, not an average), and even
 * the best value in an n-element distribution lands at (n-1)/n rather than
 * exactly 100 -- a real, if odd-looking, property of Python's own formula
 * that this MUST reproduce bit-for-bit, not smooth over. A lone company in
 * a sector (n = 1) counts itself as 100% <= itself, so `lower_is_better`
 * scores 0 and `higher_is_better` scores 100 -- asymmetric on purpose,
 * because that is what the ported formula actually does.
 *
 * Use this for scoringMode 'sector_percentile' (and PercentileComponent,
 * which is the same shape one metric at a time). 'universe_percentile'
 * (p3_controversy_flags) needs `universeRankPercentile` below instead --
 * governance_score.py's `_controversy_score` uses pandas' `rank(pct=True,
 * method="average")`, a DIFFERENT tie-handling rule (the tied block's
 * average rank, not its upper edge), so one shared function would get one
 * of the two Python call sites wrong. Returns null if the distribution is
 * empty -- there is nothing to rank against, which is itself a finding, not
 * a zero.
 */
export function percentileRank(
  value: number,
  distribution: readonly number[],
  polarity: Polarity
): number | null {
  const n = distribution.length;
  if (n === 0 || !Number.isFinite(value)) return null;

  let countLessOrEqual = 0;
  for (const v of distribution) {
    if (v <= value) countLessOrEqual++;
  }
  const pct = countLessOrEqual / n;
  return polarity === "lower_is_better" ? 100 * (1 - pct) : 100 * pct;
}

/**
 * Percentile rank matching pandas' `Series.rank(pct=True,
 * method="average")` -- a tied block shares the AVERAGE of the ranks it
 * occupies (1-indexed), divided by n, unlike `percentileRank` above (which
 * shares the tied block's upper edge). Only governance_score.py's
 * `_controversy_score` uses this shape today (scoringMode
 * 'universe_percentile', ranked across the whole index rather than one
 * sector) -- see that function's own `penalty.rank(pct=True,
 * method="average")` call.
 */
export function universeRankPercentile(
  value: number,
  distribution: readonly number[],
  polarity: Polarity
): number | null {
  const n = distribution.length;
  if (n === 0 || !Number.isFinite(value)) return null;

  let below = 0;
  let equal = 0;
  for (const v of distribution) {
    if (v < value) below++;
    else if (v === value) equal++;
  }
  const avgRank = below + (equal + 1) / 2; // 1-indexed average rank of the tied block
  const pct = avgRank / n;
  return polarity === "lower_is_better" ? 100 * (1 - pct) : 100 * pct;
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
