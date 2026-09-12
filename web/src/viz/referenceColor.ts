// Extends reference.ts's per-sub-score reference values up to pillar and
// composite axes (needed because the Global view's axes ARE pillar scores),
// using the exact same aggregateWithDisclosurePenalty/weightedMeanSkippingNulls/
// normalizedWeights functions pipeline.ts uses to build those aggregates in
// the first place. Reusing those, rather than re-deriving "how sub-scores
// combine" here, is what keeps the coloured map and the scored table from
// ever disagreeing.
import { weightedMeanSkippingNulls } from "../scoring/percentile";
import { aggregateWithDisclosurePenalty, normalizedWeights, weightsForSector, PILLARS, type WeightsState } from "../scoring/pipeline";
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

  // Same disclosure-coverage penalty the scored companies themselves go
  // through (see pipeline.ts's aggregateWithDisclosurePenalty) -- otherwise
  // the reference point (sector median/best, a named company) would sit on
  // a different basis than the points being compared against it, and the
  // coloured map and the scored table would disagree.
  const pillarScore = (pillar: Pillar): number | null =>
    aggregateWithDisclosurePenalty(
      registryForPillar(pillar).map((s) => ({
        id: s.id,
        value: refValues.get(s.id)?.score ?? null,
        weight: subW[s.id] ?? 1,
        disclosed: (refValues.get(s.id)?.raw ?? null) !== null,
        gapKind: s.gapKind,
      }))
    ).score;

  if (axis.kind === "subscore") return refValues.get(axis.id)?.score ?? null;
  if (axis.kind === "pillar") return pillarScore(axis.pillar);
  return weightedMeanSkippingNulls(PILLARS.map((p) => ({ value: pillarScore(p), weight: pillarW[p] })));
}

/** Diverging orange -> accent, a single continuous gradient (no grey
 * midpoint): worse is orange, better is accent, and "at reference" is
 * whatever blend sits between them. `delta === null` (no reference to
 * compare against at all -- a different situation from "tied with the
 * reference") is the one case that still needs a distinct neutral grey,
 * since it isn't a point on this scale at all.
 *
 * `t` is a delta on the 0-100 score scale, clamped to +/-CLAMP. This is
 * `avgDelta` from ScatterView -- the MEAN across every currently-visible
 * axis, which is a materially narrower distribution than any single axis's
 * own delta (independent per-axis deltas partially cancel out when
 * averaged). Measured against the real matrix: median |avgDelta| ~11,
 * p75 ~17, p95 ~26, max observed ~36 -- a +/-40 clamp (sized for a single
 * axis) left most companies within the muddy middle third of the scale.
 * Clamping at 20 instead means a middling company still reads as a clear
 * lean rather than "basically the same colour as everyone else", while the
 * ~10% most extreme companies per axis-set legitimately max out solid. */
const CLAMP = 20;
const NO_REFERENCE_RGB = [150, 150, 148];
const WORSE_RGB = [228, 108, 10]; // #E46C0A -- "worse"
const BETTER_RGB = [170, 182, 68]; // #AAB644 -- "better"

export function divergingColor(delta: number | null): string {
  if (delta === null) return `rgb(${NO_REFERENCE_RGB.join(",")})`;
  const t = Math.max(-CLAMP, Math.min(CLAMP, delta)) / CLAMP; // -1..1
  return lerpColor(WORSE_RGB, BETTER_RGB, (t + 1) / 2);
}

function lerpColor(a: number[], b: number[], t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}
