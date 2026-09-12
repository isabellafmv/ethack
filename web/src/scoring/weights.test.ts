import { describe, expect, it } from "vitest";
import { defaultWeights } from "./pipeline";
import {
  applyPreset, decodeWeightModeFromHash, decodeWeightsFromHash,
  encodeWeightModeToHash, encodeWeightsToHash, PRESETS,
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
