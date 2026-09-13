import { describe, expect, it } from "vitest";
import { defaultWeights, normalizedWeights } from "./pipeline";
import { PYTHON_P2_WEIGHTS, PYTHON_P3_WEIGHTS } from "./registry";
import {
  applyPreset, decodeWeightModeFromHash, decodeWeightsFromHash,
  encodeWeightModeToHash, encodeWeightsToHash, PRESETS, pythonDefaultWeights,
} from "./weights";

describe("presets", () => {
  it("environmental-led weighs P1 above the other two", () => {
    const w = applyPreset("environmental_led", defaultWeights());
    expect(w.pillars.P1!).toBeGreaterThan(w.pillars.P2!);
    expect(w.pillars.P1!).toBeGreaterThan(w.pillars.P3!);
  });

  it("equal preset weighs every pillar the same", () => {
    const w = applyPreset("equal", defaultWeights());
    expect(w.pillars.P1).toBe(w.pillars.P2);
    expect(w.pillars.P2).toBe(w.pillars.P3);
  });

  it("applying a preset preserves the caller's sub-score weights", () => {
    const current = defaultWeights();
    current.subscores["p1_carbon_intensity"] = 7;
    const w = applyPreset("governance_led", current);
    expect(w.subscores["p1_carbon_intensity"]).toBe(7);
  });

  it("every preset id has a label", () => {
    for (const id of Object.keys(PRESETS) as (keyof typeof PRESETS)[]) {
      expect(PRESETS[id].label.length).toBeGreaterThan(0);
    }
  });
});

describe("URL hash persistence", () => {
  it("round-trips a weight configuration through the hash", () => {
    const w = defaultWeights();
    w.pillars.P1 = 3;
    w.pillars.P2 = 1;
    w.pillars.P3 = 0.5;
    w.subscores["p1_carbon_intensity"] = 2;

    const hash = encodeWeightsToHash(w);
    const decoded = decodeWeightsFromHash(hash);

    expect(decoded).not.toBeNull();
    expect(decoded!.pillars.P1).toBeCloseTo(3);
    expect(decoded!.pillars.P2).toBeCloseTo(1);
    expect(decoded!.pillars.P3).toBeCloseTo(0.5);
    expect(decoded!.subscores["p1_carbon_intensity"]).toBeCloseTo(2);
  });

  it("returns null for a hash with no weight segment", () => {
    expect(decodeWeightsFromHash("#somethingElse=1")).toBeNull();
  });

  it("ignores unrecognised keys instead of throwing -- a stale shared link must not crash the app", () => {
    expect(() => decodeWeightsFromHash("#w=NOT_A_REAL_ID%3A5")).not.toThrow();
  });
});

describe("weight mode persistence", () => {
  it("round-trips manual and materiality mode through the hash", () => {
    expect(decodeWeightModeFromHash(encodeWeightModeToHash("materiality"))).toBe("materiality");
    expect(decodeWeightModeFromHash(encodeWeightModeToHash("manual"))).toBe("manual");
  });

  it("a hash with no mode segment decodes to manual -- old shared links keep working", () => {
    expect(decodeWeightModeFromHash("#w=P1:1,P2:1,P3:1")).toBe("manual");
    expect(decodeWeightModeFromHash("")).toBe("manual");
  });

  it("manual mode encodes to an empty segment, keeping manual-mode URLs unchanged", () => {
    expect(encodeWeightModeToHash("manual")).toBe("");
  });
});

describe("pythonDefaultWeights", () => {
  const sectorWeights = {
    Energy: { pillars: { P1: 1, P2: 1, P3: 1 }, subscores: { p1_carbon_intensity: 18, p1_energy_mix: 4 }, rationale: "why" },
    Financials: { pillars: { P1: 1, P2: 1, P3: 1 }, subscores: { p1_carbon_intensity: 4, p1_energy_mix: 4 }, rationale: "why not" },
  };

  it("keeps pillar weights flat/equal for every sector, matching final_score.py's fixed 1/3 split", () => {
    const out = pythonDefaultWeights(sectorWeights);
    for (const sector of out.values()) expect(sector.pillars).toEqual({ P1: 1, P2: 1, P3: 1 });
  });

  it("overlays Python's fixed P2/P3 WEIGHTS onto every sector, identically", () => {
    const out = pythonDefaultWeights(sectorWeights);
    for (const sector of out.values()) {
      for (const [id, w] of Object.entries(PYTHON_P2_WEIGHTS)) expect(sector.subscores[id]).toBe(w);
      for (const [id, w] of Object.entries(PYTHON_P3_WEIGHTS)) expect(sector.subscores[id]).toBe(w);
    }
  });

  it("keeps each sector's own P1 sub-score weights, not shared across sectors", () => {
    const out = pythonDefaultWeights(sectorWeights);
    expect(out.get("Energy")!.subscores.p1_carbon_intensity).toBe(18);
    expect(out.get("Financials")!.subscores.p1_carbon_intensity).toBe(4);
  });

  it("passes through the rationale per sector", () => {
    const out = pythonDefaultWeights(sectorWeights);
    expect(out.get("Energy")!.rationale).toBe("why");
  });

  it("normalizes P2's fixed weights to exactly Python's own proportions once run through normalizedWeights", () => {
    const out = pythonDefaultWeights(sectorWeights);
    const { subscores } = normalizedWeights(out.get("Energy")!);
    const p2Total = Object.values(PYTHON_P2_WEIGHTS).reduce((a, b) => a + b, 0);
    for (const [id, w] of Object.entries(PYTHON_P2_WEIGHTS)) {
      expect(subscores[id]).toBeCloseTo(w / p2Total);
    }
  });
});
