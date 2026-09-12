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

function bySubId(subs: AxisSlot[], id: string): AxisSlot {
  const found = subs.find((s) => s.kind === "subscore" && s.id === id);
  if (!found) throw new Error(`view default references unknown sub-score id ${JSON.stringify(id)}`);
  return found;
}

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
    // Four sub-scores, three axes. p1_energy_mix is reachable via the
    // dropdown but not a default -- it's 0/500 covered in real data today,
    // while p1_carbon_intensity and the newer p1_input_efficiency actually
    // have companies on them. Defaulting to two empty axes out of three
    // would undercut the entire reason input_efficiency was added.
    options: P1_SUBS,
    defaultAxes: [bySubId(P1_SUBS, "p1_carbon_intensity"), bySubId(P1_SUBS, "p1_input_efficiency"), bySubId(P1_SUBS, "p1_resource_waste")],
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
    // Four sub-scores, three axes -- the inverse of P2's situation: the
    // NEW sub-score (p3_capital_stewardship) is the well-covered one and
    // belongs in the default three; p3_controversy_flags (0/500 covered
    // today) moves to dropdown-only.
    options: P3_SUBS,
    defaultAxes: [bySubId(P3_SUBS, "p3_board_independence"), bySubId(P3_SUBS, "p3_exec_compensation"), bySubId(P3_SUBS, "p3_capital_stewardship")],
  },
];

export function viewById(id: ViewConfig["id"]): ViewConfig {
  const v = VIEWS.find((v) => v.id === id);
  if (!v) throw new Error(`unknown view id ${JSON.stringify(id)}`);
  return v;
}
