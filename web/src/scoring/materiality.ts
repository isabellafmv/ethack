// Maps data/materiality.csv's 13 per-sector "indicator" importance weights
// onto this registry's sub-score ids, producing one per-sector P1 weight
// set. Pure logic only -- no file I/O here, so it's testable without a
// filesystem; web/scripts/make-materiality.ts does the reading/writing and
// calls straight into this module.
import type { Pillar } from "./registry";
//
// materiality.csv is a hand-curated judgement call (its own generator,
// pipeline/materiality.py, says so explicitly: "This is a JUDGEMENT, not a
// derivation"), not a DB-refresh artifact -- it's generated once and
// committed, the same treatment as the fixture files, not wired into
// `npm run data`.
//
// Only the FOUR P1 indicator columns are mapped: environmental_score.py is
// the one pillar file that actually applies materiality.csv's weights
// (renormalized within P1) to its own sub-scores. transition_score.py and
// governance_score.py use their own fixed, sector-INVARIANT WEIGHTS dicts
// instead (registry.ts's PYTHON_P2_WEIGHTS/PYTHON_P3_WEIGHTS) -- the CSV's
// P2/P3 columns are a real SASB-inspired judgement call, but Python simply
// never wires them into a P2/P3 score, so mapping them here would produce
// per-sector P2/P3 weights that don't match the Python oracle this
// registry is built to reproduce. See weights.ts's pythonDefaultWeights for
// how the two are combined into one per-sector WeightsState.
export const INDICATOR_TO_SUBSCORE: Readonly<Record<string, string>> = {
  carbon_intensity: "p1_carbon_intensity",
  energy_mix: "p1_energy_mix",
  resource_waste_intensity: "p1_resource_waste",
  input_efficiency: "p1_input_efficiency",
};

/** Every materiality.csv column outside the four P1 indicators -- named
 * here (rather than just "whatever's left over") so a future column rename
 * doesn't silently start being treated as one of these by accident, and so
 * assertIndicatorColumnsKnown still validates the CSV's full 13-indicator
 * shape even though only four of them feed a score. */
export const UNMAPPED_INDICATORS: ReadonlySet<string> = new Set([
  "carbon_price_exposure",
  "transition_affordability",
  "innovation_momentum",
  "structural_disruption",
  "climate_governance",
  "compensation_alignment",
  "board_independence",
  "capital_stewardship",
  "controversy_record",
]);

const NON_INDICATOR_COLUMNS = new Set(["sector", "rationale"]);

/** Throws by name if materiality.csv gains, renames, or drops a column this
 * module doesn't know about -- fail loudly on drift, mirroring
 * registry.ts's assertRegistryMatchesSchema convention, rather than
 * silently mis-mapping or silently ignoring a new column. */
export function assertIndicatorColumnsKnown(header: readonly string[]): void {
  const known = new Set([...Object.keys(INDICATOR_TO_SUBSCORE), ...UNMAPPED_INDICATORS, ...NON_INDICATOR_COLUMNS]);
  const unknown = header.filter((col) => !known.has(col));
  if (unknown.length) {
    throw new Error(
      `materiality.csv has column(s) this module doesn't know how to map: ${unknown.join(", ")}. ` +
        `Add them to INDICATOR_TO_SUBSCORE or UNMAPPED_INDICATORS in materiality.ts.`
    );
  }
  const missing = [...Object.keys(INDICATOR_TO_SUBSCORE), ...UNMAPPED_INDICATORS].filter(
    (col) => !header.includes(col)
  );
  if (missing.length) {
    throw new Error(`materiality.csv is missing expected column(s): ${missing.join(", ")}.`);
  }
}

export interface SectorWeights {
  pillars: Record<Pillar, number>;
  subscores: Record<string, number>;
  /** The CSV's written rationale for this sector -- surfaced in the UI so
   * "why does Utilities weigh energy mix so heavily" has an answer on
   * screen, not just in a spreadsheet nobody sees. */
  rationale: string;
}

/** One row of the parsed materiality.csv, string-valued as read from disk. */
export type MaterialityRow = Record<string, string>;

/**
 * Derives one per-sector P1 sub-score weight set from the parsed CSV rows
 * (renormalized within P1 downstream by pipeline.ts's normalizedWeights,
 * the same treatment environmental_score.py gives these four numbers).
 * `pillars` is always the flat {P1:1, P2:1, P3:1} -- final_score.py combines
 * pillars with a fixed EQUAL 1/3 weight each, never a materiality-derived
 * split, so this must not vary by sector either; see weights.ts's
 * pythonDefaultWeights for how P1's per-sector weights here get combined
 * with P2/P3's fixed WEIGHTS dicts into one full per-sector WeightsState.
 */
export function deriveMaterialityWeights(rows: readonly MaterialityRow[]): Record<string, SectorWeights> {
  const out: Record<string, SectorWeights> = {};
  for (const row of rows) {
    const sector = row.sector;
    const subscores: Record<string, number> = {};
    for (const [column, subId] of Object.entries(INDICATOR_TO_SUBSCORE)) {
      subscores[subId] = Number(row[column]);
    }
    out[sector] = { pillars: { P1: 1, P2: 1, P3: 1 }, subscores, rationale: row.rationale };
  }
  return out;
}
