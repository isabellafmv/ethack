// Maps data/materiality.csv's 13 per-sector "indicator" importance weights
// onto this registry's sub-score ids, producing one WeightsState-shaped
// object per GICS sector. Pure logic only -- no file I/O here, so it's
// testable without a filesystem; web/scripts/make-materiality.ts does the
// reading/writing and calls straight into this module.
//
// materiality.csv is a hand-curated judgement call (its own generator,
// pipeline/materiality.py, says so explicitly: "This is a JUDGEMENT, not a
// derivation"), not a DB-refresh artifact -- it's generated once and
// committed, the same treatment as the fixture files, not wired into
// `npm run data`.
//
// Important honesty note: the CSV's indicator CONCEPTS don't always match
// what the registry sub-score of the same mapped name actually computes.
// E.g. `innovation_momentum`'s stated concept (pipeline/materiality.py)
// blends SBTi validation + R&D intensity; `p2_innovation` only computes
// patent share. `resource_waste_intensity` wants waste_total_tonnes/revenue;
// `p1_resource_waste` only reads waste_diverted_pct. This mapping transfers
// *importance weight for a named topic*, not *the exact formula* -- a
// reasonable and common approach for weighting, but not a literal
// correspondence, and worth remembering when reading the numbers.
import type { Pillar } from "./registry";

/** materiality.csv column -> registry sub-score id. Three columns have no
 * mapping at all: transition_affordability, structural_disruption, and
 * climate_governance name concepts this registry has no sub-score for yet.
 * Their weight mass is dropped, not redistributed -- see
 * deriveMaterialityWeights's pillar-sum comment for the consequence. */
export const INDICATOR_TO_SUBSCORE: Readonly<Record<string, string>> = {
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
};

/** Indicator columns that exist in materiality.csv but are deliberately
 * unmapped -- named here (rather than just "whatever's left over") so a
 * future column rename doesn't silently start being treated as one of
 * these by accident. */
export const UNMAPPED_INDICATORS: ReadonlySet<string> = new Set([
  "transition_affordability",
  "structural_disruption",
  "climate_governance",
]);

/** Registry sub-scores with no materiality.csv column at all. Given a
 * neutral weight so they aren't silently zeroed out of the composite under
 * materiality mode, but excluded from the pillar-weight sum below (mixing a
 * neutral 1 with CSV-scale numbers like 8-20 would arbitrarily inflate
 * P2's implied pillar weight). */
export const NEUTRAL_SUBSCORES: readonly string[] = ["p2_regulatory_momentum", "p2_sector_exposure"];
const NEUTRAL_WEIGHT = 1;

const SUBSCORE_PILLAR: Readonly<Record<string, Pillar>> = {
  p1_carbon_intensity: "P1", p1_energy_mix: "P1", p1_resource_waste: "P1", p1_input_efficiency: "P1",
  p2_carbon_price_exposure: "P2", p2_innovation: "P2", p2_regulatory_momentum: "P2", p2_sector_exposure: "P2",
  p3_exec_compensation: "P3", p3_board_independence: "P3", p3_capital_stewardship: "P3", p3_controversy_flags: "P3",
};

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
 * Derives one WeightsState-shaped SectorWeights per sector from the parsed
 * CSV rows. Pillar weight = the SUM of only the materiality-derived (mapped)
 * sub-score weights for that pillar -- the two neutral defaults are
 * deliberately excluded from that sum, and the three unmapped indicators'
 * weight mass simply disappears rather than being redistributed. This makes
 * a materiality-mode P2 pillar weight structurally smaller than the CSV's
 * own rationale would argue for in sectors where transition_affordability/
 * structural_disruption carry real weight (e.g. Energy: those two alone are
 * ~22 of that row's ~100) -- an honest limitation of "no sub-score exists
 * yet for that concept," not a bug to paper over.
 */
export function deriveMaterialityWeights(rows: readonly MaterialityRow[]): Record<string, SectorWeights> {
  const out: Record<string, SectorWeights> = {};
  for (const row of rows) {
    const sector = row.sector;
    const subscores: Record<string, number> = {};
    for (const [column, subId] of Object.entries(INDICATOR_TO_SUBSCORE)) {
      subscores[subId] = Number(row[column]);
    }
    for (const subId of NEUTRAL_SUBSCORES) subscores[subId] = NEUTRAL_WEIGHT;

    const pillars = { P1: 0, P2: 0, P3: 0 } as Record<Pillar, number>;
    for (const [subId, weight] of Object.entries(subscores)) {
      if (NEUTRAL_SUBSCORES.includes(subId)) continue; // excluded from the pillar sum, see doc comment
      pillars[SUBSCORE_PILLAR[subId]] += weight;
    }

    out[sector] = { pillars, subscores, rationale: row.rationale };
  }
  return out;
}
