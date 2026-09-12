import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertIndicatorColumnsKnown,
  deriveMaterialityWeights,
  INDICATOR_TO_SUBSCORE,
  NEUTRAL_SUBSCORES,
  UNMAPPED_INDICATORS,
  type MaterialityRow,
} from "./materiality";

const __dirname = dirname(fileURLToPath(import.meta.url));

function row(overrides: Record<string, string> = {}): MaterialityRow {
  const base: MaterialityRow = {
    sector: "TestSector",
    rationale: "because",
    carbon_intensity: "10", energy_mix: "5", resource_waste_intensity: "5", input_efficiency: "5",
    carbon_price_exposure: "10", transition_affordability: "10", innovation_momentum: "5",
    structural_disruption: "5", climate_governance: "10", compensation_alignment: "5",
    board_independence: "5", capital_stewardship: "10", controversy_record: "10",
  };
  return { ...base, ...overrides };
}

describe("INDICATOR_TO_SUBSCORE", () => {
  it("maps each of the 10 known indicator columns to the correct sub-score id", () => {
    expect(INDICATOR_TO_SUBSCORE).toEqual({
      carbon_intensity: "p1_carbon_intensity",
      energy_mix: "p1_energy_mix",
      resource_waste_intensity: "p1_resource_waste",
      input_efficiency: "p1_input_efficiency",
      carbon_price_exposure: "p2_carbon_price_exposure",
      innovation_momentum: "p2_innovation",
      compensation_alignment: "p3_exec_compensation",
      board_independence: "p3_board_independence",
      capital_stewardship: "p3_capital_stewardship",
      controversy_record: "p3_controversy_flags",
    });
  });
});

describe("deriveMaterialityWeights", () => {
  it("puts the 3 unmapped indicators' weight mass nowhere in the output", () => {
    const out = deriveMaterialityWeights([row()]);
    const sector = out.TestSector;
    // The subscores object's keys are exactly the mapped sub-score ids plus
    // the two neutral defaults -- none of the three unmapped indicators
    // (transition_affordability, structural_disruption, climate_governance)
    // contribute a key, a value, or a share of any pillar sum.
    const expectedKeys = new Set([...Object.values(INDICATOR_TO_SUBSCORE), ...NEUTRAL_SUBSCORES]);
    expect(new Set(Object.keys(sector.subscores))).toEqual(expectedKeys);
    expect(UNMAPPED_INDICATORS.size).toBe(3);
    const pillarTotal = sector.pillars.P1 + sector.pillars.P2 + sector.pillars.P3;
    const mappedTotal = Object.values(INDICATOR_TO_SUBSCORE)
      .map((id) => sector.subscores[id])
      .reduce((a, b) => a + b, 0);
    expect(pillarTotal).toBe(mappedTotal); // no extra mass leaked in from anywhere
  });

  it("gives the 2 unmapped P2 sub-scores the neutral default weight, excluded from the P2 pillar sum", () => {
    const out = deriveMaterialityWeights([row()]);
    const sector = out.TestSector;
    for (const id of NEUTRAL_SUBSCORES) expect(sector.subscores[id]).toBe(1);
    // P2 pillar sum should be carbon_price_exposure(10) + innovation_momentum(5) = 15,
    // NOT +1+1 for the two neutral sub-scores.
    expect(sector.pillars.P2).toBe(15);
  });

  it("pillar weight equals the sum of exactly the mapped sub-scores for that pillar, for two very different sectors", () => {
    const energy = row({
      sector: "Energy",
      carbon_intensity: "18", energy_mix: "4", resource_waste_intensity: "4", input_efficiency: "6",
      carbon_price_exposure: "16", innovation_momentum: "6",
      compensation_alignment: "3", board_independence: "2", capital_stewardship: "6", controversy_record: "3",
    });
    const financials = row({
      sector: "Financials",
      carbon_intensity: "4", energy_mix: "4", resource_waste_intensity: "2", input_efficiency: "3",
      carbon_price_exposure: "3", innovation_momentum: "8",
      compensation_alignment: "7", board_independence: "4", capital_stewardship: "20", controversy_record: "13",
    });
    const out = deriveMaterialityWeights([energy, financials]);
    expect(out.Energy.pillars.P1).toBe(18 + 4 + 4 + 6);
    expect(out.Energy.pillars.P2).toBe(16 + 6);
    expect(out.Energy.pillars.P3).toBe(3 + 2 + 6 + 3);
    expect(out.Financials.pillars.P1).toBe(4 + 4 + 2 + 3);
    expect(out.Financials.pillars.P2).toBe(3 + 8);
    expect(out.Financials.pillars.P3).toBe(7 + 4 + 20 + 13);
  });

  it("passes through the CSV rationale per sector", () => {
    const out = deriveMaterialityWeights([row({ sector: "Energy", rationale: "emissions are the product" })]);
    expect(out.Energy.rationale).toBe("emissions are the product");
  });
});

describe("assertIndicatorColumnsKnown", () => {
  it("throws by name on an unrecognized column", () => {
    const header = Object.keys(row());
    header.push("some_new_indicator");
    expect(() => assertIndicatorColumnsKnown(header)).toThrow(/some_new_indicator/);
  });

  it("throws by name when an expected column is missing", () => {
    const header = Object.keys(row()).filter((h) => h !== "capital_stewardship");
    expect(() => assertIndicatorColumnsKnown(header)).toThrow(/capital_stewardship/);
  });

  it("passes silently for the real header shape", () => {
    expect(() => assertIndicatorColumnsKnown(Object.keys(row()))).not.toThrow();
  });
});

describe("against the real data/materiality.csv", () => {
  function parseCsv(text: string): MaterialityRow[] {
    // Minimal RFC4180 parser (materiality.csv's rationale column is
    // quoted and contains commas) -- deliberately not importing from
    // web/scripts (vitest only includes src/**/*.test.ts, and this is
    // exactly the kind of small parser worth keeping dependency-free here).
    const lines: string[][] = [];
    let field = "", row: string[] = [], inQuotes = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inQuotes) {
        if (ch === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQuotes = false; }
        else field += ch;
      } else if (ch === '"') inQuotes = true;
      else if (ch === ",") { row.push(field); field = ""; }
      else if (ch === "\n") { row.push(field); field = ""; lines.push(row); row = []; }
      else if (ch !== "\r") field += ch;
    }
    if (field !== "" || row.length > 0) { row.push(field); lines.push(row); }
    const header = lines[0];
    return lines.slice(1).filter((r) => r.length === header.length).map((r) => {
      const obj: MaterialityRow = {};
      header.forEach((h, i) => (obj[h] = r[i]));
      return obj;
    });
  }

  it("produces exactly the 11 GICS sector names as keys", () => {
    const csvPath = resolve(__dirname, "..", "..", "..", "data", "materiality.csv");
    const rows = parseCsv(readFileSync(csvPath, "utf-8"));
    assertIndicatorColumnsKnown(Object.keys(rows[0]));
    const out = deriveMaterialityWeights(rows);
    expect(new Set(Object.keys(out))).toEqual(
      new Set([
        "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy", "Financials",
        "Health Care", "Industrials", "Information Technology", "Materials", "Real Estate", "Utilities",
      ])
    );
  });
});
