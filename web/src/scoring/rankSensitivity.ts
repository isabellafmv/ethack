// "A ranking that collapses under a 10% weight change is not a ranking" --
// this is the demo moment the sliders were built for. For every company, we
// perturb the pillar weights within a plausible neighbourhood of the current
// setting and measure how far its composite RANK moves. A company whose rank
// barely moves is robust; a company that swings from #12 to #180 on a 10%
// nudge is telling you the ranking is unstable at that point in the index,
// not that the company is unstable.
//
// Seeded PRNG so this is deterministic in tests and reproducible from a
// shared URL -- "reproducible" is a stated requirement, and silent
// randomness would quietly violate it.

import { computeScores, PILLARS, type WeightsState } from "./pipeline";
import type { Company } from "./types";

export interface RankSpread {
  ticker: string;
  baseRank: number;
  minRank: number;
  maxRank: number;
  /** maxRank - minRank across the sampled neighbourhood. 0 = perfectly
   * stable at this weight setting; a large spread is the finding. */
  spread: number;
}

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function ranksFromScores(scores: Map<string, { composite: number | null }>): Map<string, number> {
  const withScores = [...scores.entries()].filter(([, s]) => s.composite !== null) as [string, { composite: number }][];
  withScores.sort((a, b) => b[1].composite - a[1].composite);
  const ranks = new Map<string, number>();
  withScores.forEach(([ticker], i) => ranks.set(ticker, i + 1));
  return ranks;
}

/**
 * @param companies the (typically unfiltered) universe to rank within
 * @param weights the current slider position -- the centre of the sampled neighbourhood
 * @param perturbFraction how far pillar weights are allowed to jitter, as a
 *   fraction of their normalised value (0.1 = "the plausible +/-10% a viewer
 *   might drag to")
 * @param samples neighbourhood sample count; 30 is enough for a stable
 *   spread at 500 companies and stays well under a frame budget
 * @param seed fixes the PRNG so results are reproducible
 */
export function rankSensitivity(
  companies: readonly Company[],
  weights: WeightsState,
  { perturbFraction = 0.1, samples = 30, seed = 1 }: { perturbFraction?: number; samples?: number; seed?: number } = {}
): Map<string, RankSpread> {
  const rand = mulberry32(seed);
  const base = computeScores(companies, weights);
  const baseRanks = ranksFromScores(base);

  const minRank = new Map<string, number>();
  const maxRank = new Map<string, number>();
  for (const ticker of baseRanks.keys()) {
    minRank.set(ticker, baseRanks.get(ticker)!);
    maxRank.set(ticker, baseRanks.get(ticker)!);
  }

  for (let i = 0; i < samples; i++) {
    const jittered: WeightsState = {
      pillars: Object.fromEntries(
        PILLARS.map((p) => {
          const base = weights.pillars[p] ?? 1;
          const jitter = 1 + (rand() * 2 - 1) * perturbFraction;
          return [p, Math.max(0, base * jitter)];
        })
      ),
      subscores: weights.subscores,
    };
    const sampleScores = computeScores(companies, jittered);
    const sampleRanks = ranksFromScores(sampleScores);
    for (const [ticker, rank] of sampleRanks) {
      if (rank < (minRank.get(ticker) ?? Infinity)) minRank.set(ticker, rank);
      if (rank > (maxRank.get(ticker) ?? -Infinity)) maxRank.set(ticker, rank);
    }
  }

  const out = new Map<string, RankSpread>();
  for (const [ticker, baseRank] of baseRanks) {
    const lo = minRank.get(ticker) ?? baseRank;
    const hi = maxRank.get(ticker) ?? baseRank;
    out.set(ticker, { ticker, baseRank, minRank: lo, maxRank: hi, spread: hi - lo });
  }
  return out;
}
