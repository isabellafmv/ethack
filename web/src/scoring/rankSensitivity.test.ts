import { describe, expect, it } from "vitest";
import { defaultWeights } from "./pipeline";
import { rankSensitivity } from "./rankSensitivity";
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

describe("rankSensitivity", () => {
  it("is deterministic for a fixed seed", () => {
    const companies = [
      makeCompany("A", "Energy", 100, 1_000_000),
      makeCompany("B", "Energy", 200, 1_000_000),
      makeCompany("C", "Energy", 300, 1_000_000),
    ];
    const r1 = rankSensitivity(companies, defaultWeights(), { seed: 42, samples: 10 });
    const r2 = rankSensitivity(companies, defaultWeights(), { seed: 42, samples: 10 });
    expect(r1.get("A")).toEqual(r2.get("A"));
  });

  it("reports zero spread when only one pillar has any data at all -- nothing else can move the rank", () => {
    const companies = [
      makeCompany("A", "Energy", 100, 1_000_000),
      makeCompany("B", "Energy", 900, 1_000_000),
    ];
    const spreads = rankSensitivity(companies, defaultWeights(), { seed: 1, samples: 20 });
    // Perturbing P2/P3 weights cannot change a ranking that only P1 can see.
    expect(spreads.get("A")!.spread).toBe(0);
    expect(spreads.get("B")!.spread).toBe(0);
  });

  it("gives every ranked company a spread entry", () => {
    const companies = [
      makeCompany("A", "Energy", 100, 1_000_000),
      makeCompany("B", "Energy", 500, 1_000_000),
      makeCompany("C", "Health Care", 300, 2_000_000),
    ];
    const spreads = rankSensitivity(companies, defaultWeights(), { seed: 7 });
    expect(spreads.size).toBe(3);
    for (const s of spreads.values()) {
      expect(s.minRank).toBeLessThanOrEqual(s.baseRank);
      expect(s.maxRank).toBeGreaterThanOrEqual(s.baseRank);
    }
  });
});
