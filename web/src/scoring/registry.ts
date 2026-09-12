// THE single declaration of what a score is. One object per sub-score.
//
// `inputs` must be canonical pipeline/common/fields.py names -- that shared
// vocabulary is what keeps Python and TypeScript from drifting into two
// hand-synced dictionaries. assertRegistryMatchesSchema() below is called on
// boot and throws BY NAME if a field was renamed or removed upstream; a
// renamed field must break the app loudly, never produce a silently empty
// axis on stage.
//
// `polarity` is declared, not inferred, because the diverging colour scale
// and "better/worse than reference" language downstream are meaningless
// without knowing which direction is good. `nullPolicy` is declared per
// sub-score for the same reason: defaulting a missing input to the sector
// median and plotting it as a solid point is "rewarding silence" -- the
// score_calculation/category_score_utils.py bug this project exists to not
// repeat. Every default sub-score below uses nullPolicy 'not_disclosed'
// deliberately; 'sector_median' and 'zero' exist for a sub-score that has an
// honest reason to need them, not as a default.

export type Pillar = "P1" | "P2" | "P3";
export type Polarity = "higher_is_better" | "lower_is_better";
export type NullPolicy = "not_disclosed" | "sector_median" | "zero";

/** Raw canonical-field values for one company, coerced to number (booleans
 * become 1/0). Only ever contains the inputs a sub-score declared, and only
 * once every one of them has a trustworthy value -- see pipeline.ts. */
export type RawInputs = Record<string, number>;

export interface SubScoreDef {
  id: string;
  pillar: Pillar;
  label: string;
  polarity: Polarity;
  inputs: string[];
  compute: (f: RawInputs) => number;
  nullPolicy: NullPolicy;
  basis: string;
}

/** Fields that must never enter a pillar score (mirrors fields.py
 * VALIDATION_ONLY). Enforced in assertRegistryMatchesSchema so nobody wires
 * the thing we're trying to beat into the thing that beats it. */
export const VALIDATION_ONLY_FIELDS = new Set([
  "esg_risk_score_external",
  "esg_controversy_level_external",
]);

const pct = (n: number, d: number): number => (d === 0 ? NaN : (n / d) * 100);

export const REGISTRY: SubScoreDef[] = [
  // === P1 Environmental =====================================================
  {
    id: "p1_carbon_intensity",
    pillar: "P1",
    label: "Carbon intensity",
    polarity: "lower_is_better",
    inputs: ["scope1_tco2e", "revenue_usd"],
    // tCO2e per $M revenue -- Scope 2/3 aren't in the payload yet (see the
    // pillar spec note), so this reads Scope 1 only. Renamed to say so
    // wherever it's labelled in the UI, not just here.
    compute: (f) => (f.revenue_usd === 0 ? NaN : (f.scope1_tco2e / f.revenue_usd) * 1e6),
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p1_energy_mix",
    pillar: "P1",
    label: "Renewable energy share",
    polarity: "higher_is_better",
    inputs: ["renewable_electricity_mwh", "total_electricity_mwh"],
    compute: (f) => pct(f.renewable_electricity_mwh, f.total_electricity_mwh),
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p1_resource_waste",
    pillar: "P1",
    label: "Waste diverted from landfill",
    polarity: "higher_is_better",
    inputs: ["waste_diverted_pct"],
    compute: (f) => f.waste_diverted_pct,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },

  // === P2 Transition =========================================================
  {
    id: "p2_carbon_price_exposure",
    pillar: "P2",
    label: "Carbon-price exposure",
    polarity: "lower_is_better",
    inputs: ["scope1_tco2e", "scope2_location_tco2e", "ebitda_usd"],
    // Tonnes of (Scope 1 + Scope 2) per $M EBITDA: how much a given carbon
    // price would eat into earnings. A risk measure, not a virtue measure --
    // that's exactly why polarity has to be declared, not assumed.
    compute: (f) =>
      f.ebitda_usd === 0
        ? NaN
        : ((f.scope1_tco2e + f.scope2_location_tco2e) / f.ebitda_usd) * 1e6,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p2_sector_exposure",
    pillar: "P2",
    label: "Disclosed risk-factor intensity",
    polarity: "lower_is_better",
    inputs: ["risk_hitword_density"],
    compute: (f) => f.risk_hitword_density,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p2_regulatory_momentum",
    pillar: "P2",
    label: "Target strength & validation",
    polarity: "higher_is_better",
    inputs: ["target_reduction_pct", "sbti_target_validated"],
    // A stated reduction target, discounted when it hasn't been externally
    // validated -- an unvalidated target is a press release, not a plan.
    compute: (f) => f.target_reduction_pct * (f.sbti_target_validated ? 1 : 0.7),
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p2_innovation",
    pillar: "P2",
    label: "Climate-patent share",
    polarity: "higher_is_better",
    inputs: ["y02_patent_share_pct"],
    compute: (f) => f.y02_patent_share_pct,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },

  // === P3 Governance ==========================================================
  {
    id: "p3_board_independence",
    pillar: "P3",
    label: "Board independence",
    polarity: "higher_is_better",
    inputs: ["independent_director_count", "board_size"],
    compute: (f) => pct(f.independent_director_count, f.board_size),
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p3_exec_compensation",
    pillar: "P3",
    label: "Climate-linked pay design",
    polarity: "higher_is_better",
    inputs: ["comp_tied_to_emissions_target", "has_clawback_policy", "has_psu_plan"],
    compute: (f) =>
      ((f.comp_tied_to_emissions_target + f.has_clawback_policy + f.has_psu_plan) / 3) * 100,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p3_controversy_flags",
    pillar: "P3",
    label: "Penalty record",
    polarity: "lower_is_better",
    inputs: ["penalty_count"],
    compute: (f) => f.penalty_count,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
];

export function registryForPillar(pillar: Pillar): SubScoreDef[] {
  return REGISTRY.filter((s) => s.pillar === pillar);
}

export function subScoreById(id: string): SubScoreDef {
  const s = REGISTRY.find((r) => r.id === id);
  if (!s) throw new Error(`unknown sub-score id ${JSON.stringify(id)}`);
  return s;
}

/**
 * Boot-time contract check. Every registry input must exist in the payload's
 * own field vocabulary (payload.schema, which mirrors fields.py in full --
 * it lists the whole 59-field vocabulary regardless of which fields any
 * company actually has data for). A field missing here means someone
 * renamed or dropped it upstream without telling the frontend: fail loudly,
 * by name, rather than silently rendering an empty axis that looks like a
 * data problem instead of a code problem.
 */
export function assertRegistryMatchesSchema(schema: Record<string, unknown>): void {
  const missing: string[] = [];
  const forbidden: string[] = [];
  for (const sub of REGISTRY) {
    for (const field of sub.inputs) {
      if (!(field in schema)) missing.push(`${sub.id} -> ${field}`);
      if (VALIDATION_ONLY_FIELDS.has(field)) forbidden.push(`${sub.id} -> ${field}`);
    }
  }
  if (missing.length) {
    throw new Error(
      `Registry/schema mismatch: field(s) not in payload.schema -- ` +
        `renamed or removed upstream? ${missing.join(", ")}`
    );
  }
  if (forbidden.length) {
    throw new Error(
      `Registry uses a VALIDATION_ONLY field, which must never enter a ` +
        `pillar score: ${forbidden.join(", ")}`
    );
  }
}
