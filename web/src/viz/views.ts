// Four views = four axis triples over one renderer and one config object, not
// four components (Task 4). Global reads pillar composites; the three pillar
// views read that pillar's own registry entries. P2 has four sub-scores and
// three axes -- the fourth (p2_innovation) must stay reachable via the axis
// dropdown, never silently dropped, so `options` always lists every entry in
// the pillar even when only three are shown at once.
import { registryForPillar, subScoreById, type Pillar } from "../scoring/registry";
import type { CompanyScoreResult } from "../scoring/pipeline";

export type AxisSlot =
  | { kind: "pillar"; pillar: Pillar }
  | { kind: "composite" }
  | { kind: "subscore"; id: string };

export function axisKey(axis: AxisSlot): string {
  return axis.kind === "subscore" ? `sub:${axis.id}` : axis.kind === "pillar" ? `pillar:${axis.pillar}` : "composite";
}

export function axisLabel(axis: AxisSlot): string {
  if (axis.kind === "composite") return "Composite";
  if (axis.kind === "pillar") return `${axis.pillar} score`;
  return subScoreById(axis.id).label;
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

const P1_SUBS = registryForPillar("P1").map((s): AxisSlot => ({ kind: "subscore", id: s.id }));
const P2_SUBS = registryForPillar("P2").map((s): AxisSlot => ({ kind: "subscore", id: s.id }));
const P3_SUBS = registryForPillar("P3").map((s): AxisSlot => ({ kind: "subscore", id: s.id }));

export const VIEWS: ViewConfig[] = [
  {
    id: "global",
    label: "Global",
    options: [
      { kind: "pillar", pillar: "P1" }, { kind: "pillar", pillar: "P2" }, { kind: "pillar", pillar: "P3" },
      { kind: "composite" },
    ],
    defaultAxes: [{ kind: "pillar", pillar: "P1" }, { kind: "pillar", pillar: "P2" }, { kind: "pillar", pillar: "P3" }],
  },
  {
    id: "P1",
    label: "Environmental",
    options: P1_SUBS,
    defaultAxes: [P1_SUBS[0], P1_SUBS[1], P1_SUBS[2]],
  },
  {
    id: "P2",
    label: "Transition",
    // Four sub-scores, three axes -- p2_innovation is reachable via the
    // dropdown (options carries all four) even though it's not a default.
    options: P2_SUBS,
    defaultAxes: [P2_SUBS[0], P2_SUBS[1], P2_SUBS[2]],
  },
  {
    id: "P3",
    label: "Governance",
    options: P3_SUBS,
    defaultAxes: [P3_SUBS[0], P3_SUBS[1], P3_SUBS[2]],
  },
];

export function viewById(id: ViewConfig["id"]): ViewConfig {
  const v = VIEWS.find((v) => v.id === id);
  if (!v) throw new Error(`unknown view id ${JSON.stringify(id)}`);
  return v;
}
