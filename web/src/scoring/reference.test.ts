import { describe, expect, it } from "vitest";
import { computeScores, defaultWeights } from "./pipeline";
import { referenceDelta, referenceLabel, resolveReference } from "./reference";
import type { Company, FieldRecord } from "./types";

function field(v: number): FieldRecord {
  return { v, u: null, fy: 2023, src: "S01", st: "structural", c: 1, url: 0 };
}

function makeCompany(ticker: string, sector: string, scope1: number, revenue: number): Company {
  return {
    ticker,
    name: ticker,
    sector,
    sub_industry: "",
    fields: { scope1_tco2e: field(scope1), revenue_usd: field(revenue) },
    alternatives: {},
    confidence: 1,
  };
}

const companies = [
  makeCompany("A", "Energy", 10, 1_000_000),
  makeCompany("B", "Energy", 20, 1_000_000),
  makeCompany("C", "Energy", 30, 1_000_000),
];

describe("resolveReference", () => {
  it("sector_median percentile-ranks against the same CDF-style distribution scores use", () => {
    // dist = [10, 20, 30]; median = 20; count(<=20)/3 = 2/3 -> pct 0.6667 ->
    // 100*(1-0.6667) for lower_is_better. Mirrors percentileRank's
    // _sector_percentile_vs_measured formula exactly -- not a round 50.
    const ref = resolveReference(companies, { mode: "sector_median" }, "Energy");
    const carbon = ref.get("p1_carbon_intensity")!;
    expect(carbon.score).toBeCloseTo(100 / 3);
  });

  it("sector_best resolves to the polarity-correct extreme (lowest intensity, since lower is better)", () => {
    // Even the best value in a 3-element distribution doesn't land at
    // exactly 100 under the CDF formula: count(<=10)/3 = 1/3 -> pct 0.333 ->
    // 100*(1-0.333) = 66.67. A real property of the ported Python formula.
    const ref = resolveReference(companies, { mode: "sector_best" }, "Energy");
    const carbon = ref.get("p1_carbon_intensity")!;
    expect(carbon.raw).toBeCloseTo(10); // A's intensity is the lowest, hence best
    expect(carbon.score).toBeCloseTo(200 / 3);
  });

  it("a named company's own value round-trips as the reference", () => {
    const ref = resolveReference(companies, { mode: "company", companyTicker: "B" }, "Energy");
    const carbon = ref.get("p1_carbon_intensity")!;
    expect(carbon.raw).toBeCloseTo(20);
  });

  it("index_median pools every sector, not just the one passed in", () => {
    const crossSector = [
      ...companies,
      makeCompany("D", "Health Care", 1000, 1_000_000),
      makeCompany("E", "Health Care", 2000, 1_000_000),
    ];
    const bySector = resolveReference(crossSector, { mode: "sector_median" }, "Energy");
    const byIndex = resolveReference(crossSector, { mode: "index_median" }, "Energy");
    expect(byIndex.get("p1_carbon_intensity")!.raw).not.toBe(bySector.get("p1_carbon_intensity")!.raw);
  });
});

describe("referenceDelta", () => {
  it("sector_adjusted delta is symmetric around the sector median reference", () => {
    const scores = computeScores(companies, defaultWeights());
    const ref = resolveReference(companies, { mode: "sector_median" }, "Energy");
    const aScore = scores.get("A")!.pillars.P1.subScores[0];
    const cScore = scores.get("C")!.pillars.P1.subScores[0];
    const refVal = ref.get("p1_carbon_intensity")!;

    const deltaA = referenceDelta(aScore.rawValue, aScore.score, refVal, "lower_is_better", "sector_adjusted");
    const deltaC = referenceDelta(cScore.rawValue, cScore.score, refVal, "lower_is_better", "sector_adjusted");
    expect(deltaA).toBeGreaterThan(0); // A is the best performer -> positive delta
    expect(deltaC).toBeLessThan(0); // C is the worst -> negative delta
  });

  it("returns null when either side is missing rather than fabricating a zero", () => {
    expect(referenceDelta(null, null, { raw: 5, score: 50 }, "higher_is_better", "raw")).toBeNull();
  });
});

describe("referenceLabel", () => {
  it("names the mode for a company reference so raw vs sector-adjusted is never silent", () => {
    expect(referenceLabel({ mode: "company", companyTicker: "NVDA" }, "raw")).toBe("vs NVDA, raw");
    expect(referenceLabel({ mode: "company", companyTicker: "NVDA" }, "sector_adjusted")).toBe(
      "vs NVDA, sector-adjusted"
    );
  });

  it("labels the built-in modes plainly", () => {
    expect(referenceLabel({ mode: "sector_median" }, "raw")).toBe("vs sector median");
    expect(referenceLabel({ mode: "index_median" }, "raw")).toBe("vs index median");
  });
});
