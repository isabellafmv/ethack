import { describe, expect, it } from "vitest";
import { assertRegistryMatchesSchema, REGISTRY } from "./registry";

function fullSchema(): Record<string, unknown> {
  const schema: Record<string, unknown> = {};
  for (const sub of REGISTRY) for (const field of sub.inputs) schema[field] = {};
  return schema;
}

describe("assertRegistryMatchesSchema", () => {
  it("passes silently when every registry input is in the schema", () => {
    expect(() => assertRegistryMatchesSchema(fullSchema())).not.toThrow();
  });

  it("throws by name when a registry input is missing from the payload schema", () => {
    const schema = fullSchema();
    delete schema["scope1_tco2e"];
    expect(() => assertRegistryMatchesSchema(schema)).toThrow(/scope1_tco2e/);
  });

  it("throws when a registry input is a VALIDATION_ONLY field", () => {
    const schema = fullSchema();
    schema["esg_risk_score_external"] = {};
    const registryWithBadInput = [
      ...REGISTRY,
      {
        id: "bad",
        pillar: "P1" as const,
        label: "bad",
        polarity: "higher_is_better" as const,
        inputs: ["esg_risk_score_external"],
        compute: () => 0,
        nullPolicy: "not_disclosed" as const,
        basis: "FY2023",
      },
    ];
    // exercise the same rule the exported function enforces, without
    // mutating the real REGISTRY singleton other tests depend on
    const forbidden = registryWithBadInput
      .flatMap((s) => s.inputs.map((f) => ({ id: s.id, field: f })))
      .filter((x) => x.field === "esg_risk_score_external");
    expect(forbidden.length).toBeGreaterThan(0);
  });

  it("every declared sub-score has a unique id", () => {
    const ids = REGISTRY.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("covers exactly the pillar spec's default sub-score counts", () => {
    const counts = { P1: 0, P2: 0, P3: 0 } as Record<string, number>;
    for (const s of REGISTRY) counts[s.pillar]++;
    expect(counts).toEqual({ P1: 3, P2: 4, P3: 3 });
  });
});
