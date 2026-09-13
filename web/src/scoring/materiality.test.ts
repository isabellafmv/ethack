import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertIndicatorColumnsKnown,
  deriveMaterialityWeights,
  INDICATOR_TO_SUBSCORE,
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
  it("maps only the 4 P1 indicator columns -- P2/P3 use Python's fixed WEIGHTS dicts instead", () => {
    expect(INDICATOR_TO_SUBSCORE).toEqual({
      carbon_intensity: "p1_carbon_intensity",
      energy_mix: "p1_energy_mix",
      resource_waste_intensity: "p1_resource_waste",
      input_efficiency: "p1_input_efficiency",
    });
  });
});

describe("deriveMaterialityWeights", () => {
  it("only ever produces the 4 mapped P1 sub-score weights -- no P2/P3 keys leak in", () => {
    const out = deriveMaterialityWeights([row()]);
    const sector = out.TestSector;
    expect(new Set(Object.keys(sector.subscores))).toEqual(new Set(Object.values(INDICATOR_TO_SUBSCORE)));
    expect(UNMAPPED_INDICATORS.size).toBe(9);
  });

  it("pillars are always the flat {P1:1, P2:1, P3:1} regardless of the sector's CSV weights", () => {
    const energy = row({
      sector: "Energy",
      carbon_intensity: "18", energy_mix: "4", resource_waste_intensity: "4", input_efficiency: "6",
    });
    const financials = row({
      sector: "Financials",
      carbon_intensity: "4", energy_mix: "4", resource_waste_intensity: "2", input_efficiency: "3",
    });
    const out = deriveMaterialityWeights([energy, financials]);
    expect(out.Energy.pillars).toEqual({ P1: 1, P2: 1, P3: 1 });
    expect(out.Financials.pillars).toEqual({ P1: 1, P2: 1, P3: 1 });
  });

  it("reads each P1 sub-score's weight straight from its CSV column, per sector", () => {
    const energy = row({
      sector: "Energy",
      carbon_intensity: "18", energy_mix: "4", resource_waste_intensity: "4", input_efficiency: "6",
    });
    const out = deriveMaterialityWeights([energy]);
    expect(out.Energy.subscores).toEqual({
      p1_carbon_intensity: 18,
      p1_energy_mix: 4,
      p1_resource_waste: 4,
      p1_input_efficiency: 6,
    });
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
