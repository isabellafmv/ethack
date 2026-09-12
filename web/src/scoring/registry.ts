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
// non-reporter bug live in score_calculation/transition/transition_score.py's
// _build_sector_intensity (a since-deleted file, category_score_utils.py,
// was the historical location; the pattern moved, the risk didn't). Most
// sub-scores below use nullPolicy 'not_disclosed'; 'sector_median' is used
// where the project has deliberately decided that silence itself is the
// finding (see p2_regulatory_momentum); 'zero' exists for a sub-score with
// an honest reason to need it, not as a default.

export type Pillar = "P1" | "P2" | "P3";
export type Polarity = "higher_is_better" | "lower_is_better";
export type NullPolicy = "not_disclosed" | "sector_median" | "zero";
/** 'pipeline_gap': null because the data source hasn't been pulled for
 * effectively the whole universe -- nobody's fault, so it's excluded from
 * the disclosure-coverage penalty in pipeline.ts (renormalizing around it
 * for free is already correct and this must not double-count that). Default
 * is 'disclosure_gap': a company-specific absence of otherwise-available
 * data counts against that pillar's disclosure coverage. Mirrors
 * score_calculation's PIPELINE_GAP_INDICATORS / disclosure-gap taxonomy. */
export type GapKind = "pipeline_gap" | "disclosure_gap";

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
  /** Fields that participate in compute() but never gate availability: an
   * absent/untrusted optional input is silently zero-filled (mirrors the
   * `nullPolicy: 'zero'` per-field convention, just scoped to specific
   * fields instead of the whole sub-score). Every sub-score without a
   * genuine reason to need this has none -- see p3_capital_stewardship for
   * the one that does and why. */
  optionalInputs?: string[];
  compute: (f: RawInputs) => number;
  nullPolicy: NullPolicy;
  /** Defaults to 'disclosure_gap' when omitted -- see GapKind. */
  gapKind?: GapKind;
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
    label: "Grid carbon intensity",
    polarity: "lower_is_better",
    // Modelled on score_calculation/environmental/environmental_score.py's
    // _energy_mix_score. The spec's own fields (renewable/total electricity,
    // S10/S21) have never been pulled -- 0/500 real coverage -- so this is a
    // REGIONAL PROXY instead, from S19 (EPA eGRID): the carbon intensity of
    // the electricity grid where a company is headquartered. Every company
    // in the same US state shares the identical value, by construction --
    // coarser than the spec's own indicator would be, but a real published
    // government number, not a reconstruction of something else. ~475/500
    // covered; the rest are non-US-headquartered companies with no US grid
    // to map to.
    inputs: ["grid_intensity_kgco2e_per_mwh"],
    compute: (f) => f.grid_intensity_kgco2e_per_mwh,
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
    // Matches environmental_score.py's PIPELINE_GAP_INDICATORS: the real
    // spec indicator here needs S16 (EPA TRI), S17 (EPA RSEI), or S26 (WRI
    // Aqueduct) -- none pulled, 0/500, for the whole universe. Not a
    // company-specific disclosure gap, so it must not count against P1's
    // disclosure-coverage penalty.
    gapKind: "pipeline_gap",
    basis: "FY2023",
  },
  {
    id: "p1_input_efficiency",
    pillar: "P1",
    label: "Input efficiency",
    polarity: "lower_is_better",
    inputs: ["cogs_usd", "revenue_usd"],
    // Modelled on score_calculation/environmental/environmental_score.py's
    // _input_efficiency_score, which blends this ratio with an energy-cost
    // one and ranks each independently before averaging. That second ratio
    // (energy_cost_usd) is 16/500 covered -- a near-no-op in practice -- so
    // it's dropped here rather than threading sector-distribution context
    // into compute(), which only ever sees one company at a time. COGS/
    // revenue alone still reads as "how input-intensive is this business",
    // not an emissions measure -- it's a proxy, and the label says so.
    compute: (f) => (f.revenue_usd === 0 ? NaN : (f.cogs_usd / f.revenue_usd) * 100),
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },

  // === P2 Transition =========================================================
  {
    id: "p2_carbon_price_exposure",
    pillar: "P2",
    label: "Carbon-price exposure",
    polarity: "higher_is_better",
    inputs: ["scope1_tco2e", "ebitda_usd"],
    // Ceiling-mapped, modelled on transition_score.py's _ceiling_score: an
    // assumed $100/ton carbon price (ASSUMED_CARBON_PRICE_USD_PER_TON) against
    // Scope 1 emissions, as a share of EBITDA, clipped to 0-50% erosion and
    // mapped so 0% erosion -> 100 (best) and >=50% erosion -> 0 (worst).
    // compute() already returns an oriented 0-100 value here, which is why
    // polarity is higher_is_better even though the underlying risk (erosion)
    // is a "lower is better" quantity -- percentile-ranking a pre-oriented
    // score a second time would double-flip it if polarity stayed
    // lower_is_better.
    //
    // Two deliberate divergences from transition_score.py's
    // carbon_price_exposure_score:
    // 1. Scope 1 only, not Scope 1+2 -- matches what GHGRP actually
    //    publishes (facility-level Scope 1 combustion emissions; GHGRP
    //    doesn't report Scope 2) and matches Python's own
    //    estimated_emissions_tco2e, which is scope1_tco2e alone.
    //    scope2_location_tco2e has 0/500 real coverage in this pipeline --
    //    requiring it (as an earlier version of this sub-score did) made
    //    this whole sub-score permanently unavailable for every company,
    //    a real bug, not a design choice.
    // 2. NOT using transition_score.py's sector-benchmark fallback for
    //    non-reporters (estimated_emissions_tco2e's "modelled" tier) --
    //    that's the exact "reward silence" pattern this project exists to
    //    avoid. A company missing scope1_tco2e stays honestly excluded via
    //    nullPolicy below, same stance as p1_carbon_intensity.
    compute: (f) => {
      if (f.ebitda_usd <= 0) return NaN; // <=0, not ===0: negative EBITDA
      const carbonCostUsd = f.scope1_tco2e * 100; // ASSUMED_CARBON_PRICE_USD_PER_TON
      const pctErosion = (carbonCostUsd * 100) / f.ebitda_usd;
      const clipped = Math.max(0, Math.min(50, pctErosion));
      return 100 * (1 - clipped / 50);
    },
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
    // Deliberate exception to this file's default stance: a company with NO
    // stated target is scored against its sector's MEDIAN target strength,
    // not excluded. Modelled on transition_score.py's sector-counterfactual
    // target ("no target still carries the liability, it just isn't
    // acknowledged") -- silence here is treated as a real, scoreable
    // liability rather than a data gap, unlike every other sub-score in
    // this registry. This is an editorial stance, not a bug; label copy
    // downstream should say so.
    nullPolicy: "sector_median",
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
    // governance_score.py's _board_independence_score blends this ratio with
    // whether a lead independent director is named (lead_independent_director,
    // 495/500 covered vs this ratio's 135/500) -- deliberately NOT ported
    // here. That blend needs "mean of independently-available components",
    // which this registry's inputs/optionalInputs model can't express without
    // either gating on both (losing the 360 companies that have only the
    // lead-director flag) or zero-filling the ratio when absent (a false
    // "0% independent" for companies that simply don't disclose board
    // composition -- exactly the reward/punish-silence pattern this project
    // avoids). Left as ratio-only, a documented scope cut, not a silent gap.
    inputs: ["independent_director_count", "board_size"],
    compute: (f) => pct(f.independent_director_count, f.board_size),
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p3_exec_compensation",
    pillar: "P3",
    label: "Compensation alignment",
    polarity: "higher_is_better",
    inputs: ["has_clawback_policy", "has_psu_plan", "performance_period_years"],
    // Modelled on governance_score.py's _compensation_alignment_score: mean
    // of the two booleans and the LTI performance period, capped at 3 years
    // (longer periods reward long-term thinking; 3+ years is already a
    // strong signal, more isn't better). Replaces comp_tied_to_emissions_target,
    // which is in the pillar spec's four booleans but S04 doesn't actually
    // emit it -- 0/500, structurally, not a temporary gap -- so requiring it
    // made this sub-score permanently unavailable for the whole universe, a
    // real bug rather than an honest data gap. Relabelled from "Climate-linked
    // pay design" to "Compensation alignment" since none of its three real
    // components are climate-specific -- this measures general pay-governance
    // structure, and the label should say so honestly.
    compute: (f) => {
      const performanceComponent = (Math.min(f.performance_period_years, 3) / 3) * 100;
      return (f.has_clawback_policy * 100 + f.has_psu_plan * 100 + performanceComponent) / 3;
    },
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p3_controversy_flags",
    pillar: "P3",
    label: "Penalty record",
    polarity: "lower_is_better",
    inputs: ["penalty_total_usd"],
    // Modelled on governance_score.py's _controversy_score: a dollar total
    // of EPA ECHO penalties, not a raw count -- the spec's own note is that
    // penalty COUNT correlates with facility count and should really be
    // normalised per facility, which this pipeline doesn't have a reliable
    // figure for either; a dollar total is at least an absolute magnitude,
    // not an artifact of how many facilities happen to file separately.
    // Python ranks this UNIVERSE-WIDE (not per-sector), reasoning that most
    // companies genuinely have $0 in penalties and that tie shouldn't be
    // split arbitrarily by sector -- kept SECTOR-relative here instead,
    // matching every other sub-score in this registry's distribution scope;
    // switching just this one to a universe-wide distribution needs a second
    // distribution-builder, a bigger change than this pass makes. Documented
    // divergence, not an oversight.
    compute: (f) => f.penalty_total_usd,
    nullPolicy: "not_disclosed",
    basis: "FY2023",
  },
  {
    id: "p3_capital_stewardship",
    pillar: "P3",
    label: "Capital stewardship",
    polarity: "higher_is_better",
    // capex_usd is the one REQUIRED input -- its absence is a real data gap.
    // Modelled on governance_score.py's _capital_stewardship_score, which
    // treats rnd/buybacks/dividends absence differently: those XBRL tags
    // are optional, so a company that simply doesn't emit them gets a true
    // zero there, not an excluded sub-score. optionalInputs is what lets
    // this registry express that asymmetry without collapsing coverage to
    // the intersection of four independently-thin fields.
    inputs: ["capex_usd"],
    optionalInputs: ["rnd_expense_usd", "buybacks_usd", "dividends_paid_usd"],
    compute: (f) => {
      const reinvestment = f.capex_usd + f.rnd_expense_usd;
      const total = reinvestment + f.buybacks_usd + f.dividends_paid_usd;
      return total <= 0 ? NaN : (reinvestment / total) * 100;
    },
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
    for (const field of [...sub.inputs, ...(sub.optionalInputs ?? [])]) {
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
