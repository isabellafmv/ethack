import { describe, expect, it } from "vitest";
import { defaultWeights } from "./pipeline";
import { applyPreset, decodeWeightsFromHash, encodeWeightsToHash, PRESETS } from "./weights";

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
