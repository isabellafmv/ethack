// Weight presets and URL-hash persistence. Kept separate from pipeline.ts
// because none of this touches company data -- it's pure state shaping.

import { REGISTRY, type Pillar } from "./registry";
import { defaultWeights, PILLARS, type WeightsState } from "./pipeline";

export type PresetId = "equal" | "environmental_led" | "transition_led" | "governance_led";

const LED_WEIGHT = 3; // "led" pillar gets 3x an unweighted pillar, the other two stay equal

function presetPillars(led?: Pillar): Record<Pillar, number> {
  const w = { P1: 1, P2: 1, P3: 1 } as Record<Pillar, number>;
  if (led) w[led] = LED_WEIGHT;
  return w;
}

export const PRESETS: Record<PresetId, { label: string; pillars: Record<Pillar, number> }> = {
  equal: { label: "Equal", pillars: presetPillars() },
  environmental_led: { label: "Environmental-led", pillars: presetPillars("P1") },
  transition_led: { label: "Transition-led", pillars: presetPillars("P2") },
  governance_led: { label: "Governance-led", pillars: presetPillars("P3") },
};

export function applyPreset(preset: PresetId, current: WeightsState): WeightsState {
  return { pillars: { ...PRESETS[preset].pillars }, subscores: { ...current.subscores } };
}

// --- URL hash persistence ---------------------------------------------------
// Encoding is deliberately terse (short keys, fixed precision) so a shared
// link stays a reasonable length even with all ten sub-score weights present.

const HASH_PREFIX = "w=";

export function encodeWeightsToHash(weights: WeightsState): string {
  const parts: string[] = [];
  for (const p of PILLARS) {
    const v = weights.pillars[p];
    if (v !== undefined) parts.push(`${p}:${round(v)}`);
  }
  for (const s of REGISTRY) {
    const v = weights.subscores[s.id];
    if (v !== undefined) parts.push(`${s.id}:${round(v)}`);
  }
  return HASH_PREFIX + encodeURIComponent(parts.join(","));
}

export function decodeWeightsFromHash(hash: string): WeightsState | null {
  const clean = hash.replace(/^#/, "");
  const match = clean.split("&").find((seg) => seg.startsWith(HASH_PREFIX));
  if (!match) return null;
  const body = decodeURIComponent(match.slice(HASH_PREFIX.length));
  if (!body) return null;

  const weights = defaultWeights();
  const pillarIds = new Set<string>(PILLARS);
  const subIds = new Set(REGISTRY.map((s) => s.id));
  for (const pair of body.split(",")) {
    const [key, raw] = pair.split(":");
    const value = Number(raw);
    if (!key || !Number.isFinite(value) || value < 0) continue;
    if (pillarIds.has(key)) weights.pillars[key as Pillar] = value;
    else if (subIds.has(key)) weights.subscores[key] = value;
  }
  return weights;
}

function round(n: number): number {
  return Math.round(n * 1000) / 1000;
}
