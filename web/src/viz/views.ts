// Four views = four axis triples over one renderer and one config object, not
// four components (Task 4). Global reads pillar composites; the three pillar
// views read that pillar's own registry entries. P2 has four sub-scores and
// three axes, P3 has five and three axes -- every sub-score not shown by
// default must still stay reachable via the axis dropdown, never silently
// dropped, so `options` always lists every entry in the pillar even when
// only three are shown at once.
import { registryForPillar, subScoreById, type Pillar } from "../scoring/registry";
import { normalizedWeights, type CompanyScoreResult, type WeightsState } from "../scoring/pipeline";

export type AxisSlot =
  | { kind: "pillar"; pillar: Pillar }
  | { kind: "composite" }
  | { kind: "subscore"; id: string };

export function axisKey(axis: AxisSlot): string {
  return axis.kind === "subscore" ? `sub:${axis.id}` : axis.kind === "pillar" ? `pillar:${axis.pillar}` : "composite";
}

/** The pillar's actual score name, used everywhere a pillar is named (axis
 * pickers, the weight panel, the coverage strip) so there's exactly one
 * place to keep them in sync. */
export const PILLAR_SCORE_NAMES: Record<Pillar, string> = {
  P1: "Environmental Impact",
  P2: "Transition Risk",
  P3: "Governance",
};

export function axisLabel(axis: AxisSlot): string {
  if (axis.kind === "composite") return "Composite";
  if (axis.kind === "pillar") return PILLAR_SCORE_NAMES[axis.pillar];
  return subScoreById(axis.id).label;
}

/** Plain-language paragraph for each pillar, shown in the axis-picker info
 * popover (Task 7) when a pillar rather than a sub-score is selected. Each
 * one names how its sub-scores combine (a weighted mean, with weights the
 * viewer controls in the sidebar) and what the disclosure-coverage penalty
 * does when one of them is missing for a company. */
export const PILLAR_DESCRIPTIONS: Record<Pillar, string> = {
  P1: "A weighted average of this company's environmental sub-scores (carbon intensity, grid " +
    "carbon intensity, waste diversion, input efficiency), each already ranked against " +
    "sector peers on a 0-100 scale. The weights are set in the sidebar and can be adjusted " +
    "or switched to sector-materiality mode. If a sub-score is missing for a company (not " +
    "disclosed), it's dropped from the average rather than counted as zero -- but the " +
    "pillar score is then scaled down by a disclosure-coverage penalty (as low as 60% of " +
    "the raw average when every disclosure-dependent sub-score is missing), so a company " +
    "can't score well simply by not reporting.",
  P2: "A weighted average of this company's transition-risk sub-scores (carbon-price " +
    "exposure, sector carbon intensity, regulatory commitment, transition affordability), " +
    "each already on a 0-100 scale -- some ranked against sector peers, others an absolute " +
    "score comparable across every sector (each sub-score's own info popover says which). " +
    "The weights are set in the sidebar and can be adjusted or switched to sector-" +
    "materiality mode; the manual default here isn't an even split -- it starts from the " +
    "same fixed weights the underlying model itself uses for this pillar. If a sub-score " +
    "is missing for a company (not " +
    "disclosed), it's dropped from the average rather than counted as zero -- but the " +
    "pillar score is then scaled down by a disclosure-coverage penalty (as low as 60% of " +
    "the raw average when every disclosure-dependent sub-score is missing), so a company " +
    "can't score well simply by not reporting.",
  P3: "A weighted average of this company's governance sub-scores (board independence, " +
    "compensation alignment, climate governance, penalty record, capital stewardship), " +
    "each already on a 0-100 scale -- penalty record is ranked against every company in the " +
    "index, the rest are absolute scores comparable across every sector (each sub-score's " +
    "own info popover says which). The weights are set in the sidebar and can be adjusted " +
    "or switched to sector-materiality mode; the manual default here isn't an even split -- " +
    "it starts from the same fixed weights the underlying model itself uses for this " +
    "pillar. If a sub-score is missing for a company (not disclosed), it's dropped from " +
    "the average rather than counted as zero -- " +
    "but the pillar score is then scaled down by a disclosure-coverage penalty (as low as " +
    "60% of the raw average when every disclosure-dependent sub-score is missing), so a " +
    "company can't score well simply by not reporting.",
};

/** Shown when the axis picker has "Composite" selected. */
export const COMPOSITE_DESCRIPTION =
  "A weighted average of the three pillar scores (Environmental, Transition risk, " +
  "Governance), each of which has already had its own disclosure-coverage penalty applied. " +
  "The pillar weights are set in the sidebar. If a whole pillar is unavailable for a " +
  "company, it's dropped from this average rather than counted as zero -- the composite is " +
  "not itself penalized a second time for that on top of what each pillar already applied.";

/** Static plain-language text for the axis-picker info popover: per-sub-score
 * copy from the registry, or the pillar/composite paragraphs above. */
export function axisDescription(axis: AxisSlot): string {
  if (axis.kind === "composite") return COMPOSITE_DESCRIPTION;
  if (axis.kind === "pillar") return PILLAR_DESCRIPTIONS[axis.pillar];
  return subScoreById(axis.id).description;
}

