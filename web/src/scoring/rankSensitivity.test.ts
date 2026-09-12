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

describe("rankSensitivity: per-sector weights (Map<string, WeightsState>)", () => {
  function richCompany(ticker: string, sector: string, p1Value: number, p3Value: number): Company {
    return {
      ticker, name: ticker, sector, sub_industry: "",
      fields: {
        scope1_tco2e: field(p1Value), revenue_usd: field(1_000_000),
        independent_director_count: field(p3Value), board_size: field(10),
      },
      alternatives: {}, confidence: 1,
    };
  }

  it("applies the same per-sample per-pillar jitter factor across every sector, not one independent draw per sector", () => {
    // Energy's raw weights are exactly 2x Materials' -- proportional, so
    // normalizedWeights() is IDENTICAL for both sectors regardless of scale.
    // A shared jitter factor keeps that identity true on every sample; an
    // independent-per-sector jitter would (almost certainly, over 20
    // samples) break it.
    const proportional = new Map([
      ["Energy", { pillars: { P1: 2, P2: 2, P3: 2 }, subscores: {} }],
      ["Materials", { pillars: { P1: 1, P2: 1, P3: 1 }, subscores: {} }],
    ]);
    const companies = [
      richCompany("A", "Energy", 100, 2), // good P1, weak P3
      richCompany("B", "Energy", 900, 8), // weak P1, good P3
      richCompany("C", "Materials", 100, 2), // same pattern as A
      richCompany("D", "Materials", 900, 8), // same pattern as B
    ];
    const spreads = rankSensitivity(companies, proportional, { seed: 5, samples: 20 });
    expect(spreads.get("A")!.spread).toBe(spreads.get("C")!.spread);
    expect(spreads.get("B")!.spread).toBe(spreads.get("D")!.spread);
  });

  it("is deterministic for a fixed seed", () => {
    const weights = new Map([
      ["Energy", defaultWeights()],
      ["Health Care", { pillars: { P1: 3, P2: 1, P3: 1 }, subscores: {} }],
    ]);
    const companies = [
      makeCompany("A", "Energy", 100, 1_000_000),
      makeCompany("B", "Energy", 200, 1_000_000),
      makeCompany("C", "Health Care", 300, 2_000_000),
    ];
    const r1 = rankSensitivity(companies, weights, { seed: 42, samples: 10 });
    const r2 = rankSensitivity(companies, weights, { seed: 42, samples: 10 });
    expect(r1).toEqual(r2);
  });
});
