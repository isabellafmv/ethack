// Extends reference.ts's per-sub-score reference values up to pillar and
// composite axes (needed because the Global view's axes ARE pillar scores),
// using the exact same weightedMeanSkippingNulls/normalizedWeights functions
// pipeline.ts uses to build those aggregates in the first place. Reusing
// those, rather than re-deriving "how sub-scores combine" here, is what
// keeps the coloured map and the scored table from ever disagreeing.
import { weightedMeanSkippingNulls } from "../scoring/percentile";
import { normalizedWeights, weightsForSector, PILLARS, type WeightsState } from "../scoring/pipeline";
import { registryForPillar, type Pillar } from "../scoring/registry";
import type { ReferenceValues } from "../scoring/reference";
import { type AxisSlot } from "./views";

/** `sector` is the COMPANY's sector, not the reference's -- in materiality
 * mode, a company's own weights (not the reference point's) are what
 * determine how its axes combine, so its point colour and its point
 * position always agree on which weights were used. */
export function referenceScoreForAxis(
  axis: AxisSlot,
  refValues: ReferenceValues,
  weights: WeightsState | Map<string, WeightsState>,
  sector: string
): number | null {
  const { pillars: pillarW, subscores: subW } = normalizedWeights(weightsForSector(weights, sector));

  const pillarScore = (pillar: Pillar): number | null =>
    weightedMeanSkippingNulls(
      registryForPillar(pillar).map((s) => ({ value: refValues.get(s.id)?.score ?? null, weight: subW[s.id] ?? 1 }))
    );

  if (axis.kind === "subscore") return refValues.get(axis.id)?.score ?? null;
  if (axis.kind === "pillar") return pillarScore(axis.pillar);
  return weightedMeanSkippingNulls(PILLARS.map((p) => ({ value: pillarScore(p), weight: pillarW[p] })));
}

/** Diverging red -> grey -> green. `t` is a delta on the 0-100 score scale,
 * clamped to +/-40 (deltas rarely exceed that in practice; clamping keeps a
 * handful of extreme companies from washing out the rest of the scale). */
export function divergingColor(delta: number | null): string {
  if (delta === null) return "#6b7280"; // neutral grey -- no reference to compare against
  const t = Math.max(-40, Math.min(40, delta)) / 40; // -1..1
  if (t >= 0) {
    // grey (#9ca3af) -> green (#22c55e)
    return lerpColor([156, 163, 175], [34, 197, 94], t);
  }
  // grey -> red (#ef4444)
  return lerpColor([156, 163, 175], [239, 68, 68], -t);
}

function lerpColor(a: number[], b: number[], t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}