/** The weight this axis currently carries in its parent aggregation -- a
 * pillar's share of the composite, or a sub-score's share within its own
 * pillar -- read from the same normalizedWeights() DetailPanel.tsx uses, so
 * the number in the popover never drifts from what scoring actually applies.
 * Composite sits at the top of the tree and has no weight of its own, hence
 * null. */
export function axisWeightPct(axis: AxisSlot, weights: WeightsState): number | null {
  if (axis.kind === "composite") return null;
  const { pillars, subscores } = normalizedWeights(weights);
  if (axis.kind === "pillar") return pillars[axis.pillar] * 100;
  return (subscores[axis.id] ?? 0) * 100;
}

/** The value this axis reads off one company's already-computed scores.
 * Composite/pillar/sub-score all share the same 0-100 (or null) scale, so an
 * axis never needs to know which kind it is beyond this one lookup. */
export function axisValue(result: CompanyScoreResult, axis: AxisSlot): number | null {
  if (axis.kind === "composite") return result.composite;
  if (axis.kind === "pillar") return result.pillars[axis.pillar].score;
  const sub = subScoreById(axis.id);
  return result.pillars[sub.pillar].subScores.find((s) => s.id === axis.id)?.score ?? null;
}

/** 'imputed' only ever applies to a sub-score axis (pillar/composite are
 * aggregates with no single status of their own) -- used to render a point
 * hollow/wireframe rather than solid when it's standing in for a value that
 * was never actually measured. */
export function axisIsImputed(result: CompanyScoreResult, axis: AxisSlot): boolean {
  if (axis.kind !== "subscore") return false;
  const sub = subScoreById(axis.id);
  return result.pillars[sub.pillar].subScores.find((s) => s.id === axis.id)?.statusClass === "imputed";
}

export interface ViewConfig {
  id: "global" | Pillar;
  label: string;
  /** Every axis this view's three dropdowns may choose from. */
  options: AxisSlot[];
  /** What each of the three dropdowns is set to before the viewer touches them. */
  defaultAxes: [AxisSlot, AxisSlot, AxisSlot];
}

export const P1_SUBS = registryForPillar("P1").map((s): AxisSlot => ({ kind: "subscore", id: s.id }));
export const P2_SUBS = registryForPillar("P2").map((s): AxisSlot => ({ kind: "subscore", id: s.id }));
export const P3_SUBS = registryForPillar("P3").map((s): AxisSlot => ({ kind: "subscore", id: s.id }));

export function bySubId(subs: AxisSlot[], id: string): AxisSlot {
  const found = subs.find((s) => s.kind === "subscore" && s.id === id);
  if (!found) throw new Error(`view default references unknown sub-score id ${JSON.stringify(id)}`);
  return found;
}

export const VIEWS: ViewConfig[] = [
  {
    id: "global",
    label: "Map",
    options: [
      { kind: "pillar", pillar: "P1" }, { kind: "pillar", pillar: "P2" }, { kind: "pillar", pillar: "P3" },
      { kind: "composite" },
    ],
    defaultAxes: [{ kind: "pillar", pillar: "P1" }, { kind: "pillar", pillar: "P2" }, { kind: "pillar", pillar: "P3" }],
  },
  // Per-pillar views (Environmental/Transition/Governance) are parked here,
  // not deleted -- only "Map" (id: "global") is exposed as a tab for now. Their configs
  // (and P1_SUBS/P2_SUBS/P3_SUBS above) are kept working and type-checked so
  // re-enabling is a one-line uncomment, not a rebuild.
  // {
  //   id: "P1",
  //   label: "Environmental",
  //   // Four sub-scores, three axes. p1_resource_waste is reachable via the
  //   // dropdown but not a default -- it's 0/500 covered (S16/S17/S26 aren't
  //   // pulled), while the other three are all real, well-covered data:
  //   // p1_carbon_intensity, p1_input_efficiency, and p1_energy_mix (now the
  //   // grid-intensity regional proxy from S19, 475/500 -- see registry.ts).
  //   options: P1_SUBS,
  //   defaultAxes: [bySubId(P1_SUBS, "p1_carbon_intensity"), bySubId(P1_SUBS, "p1_input_efficiency"), bySubId(P1_SUBS, "p1_energy_mix")],
  // },
  // {
  //   id: "P2",
  //   label: "Transition",
  //   // Four sub-scores, three axes -- p2_innovation is reachable via the
  //   // dropdown (options carries all four) even though it's not a default.
  //   options: P2_SUBS,
  //   defaultAxes: [P2_SUBS[0], P2_SUBS[1], P2_SUBS[2]],
  // },
  // {
  //   id: "P3",
  //   label: "Governance",
  //   // Four sub-scores, three axes -- the inverse of P2's situation: the
  //   // NEW sub-score (p3_capital_stewardship) is the well-covered one and
  //   // belongs in the default three; p3_controversy_flags (0/500 covered
  //   // today) moves to dropdown-only.
  //   options: P3_SUBS,
  //   defaultAxes: [bySubId(P3_SUBS, "p3_board_independence"), bySubId(P3_SUBS, "p3_exec_compensation"), bySubId(P3_SUBS, "p3_capital_stewardship")],
  // },
];

export function viewById(id: ViewConfig["id"]): ViewConfig {
  const v = VIEWS.find((v) => v.id === id);
  if (!v) throw new Error(`unknown view id ${JSON.stringify(id)}`);
  return v;
}
