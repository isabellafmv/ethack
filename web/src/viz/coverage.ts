// Coverage strip maths: "of N companies, how many have measured / imputed /
// not-disclosed values on the three visible axes." A honest empty axis is a
// finding the spec explicitly wants on screen, not smoothed over.
import type { CompanyScoreResult } from "../scoring/pipeline";
import { subScoreById } from "../scoring/registry";
import type { AxisSlot } from "./views";

export interface AxisCoverage {
  axis: AxisSlot;
  measured: number;
  imputed: number;
  unavailable: number;
  total: number;
}

export function axisCoverage(axis: AxisSlot, results: readonly CompanyScoreResult[]): AxisCoverage {
  let measured = 0, imputed = 0, unavailable = 0;
  for (const r of results) {
    if (axis.kind === "subscore") {
      const sub = subScoreById(axis.id);
      const s = r.pillars[sub.pillar].subScores.find((x) => x.id === axis.id);
      if (s?.statusClass === "measured") measured++;
      else if (s?.statusClass === "imputed") imputed++;
      else unavailable++;
    } else {
      const score = axis.kind === "composite" ? r.composite : r.pillars[axis.pillar].score;
      if (score !== null) measured++;
      else unavailable++;
    }
  }
  return { axis, measured, imputed, unavailable, total: results.length };
}
