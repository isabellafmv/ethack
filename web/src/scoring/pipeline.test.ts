import { describe, expect, it } from "vitest";
import {
  aggregateWithDisclosurePenalty,
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
        // grid_intensity, cogs_usd: missing. waste_diverted_pct is missing
        // too, but p1_resource_waste is gapKind 'pipeline_gap' -- excluded
        // from disclosure coverage below, same as this renormalized mean.
      }),
      makeCompany("B", "Health Care", {
        scope1_tco2e: field(900),
        revenue_usd: field(1_000_000),
      }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const p1 = scores.get("A")!.pillars.P1;
    const onlyDefinedSub = p1.subScores.find((s) => s.id === "p1_carbon_intensity")!;
    // Only one of four P1 sub-scores has data; the RAW pillar score must
    // equal that one sub-score's value, not be dragged down by the nulls.
    expect(p1.scoreRaw).toBeCloseTo(onlyDefinedSub.score!);
  });

  it("applies the disclosure-coverage penalty on top of the raw pillar score, excluding pipeline-gap sub-scores", () => {
    const companies = [
      makeCompany("A", "Health Care", {
        scope1_tco2e: field(100),
        revenue_usd: field(1_000_000),
        // P1 has 3 disclosure-gap sub-scores (carbon_intensity, energy_mix,
        // input_efficiency) and 1 pipeline-gap one (resource_waste, which
        // doesn't count against coverage at all). Only carbon_intensity is
        // present here, so disclosure coverage = 1 of 3 = 1/3.
      }),
      makeCompany("B", "Health Care", { scope1_tco2e: field(900), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const p1 = scores.get("A")!.pillars.P1;
    expect(p1.disclosureCoverage).toBeCloseTo(1 / 3);
    expect(p1.score).toBeCloseTo(p1.scoreRaw! * (0.6 + 0.4 * (1 / 3)));
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

describe("computeScores: p1_input_efficiency (real registry sub-score)", () => {
  it("scores a lower COGS/revenue ratio higher (lower_is_better)", () => {
    const companies = [
      makeCompany("A", "Energy", { cogs_usd: field(200_000), revenue_usd: field(1_000_000) }),
      makeCompany("B", "Energy", { cogs_usd: field(800_000), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_input_efficiency")!;
    const b = scores.get("B")!.pillars.P1.subScores.find((s) => s.id === "p1_input_efficiency")!;
    expect(a.score!).toBeGreaterThan(b.score!);
  });

  it("stays null when cogs_usd is absent", () => {
    const companies = [
      makeCompany("A", "Energy", { revenue_usd: field(1_000_000) }),
      makeCompany("B", "Energy", { cogs_usd: field(500_000), revenue_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_input_efficiency")!;
    expect(a.statusClass).toBe("unavailable");
    expect(a.score).toBeNull();
  });
});

describe("computeScores: p3_capital_stewardship (real registry sub-score, optionalInputs)", () => {
  it("computes the reinvestment share when all four fields are present", () => {
    const companies = [
      makeCompany("A", "Industrials", {
        capex_usd: field(400), rnd_expense_usd: field(100),
        buybacks_usd: field(300), dividends_paid_usd: field(200),
      }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_capital_stewardship")!;
    // reinvestment = 400+100 = 500; total = 500+300+200 = 1000 -> 50%
    expect(a.rawValue).toBeCloseTo(50);
  });

  it("treats absent optional fields as a real zero, not a gap -- score still computes", () => {
    const companies = [
      makeCompany("A", "Industrials", { capex_usd: field(400) }), // rnd/buybacks/dividends all absent
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_capital_stewardship")!;
    // reinvestment = 400+0 = 400; total = 400+0+0 = 400 -> 100%
    expect(a.statusClass).toBe("measured");
    expect(a.rawValue).toBeCloseTo(100);
  });

  it("is null when the required capex_usd is absent, even with every optional field present", () => {
    const companies = [
      makeCompany("A", "Industrials", {
        rnd_expense_usd: field(100), buybacks_usd: field(300), dividends_paid_usd: field(200),
      }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_capital_stewardship")!;
    expect(a.statusClass).toBe("unavailable");
    expect(a.score).toBeNull();
  });

  it("is null when total <= 0 despite capex_usd being genuinely present", () => {
    const companies = [
      makeCompany("A", "Industrials", { capex_usd: field(0) }), // present, but zero, and nothing else
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_capital_stewardship")!;
    expect(a.statusClass).toBe("measured"); // capex_usd IS disclosed -- it's just zero
    expect(a.rawValue).toBeNull(); // but the ratio is undefined, so no score is invented
  });
});

describe("computeScores: p2_regulatory_momentum (real registry sub-score, sector_median nullPolicy)", () => {
  it("scores a company with no stated target against the sector's median target strength, not as a neutral gap", () => {
    const companies = [
      makeCompany("A", "Energy", { target_reduction_pct: field(30), sbti_target_validated: field(true) }), // 30
      makeCompany("B", "Energy", { target_reduction_pct: field(50), sbti_target_validated: field(false) }), // 35
      makeCompany("C", "Energy", {}), // no target at all
    ];
    const scores = computeScores(companies, defaultWeights());
    const c = scores.get("C")!.pillars.P2.subScores.find((s) => s.id === "p2_regulatory_momentum")!;
    expect(c.statusClass).toBe("unavailable"); // genuinely undisclosed...
    expect(c.rawValue).toBeCloseTo(32.5); // ...but median(30, 35), not null
    expect(c.score).toBe(50); // falls exactly between its two sector peers
  });
});

describe("computeScores: p2_carbon_price_exposure (real registry sub-score, ceiling mapping)", () => {
  it("maps 0% EBITDA erosion to best and >=50% erosion to worst, pre-percentile", () => {
    const companies = [
      makeCompany("A", "Energy", { scope1_tco2e: field(0), ebitda_usd: field(1_000_000) }),
      makeCompany("B", "Energy", { scope1_tco2e: field(500_000), ebitda_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P2.subScores.find((s) => s.id === "p2_carbon_price_exposure")!;
    const b = scores.get("B")!.pillars.P2.subScores.find((s) => s.id === "p2_carbon_price_exposure")!;
    expect(a.rawValue).toBeCloseTo(100); // 0% erosion
    expect(b.rawValue).toBeCloseTo(0); // 50% erosion, at the ceiling
    expect(a.score!).toBeGreaterThan(b.score!); // higher_is_better on the already-oriented value
  });

  it("applies the $100/ton assumed carbon price, not just a bare emissions-to-EBITDA ratio", () => {
    // 5,000 tCO2e at $100/ton = $500,000 carbon cost against $1,000,000
    // EBITDA -- exactly 50% erosion, i.e. exactly at the ceiling (score 0).
    // A version of this formula missing the price multiplier (an actual bug
    // this sub-score once had) would read this as 0.5% erosion and score
    // ~99, nowhere near the ceiling -- this guards against that regressing.
    const companies = [
      makeCompany("A", "Energy", { scope1_tco2e: field(5_000), ebitda_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P2.subScores.find((s) => s.id === "p2_carbon_price_exposure")!;
    expect(a.rawValue).toBeCloseTo(0);
  });

  it("is null (not a false best score) when EBITDA is negative", () => {
    const companies = [
      makeCompany("A", "Energy", { scope1_tco2e: field(100), ebitda_usd: field(-1) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P2.subScores.find((s) => s.id === "p2_carbon_price_exposure")!;
    expect(a.statusClass).toBe("measured"); // every input IS disclosed
    expect(a.rawValue).toBeNull(); // the ratio just isn't meaningful
    expect(a.score).toBeNull();
  });

  it("is unavailable when scope1_tco2e is missing, even with EBITDA present (no scope2 or modelled-tier fallback)", () => {
    const companies = [
      makeCompany("A", "Energy", { ebitda_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P2.subScores.find((s) => s.id === "p2_carbon_price_exposure")!;
    expect(a.statusClass).toBe("unavailable");
    expect(a.score).toBeNull();
  });
});

describe("computeScores: per-sector weights (Map<string, WeightsState>)", () => {
  const energy = [
    makeCompany("A", "Energy", {
      scope1_tco2e: field(100), revenue_usd: field(1_000_000),
      independent_director_count: field(2), board_size: field(8),
    }),
    makeCompany("B", "Energy", {
      scope1_tco2e: field(900), revenue_usd: field(1_000_000),
      independent_director_count: field(2), board_size: field(8),
    }),
  ];
  const financials = [
    makeCompany("C", "Financials", {
      scope1_tco2e: field(900), revenue_usd: field(1_000_000),
      independent_director_count: field(8), board_size: field(8),
    }),
    makeCompany("D", "Financials", {
      scope1_tco2e: field(100), revenue_usd: field(1_000_000),
      independent_director_count: field(2), board_size: field(8),
    }),
  ];
  const utilities = [
    makeCompany("U1", "Utilities", {
      scope1_tco2e: field(100), revenue_usd: field(1_000_000), // strong P1
      independent_director_count: field(2), board_size: field(8), // weak P3
    }),
    makeCompany("U2", "Utilities", {
      scope1_tco2e: field(900), revenue_usd: field(1_000_000), // weak P1
      independent_director_count: field(8), board_size: field(8), // strong P3
    }),
  ];
  const companies = [...energy, ...financials, ...utilities];

  const p1Heavy: WeightsState = { pillars: { P1: 10, P2: 0.001, P3: 0.001 }, subscores: {} };
  const p3Heavy: WeightsState = { pillars: { P1: 0.001, P2: 0.001, P3: 10 }, subscores: {} };

  it("applies each sector's own weights to that sector's companies", () => {
    const weights = new Map([["Energy", p1Heavy], ["Financials", p3Heavy]]);
    const scores = computeScores(companies, weights);
    const a = scores.get("A")!;
    const c = scores.get("C")!;
    // A is Energy's better P1 performer, weighted P1-heavy there.
    expect(Math.abs(a.composite! - a.pillars.P1.score!)).toBeLessThan(1);
    // C is Financials' better P3 performer, weighted P3-heavy there.
    expect(Math.abs(c.composite! - c.pillars.P3.score!)).toBeLessThan(1);
  });

  it("falls back to defaultWeights() for a sector absent from the map", () => {
    const weights = new Map([["Energy", p1Heavy], ["Financials", p3Heavy]]); // Utilities absent
    const viaMap = computeScores(companies, weights);
    const viaDefault = computeScores(companies, defaultWeights());
    expect(viaMap.get("U1")).toEqual(viaDefault.get("U1"));
    expect(viaMap.get("U2")).toEqual(viaDefault.get("U2"));
  });

  it("a Map with the same WeightsState for every sector is equivalent to passing that WeightsState bare", () => {
    const sameEverywhere = new Map([["Energy", p1Heavy], ["Financials", p1Heavy], ["Utilities", p1Heavy]]);
    const viaMap = computeScores(companies, sameEverywhere);
    const viaBare = computeScores(companies, p1Heavy);
    expect(viaMap).toEqual(viaBare);
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

describe("aggregateWithDisclosurePenalty", () => {
  it("is a no-op (score === scoreRaw) when every disclosure-gap entry is present", () => {
    const result = aggregateWithDisclosurePenalty([
      { id: "a", value: 80, weight: 1, disclosed: true },
      { id: "b", value: 40, weight: 1, disclosed: true },
    ]);
    expect(result.disclosureCoverage).toBe(1);
    expect(result.score).toBeCloseTo(result.scoreRaw!);
    expect(result.scoreRaw).toBeCloseTo(60);
  });

  it("floors at 0.6x the raw score when every disclosure-gap entry is missing", () => {
    const result = aggregateWithDisclosurePenalty([
      { id: "a", value: null, weight: 1, disclosed: false },
      { id: "b", value: 100, weight: 1, disclosed: false },
    ]);
    expect(result.disclosureCoverage).toBe(0);
    expect(result.scoreRaw).toBeCloseTo(100); // renormalizes around the one present value
    expect(result.score).toBeCloseTo(60); // 100 * (0.6 + 0.4*0)
  });

  it("excludes pipeline-gap entries from the coverage ratio entirely", () => {
    const result = aggregateWithDisclosurePenalty([
      { id: "a", value: 90, weight: 1, disclosed: true },
      { id: "pipeline", value: null, weight: 1, disclosed: false, gapKind: "pipeline_gap" },
    ]);
    // Only "a" (disclosure-gap) counts toward coverage, and it's present.
    expect(result.disclosureCoverage).toBe(1);
    expect(result.score).toBeCloseTo(result.scoreRaw!);
  });

  it("treats a nullPolicy-substituted value as NOT disclosed for coverage even though it produced a score", () => {
    const result = aggregateWithDisclosurePenalty([
      { id: "a", value: 70, weight: 1, disclosed: true },
      { id: "b", value: 50, weight: 1, disclosed: false }, // e.g. sector_median substitution
    ]);
    expect(result.disclosureCoverage).toBeCloseTo(0.5);
    expect(result.scoreRaw).toBeCloseTo(60); // both values count toward the raw mean
    expect(result.score).toBeCloseTo(60 * 0.8); // 0.6 + 0.4*0.5
  });

  it("returns null score/scoreRaw when nothing is available at all", () => {
    const result = aggregateWithDisclosurePenalty([{ id: "a", value: null, weight: 1, disclosed: false }]);
    expect(result.scoreRaw).toBeNull();
    expect(result.score).toBeNull();
  });
});

describe("computeScores: p1_energy_mix (real registry sub-score, grid-intensity regional proxy)", () => {
  it("scores lower grid carbon intensity higher (lower_is_better)", () => {
    const companies = [
      makeCompany("A", "Utilities", { grid_intensity_kgco2e_per_mwh: field(200) }),
      makeCompany("B", "Utilities", { grid_intensity_kgco2e_per_mwh: field(800) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_energy_mix")!;
    const b = scores.get("B")!.pillars.P1.subScores.find((s) => s.id === "p1_energy_mix")!;
    expect(a.score!).toBeGreaterThan(b.score!);
  });

  it("is null when a non-US-headquartered company has no grid to map to", () => {
    const companies = [
      makeCompany("A", "Utilities", {}), // no grid_intensity_kgco2e_per_mwh
      makeCompany("B", "Utilities", { grid_intensity_kgco2e_per_mwh: field(500) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P1.subScores.find((s) => s.id === "p1_energy_mix")!;
    expect(a.statusClass).toBe("unavailable");
    expect(a.score).toBeNull();
  });
});

describe("computeScores: p3_exec_compensation (real registry sub-score, compensation alignment)", () => {
  it("means the two booleans and the capped performance period", () => {
    const companies = [
      makeCompany("A", "Financials", {
        has_clawback_policy: field(true),
        has_psu_plan: field(true),
        performance_period_years: field(3), // capped at 3 -> 100
      }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_exec_compensation")!;
    // (100 + 100 + 100) / 3 = 100
    expect(a.rawValue).toBeCloseTo(100);
  });

  it("caps performance_period_years at 3 -- a longer period doesn't score above 100", () => {
    const companies = [
      makeCompany("A", "Financials", {
        has_clawback_policy: field(false),
        has_psu_plan: field(false),
        performance_period_years: field(10), // clipped to 3 -> 100
      }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_exec_compensation")!;
    // (0 + 0 + 100) / 3 = 33.33
    expect(a.rawValue).toBeCloseTo(100 / 3);
  });

  it("is unavailable (not silently scored) now that the dead comp_tied_to_emissions_target field is gone", () => {
    const companies = [
      makeCompany("A", "Financials", { has_clawback_policy: field(true), has_psu_plan: field(true) }),
      // performance_period_years missing -- this sub-score used to require a
      // field (comp_tied_to_emissions_target) that real data never has at
      // all, making it permanently unavailable; it must not still gate on a
      // field the pipeline can actually supply.
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_exec_compensation")!;
    expect(a.statusClass).toBe("unavailable");
    expect(a.score).toBeNull();
  });
});

describe("computeScores: p3_controversy_flags (real registry sub-score, penalty dollar total)", () => {
  it("scores a lower penalty total higher (lower_is_better)", () => {
    const companies = [
      makeCompany("A", "Industrials", { penalty_total_usd: field(0) }),
      makeCompany("B", "Industrials", { penalty_total_usd: field(1_000_000) }),
    ];
    const scores = computeScores(companies, defaultWeights());
    const a = scores.get("A")!.pillars.P3.subScores.find((s) => s.id === "p3_controversy_flags")!;
    const b = scores.get("B")!.pillars.P3.subScores.find((s) => s.id === "p3_controversy_flags")!;
    expect(a.score!).toBeGreaterThan(b.score!);
  });
});
