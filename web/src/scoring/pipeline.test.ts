import { describe, expect, it } from "vitest";
import {
  computeScores,
  defaultWeights,
  resolveInputs,
  type WeightsState,
} from "./pipeline";
import type { SubScoreDef } from "./registry";
import type { Company, FieldRecord, Status } from "./types";

function field(v: number | string | boolean, st: Status = "structural", c = 1): FieldRecord {
  return { v, u: null, fy: 2023, src: "S01", st, c, url: 0 };
}

function makeCompany(
  ticker: string,
  sector: string,
  fields: Record<string, FieldRecord>
): Company {
  return { ticker, name: ticker, sector, sub_industry: "", fields, alternatives: {}, confidence: 1 };
}

describe("computeScores: carbon intensity (real registry sub-score)", () => {
  it("scores a fully-disclosed company against its sector peers", () => {
    const companies = [
      makeCompany("A", "Energy", { scope1_tco2e: field(100), revenue_usd: field(1_000_000) }),
      makeCompany("B", "Energy", { scope1_tco2e: field(900), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_carbon_intensity")!;
    // lower_is_better: A has the lower intensity, so A should score above B.
    const b = scores.get("B")!.pillars.P1.subScores.find((s) => s.id === "p1_carbon_intensity")!;
    expect(a.score).not.toBeNull();
    expect(a.score!).toBeGreaterThan(b.score!);
    expect(a.statusClass).toBe("measured");
  });

  it("leaves a sub-score null (honest gap) when an input is not_disclosed, not a fabricated sector mean", () => {
    const companies = [
      makeCompany("A", "Energy", {
        scope1_tco2e: field(0, "not_disclosed", 0),
        revenue_usd: field(1_000_000),
      }),
      makeCompany("B", "Energy", { scope1_tco2e: field(500), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_carbon_intensity")!;
    expect(a.statusClass).toBe("unavailable");
    expect(a.rawValue).toBeNull();
    expect(a.score).toBeNull();
  });

  it("treats a field entirely absent from company.fields the same as not_disclosed", () => {
    const companies = [
      makeCompany("A", "Energy", { revenue_usd: field(1_000_000) }), // no scope1_tco2e at all
      makeCompany("B", "Energy", { scope1_tco2e: field(500), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_carbon_intensity")!;
    expect(a.score).toBeNull();
  });

  it("scores an imputed value against the distribution without letting it widen that distribution", () => {
    const measured = [
      makeCompany("A", "Energy", { scope1_tco2e: field(10), revenue_usd: field(1_000_000) }),
      makeCompany("B", "Energy", { scope1_tco2e: field(20), revenue_usd: field(1_000_000) }),
    ];
    const imputedCo = makeCompany("C", "Energy", {
      scope1_tco2e: field(15, "imputed", 0.3),
      revenue_usd: field(1_000_000, "imputed", 0.3),
    });

    const withoutImputed = computeScores(measured, defaultWeights());
    const withImputed = computeScores([...measured, imputedCo], defaultWeights());

    const aWithout = withoutImputed.get("A")!.pillars.P1.subScores[0];
    const aWith = withImputed.get("A")!.pillars.P1.subScores[0];
    expect(aWith.score).toBe(aWithout.score); // C did not join the distribution

    const c = withImputed.get("C")!.pillars.P1.subScores[0];
    expect(c.statusClass).toBe("imputed");
    expect(c.rawValue).not.toBeNull(); // imputed still renders, just doesn't set the curve
    expect(c.score).not.toBeNull();
  });
});

describe("computeScores: the sector-dummy pathology", () => {
  it("gives every company in a sector the same score when the sector has zero within-sector variance", () => {
    // This is exactly the --degenerate fixture shape: one distinct value per
    // GICS sector. The scoring layer must make this visible (everyone tied
    // at 50), not paper over it.
    const companies = [
      makeCompany("A", "Energy", { scope1_tco2e: field(500), revenue_usd: field(1_000_000) }),
      makeCompany("B", "Energy", { scope1_tco2e: field(500), revenue_usd: field(1_000_000) }),
      makeCompany("C", "Energy", { scope1_tco2e: field(500), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    for (const ticker of ["A", "B", "C"]) {
      const s = scores.get(ticker)!.pillars.P1.subScores.find((x) => x.id === "p1_carbon_intensity")!;
      expect(s.score).toBe(50);
    }
  });
});

describe("computeScores: aggregation", () => {
  it("weighted pillar mean renormalises when a sub-score is unavailable, not defaulting it to zero", () => {
    const companies = [
      makeCompany("A", "Health Care", {
        scope1_tco2e: field(100),
        revenue_usd: field(1_000_000),
        // renewable/total electricity and waste_diverted_pct: all missing
      }),
      makeCompany("B", "Health Care", {
        scope1_tco2e: field(900),
        revenue_usd: field(1_000_000),
      }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const p1 = scores.get("A")!.pillars.P1;
    const onlyDefinedSub = p1.subScores.find((s) => s.id === "p1_carbon_intensity")!;
    // Only one of three P1 sub-scores has data; the pillar score must equal
    // that one sub-score's value, not be dragged down by the two nulls.
    expect(p1.score).toBeCloseTo(onlyDefinedSub.score!);
  });

  it("composite responds to pillar weights", () => {
    const companies = [
      makeCompany("A", "Health Care", { scope1_tco2e: field(100), revenue_usd: field(1_000_000) }),
      makeCompany("B", "Health Care", { scope1_tco2e: field(900), revenue_usd: field(1_000_000) }),
    ];
    const p1Heavy: WeightsState = { pillars: { P1: 10, P2: 0.001, P3: 0.001 }, subscores: {} };
    const scores = computeScores(companies, p1Heavy);
    const a = scores.get("A")!;
    // With P1 weighted to dominate and A the better P1 performer, A's
    // composite should track its P1 score closely.
    expect(Math.abs(a.composite! - a.pillars.P1.score!)).toBeLessThan(1);
  });
});

describe("resolveInputs: nullPolicy 'zero'", () => {
  const zeroPolicySub: SubScoreDef = {
    id: "test_zero",
    pillar: "P3",
    label: "test",
    polarity: "lower_is_better",
    inputs: ["penalty_count"],
    compute: (f) => f.penalty_count,
    nullPolicy: "zero",
    basis: "FY2023",
  };

  it("fills a missing input with a literal 0 but still marks the point unavailable/hollow", () => {
    const company = makeCompany("A", "Energy", {});
    const r = resolveInputs(company, zeroPolicySub);
    expect(r.statusClass).toBe("unavailable");
    expect(r.inputs).toEqual({ penalty_count: 0 });
  });
});

describe("resolveInputs: nullPolicy 'sector_median' (via computeScores)", () => {
  const medianPolicySub: SubScoreDef = {
    id: "test_median",
    pillar: "P3",
    label: "test",
    polarity: "higher_is_better",
    inputs: ["independent_director_count"],
    compute: (f) => f.independent_director_count,
    nullPolicy: "sector_median",
    basis: "FY2023",
  };

  it("substitutes the sector median and scores at ~50 when the input is missing", () => {
    const companies = [
      makeCompany("A", "Energy", { independent_director_count: field(4) }),
      makeCompany("B", "Energy", { independent_director_count: field(8) }),
      makeCompany("C", "Energy", {}), // missing entirely
    ];
    const scores = computeScores(companies, defaultWeights(), [medianPolicySub]);
    const c = scores.get("C")!.pillars.P3.subScores[0];
    expect(c.rawValue).toBe(6); // median(4, 8)
    expect(c.score).toBe(50);
  });
});
