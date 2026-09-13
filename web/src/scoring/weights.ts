// Weight presets and URL-hash persistence. Kept separate from pipeline.ts
// because none of this touches company data -- it's pure state shaping.

import { PYTHON_P2_WEIGHTS, PYTHON_P3_WEIGHTS, REGISTRY, type Pillar } from "./registry";
import { defaultWeights, PILLARS, type WeightsState } from "./pipeline";
import type { SectorWeights } from "./materiality";

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

/**
 * The per-sector WeightsState Map that reproduces score_calculation/'s own
 * default weighting exactly -- the thing this app should score against by
 * default (see App.tsx's use of it once materiality.json has loaded), not
 * an opt-in "materiality mode" among several equally-valid choices.
 *
 * Combines two DIFFERENT weight sources, because Python itself does:
 * - P1 sub-score weights: `sectorWeights`'s own per-sector materiality
 *   values (deriveMaterialityWeights's output) -- environmental_score.py
 *   applies these, renormalized within P1, per sector.
 * - P2/P3 sub-score weights: PYTHON_P2_WEIGHTS/PYTHON_P3_WEIGHTS, identical
 *   for every sector -- transition_score.py/governance_score.py's own fixed
 *   WEIGHTS dicts, which are NOT sector-varying in Python at all.
 * - Pillar weights: always the flat {P1:1, P2:1, P3:1} -- final_score.py's
 *   fixed equal 1/3 split, never a materiality-derived pillar mix.
 */
export function pythonDefaultWeights(
  sectorWeights: Record<string, SectorWeights>
): Map<string, WeightsState & { rationale: string }> {
  const out = new Map<string, WeightsState & { rationale: string }>();
  for (const [sector, sw] of Object.entries(sectorWeights)) {
    out.set(sector, {
      pillars: { P1: 1, P2: 1, P3: 1 },
      subscores: { ...sw.subscores, ...PYTHON_P2_WEIGHTS, ...PYTHON_P3_WEIGHTS },
      rationale: sw.rationale,
    });
  }
  return out;
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

// --- weight mode (manual vs materiality) persistence ------------------------
// A separate hash segment from `w=`, so an old shared link (manual mode,
// no `mode=` segment at all) keeps decoding exactly as it always has.
// Materiality weights themselves are static (not user-adjustable), so only
// the boolean "which mode" needs to round-trip -- not any per-sector value.

export type WeightMode = "manual" | "materiality";
const MODE_PREFIX = "mode=";

export function encodeWeightModeToHash(mode: WeightMode): string {
  return mode === "materiality" ? `${MODE_PREFIX}materiality` : "";
}

export function decodeWeightModeFromHash(hash: string): WeightMode {
  const clean = hash.replace(/^#/, "");
  const seg = clean.split("&").find((s) => s.startsWith(MODE_PREFIX));
  return seg?.slice(MODE_PREFIX.length) === "materiality" ? "materiality" : "manual";
}
