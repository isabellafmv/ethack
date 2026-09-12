// Writes web/public/data/matrix.fixture.json (+ quotes.fixture.json) in the
// EXACT matrix.json/quotes.json shape produced by pipeline/export_matrix.py.
// Run via `npm run fixture` (or `npm run fixture:degenerate`) from web/.
//
// Why this exists at all: the frontend must never be blocked on the Python
// pipeline being runnable on a given machine. Real tickers/sectors/market
// caps come from data/wide_FY2025.csv (the one wide export that actually
// carries market_cap_usd); everything else is synthesised with a seeded RNG
// so the fixture is deterministic and reviewable in a diff.
//
// Coverage here is deliberately modelled on the REAL data/matrix.json in this
// repo (25 of 57 fields carry ANY data; P3 governance and half of P2 carry
// NONE yet) but widened just enough that all ten registry sub-scores have
// *some* real coverage -- otherwise Task 4/5/6 would have nothing to render
// against while the real pipeline catches up. Coverage is still thin and
// uneven on purpose: an axis with 0 real companies is a finding, not a bug,
// and the fixture should be able to demonstrate that too.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseCsv } from "./csv";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const WIDE_CSV = resolve(REPO_ROOT, "data", "wide_FY2025.csv");
const OUT_DIR = resolve(__dirname, "..", "public", "data");

const DEGENERATE = process.argv.includes("--degenerate");
const ANALYSIS_YEAR = 2023;
const SCHEMA_VERSION = 1;

// --- canonical field vocabulary (mirrors pipeline/common/fields.py) --------
// VALIDATION_ONLY fields (esg_risk_score_external, esg_controversy_level_external)
// are deliberately excluded, same as export_matrix.py's payload.schema.
type Dtype = "str" | "float" | "int" | "bool";
interface FieldMeta {
  unit: string | null;
  pillar: "P1" | "P2" | "P3" | "X";
  dtype: Dtype;
  description: string;
}

const FIELD_META: Record<string, FieldMeta> = {
  cik: { unit: null, pillar: "X", dtype: "str", description: "SEC Central Index Key, zero-padded to 10" },
  legal_name: { unit: null, pillar: "X", dtype: "str", description: "Registrant legal name as filed" },
  lei: { unit: null, pillar: "X", dtype: "str", description: "Legal Entity Identifier" },
  ultimate_parent_lei: { unit: null, pillar: "X", dtype: "str", description: "GLEIF Level 2 ultimate parent" },
  gics_sector: { unit: null, pillar: "X", dtype: "str", description: "One of 11 GICS sectors; the normalisation bucket" },
  gics_sub_industry: { unit: null, pillar: "X", dtype: "str", description: "GICS sub-industry" },
  hq_state: { unit: null, pillar: "X", dtype: "str", description: "HQ state, used to constrain entity matching" },
  subsidiary_count: { unit: "count", pillar: "X", dtype: "int", description: "Subsidiaries listed in Exhibit 21" },
  market_cap_usd: { unit: "usd", pillar: "X", dtype: "float", description: "Market cap; bubble size on the 3D map" },
  shares_outstanding: { unit: "count", pillar: "X", dtype: "float", description: "Shares outstanding" },

  scope1_tco2e: { unit: "tco2e", pillar: "P1", dtype: "float", description: "Scope 1. EPA-measured (S15) and self-reported (S10) coexist by design -- the gap between them is the say-do signal." },
  scope2_location_tco2e: { unit: "tco2e", pillar: "P1", dtype: "float", description: "Scope 2, location-based" },
  scope2_market_tco2e: { unit: "tco2e", pillar: "P1", dtype: "float", description: "Scope 2, market-based. A renewable claim that moves this but NOT the location-based figure is an unbundled REC purchase -- flag, do not credit." },
  scope3_tco2e: { unit: "tco2e", pillar: "P1", dtype: "float", description: "Scope 3, as disclosed" },
  ghg_facility_count: { unit: "count", pillar: "P1", dtype: "int", description: "Reporting facilities in GHGRP. Track YoY: a divestiture looks identical to an emissions cut." },
  renewable_electricity_mwh: { unit: "mwh", pillar: "P1", dtype: "float", description: "Renewable electricity procured/generated" },
  total_electricity_mwh: { unit: "mwh", pillar: "P1", dtype: "float", description: "Total electricity consumed" },
  grid_intensity_kgco2e_per_mwh: { unit: "kgco2e_per_mwh", pillar: "P1", dtype: "float", description: "eGRID subregion intensity for the company's facility footprint" },
  water_withdrawal_m3: { unit: "m3", pillar: "P1", dtype: "float", description: "Total water withdrawn" },
  waste_total_tonnes: { unit: "tonnes", pillar: "P1", dtype: "float", description: "Total waste generated" },
  waste_diverted_pct: { unit: "pct", pillar: "P1", dtype: "float", description: "Share of waste diverted from landfill" },
  cogs_usd: { unit: "usd", pillar: "P1", dtype: "float", description: "Cost of goods sold; input efficiency numerator" },
  energy_cost_usd: { unit: "usd", pillar: "P1", dtype: "float", description: "Energy cost where separately disclosed" },

  revenue_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "Revenue. Splits across 4+ XBRL tags -- the fallback chain lives in sources/s01_sec_xbrl/fields.py, not in caller code." },
  ebit_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "Operating income" },
  ebitda_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "EBIT + D&A; carbon-price exposure denominator" },
  free_cash_flow_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "CFO - capex. The affordability denominator: can they pay for what they promised." },
  capex_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "PaymentsToAcquirePropertyPlantAndEquipment" },
  clean_capex_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "Low-carbon portion of capex, from Item 7 MD&A. Expect ~1/3 hit rate -- the low rate is itself a finding, report it." },
  rnd_expense_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "R&D expense" },
  green_revenue_share_pct: { unit: "pct", pillar: "P2", dtype: "float", description: "Revenue from low-carbon segments. The classification is OURS, not the company's -- per-segment rationale must be published alongside." },
  sbti_target_validated: { unit: null, pillar: "P2", dtype: "bool", description: "Has an SBTi-validated target" },
  sbti_target_type: { unit: null, pillar: "P2", dtype: "str", description: "near-term | net-zero | commitment" },
  target_year: { unit: "year", pillar: "P2", dtype: "int", description: "Stated target year" },
  target_baseline_year: { unit: "year", pillar: "P2", dtype: "int", description: "Baseline year for the target" },
  target_reduction_pct: { unit: "pct", pillar: "P2", dtype: "float", description: "Stated reduction vs baseline" },
  target_scope_coverage: { unit: null, pillar: "P2", dtype: "str", description: "Which scopes the target covers" },
  risk_hitword_density: { unit: "index", pillar: "P2", dtype: "float", description: "Item 1A hitwords weighted by POSITION and proximity to intensifiers. No negation handling: name that limit in the pitch." },
  risk_first_factor_topic: { unit: null, pillar: "P2", dtype: "str", description: "Topic of the FIRST risk factor. What comes first is what management fears." },
  y02_patent_share_pct: { unit: "pct", pillar: "P2", dtype: "float", description: "Y02 (climate-mitigation) share of recent filings. True zero for financials and services -- report as zero-with-explanation, never null." },
  lobbying_spend_usd: { unit: "usd", pillar: "P2", dtype: "float", description: "Senate LDA reported spend" },
  lobbying_climate_flag: { unit: null, pillar: "P2", dtype: "bool", description: "Lobbied on a climate-relevant issue code. A flag, not a score -- attribution via trade associations is messy." },

  has_climate_oversight_committee: { unit: null, pillar: "P3", dtype: "bool", description: "Named board committee with explicit climate oversight" },
  comp_tied_to_emissions_target: { unit: null, pillar: "P3", dtype: "bool", description: "Executive comp linked to an emissions metric" },
  has_third_party_assurance: { unit: null, pillar: "P3", dtype: "bool", description: "Emissions externally assured" },
  assurance_level: { unit: null, pillar: "P3", dtype: "str", description: "limited | reasonable | none" },
  emissions_boundary_stated: { unit: null, pillar: "P3", dtype: "bool", description: "Reporting boundary explicitly stated (operational/equity control)" },
  has_clawback_policy: { unit: null, pillar: "P3", dtype: "bool", description: "Clawback provision. WATCH NEGATION: 'we do not maintain a clawback policy' contains the keyword and means the opposite." },
  has_psu_plan: { unit: null, pillar: "P3", dtype: "bool", description: "Performance share units in the LTI plan" },
  performance_period_years: { unit: "years", pillar: "P3", dtype: "float", description: "LTI performance period" },
  independent_director_count: { unit: "count", pillar: "P3", dtype: "int", description: "Independent directors" },
  board_size: { unit: "count", pillar: "P3", dtype: "int", description: "Total directors" },
  lead_independent_director: { unit: null, pillar: "P3", dtype: "bool", description: "Lead independent director present" },
  buybacks_usd: { unit: "usd", pillar: "P3", dtype: "float", description: "Share repurchases" },
  dividends_paid_usd: { unit: "usd", pillar: "P3", dtype: "float", description: "Dividends paid" },
  penalty_total_usd: { unit: "usd", pillar: "P3", dtype: "float", description: "Penalties from COURT AND AGENCY RECORDS, not news sentiment." },
  penalty_count: { unit: "count", pillar: "P3", dtype: "int", description: "Number of penalty records" },
};

const SOURCE_PRIORITY = [
  "S15", "S19", "S01", "S04", "S05", "S08", "S09", "S10", "S02", "S03", "S06",
  "S07", "S11", "S12", "S13", "S15~team", "S09~team", "S01~team", "imputed",
];

const GICS_SECTORS = [
  "Communication Services", "Consumer Discretionary", "Consumer Staples",
  "Energy", "Financials", "Health Care", "Industrials",
  "Information Technology", "Materials", "Real Estate", "Utilities",
] as const;

// Rough emissions-intensity archetype per sector, used only to make
// synthesised P1/P2 values cluster realistically instead of reading as pure
// noise -- an all-white-noise fixture would never expose a sector-relative
// percentile bug because nothing would actually correlate with sector.
const SECTOR_CARBON_INTENSITY: Record<string, number> = {
  Utilities: 9, Energy: 8, Materials: 7, Industrials: 4,
  "Consumer Staples": 3, "Consumer Discretionary": 2, "Health Care": 1.5,
  Financials: 1, "Real Estate": 1.2, "Information Technology": 1,
  "Communication Services": 1,
};

// --- seeded RNG (mulberry32, same algorithm as scoring/rankSensitivity.ts) -
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Deterministic uniform draw for (ticker, salt), independent of iteration order. */
function draw(ticker: string, salt: string): number {
  return mulberry32(hashString(`${ticker}::${salt}`))();
}

interface RawFieldRecord {
  v: number | string | boolean;
  u: string | null;
  fy: number;
  src: string;
  st: "structural" | "quote_verified" | "imputed";
  c: number;
  url: number;
  q?: string;
}

const CONFIDENCE_BY_STATUS: Record<RawFieldRecord["st"], number> = {
  structural: 1.0,
  quote_verified: 0.85,
  imputed: 0.3,
};

function csvNum(row: Record<string, string>, key: string): number | null {
  const raw = row[key];
  if (raw === undefined || raw === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function csvBool(row: Record<string, string>, key: string): boolean | null {
  const raw = row[key];
  if (raw === undefined || raw === "") return null;
  return raw === "1" || raw === "1.0" || raw.toLowerCase() === "true";
}

function csvStr(row: Record<string, string>, key: string): string | null {
  const raw = row[key];
  return raw === undefined || raw === "" ? null : raw;
}

// --- per-field quote templates (fictional, generated for the fixture only) -
const QUOTE_TEMPLATES: Record<string, (v: number | string | boolean, ticker: string) => string> = {
  scope1_tco2e: (v) => `We report Scope 1 greenhouse gas emissions of approximately ${Math.round(Number(v)).toLocaleString()} tCO2e for fiscal year 2023.`,
  scope2_location_tco2e: (v) => `Location-based Scope 2 emissions were approximately ${Math.round(Number(v)).toLocaleString()} tCO2e in fiscal year 2023.`,
  renewable_electricity_mwh: (v) => `Renewable sources accounted for ${Math.round(Number(v)).toLocaleString()} MWh of our electricity procurement in fiscal year 2023.`,
  total_electricity_mwh: (v) => `Total electricity consumption across our operations was ${Math.round(Number(v)).toLocaleString()} MWh in fiscal year 2023.`,
  waste_diverted_pct: (v) => `${Number(v).toFixed(0)}% of waste generated at our facilities was diverted from landfill in fiscal year 2023.`,
  target_reduction_pct: (v) => `We have committed to reducing emissions ${Number(v).toFixed(0)}% against our stated baseline.`,
  independent_director_count: (v, t) => `${Math.round(Number(v))} of the board's directors are independent, as disclosed in ${t}'s most recent proxy statement.`,
  comp_tied_to_emissions_target: (v) => (v ? "A portion of executive incentive compensation is tied to progress against our emissions reduction target." : "Executive compensation is not currently linked to an emissions metric."),
  has_clawback_policy: (v) => (v ? "The company maintains a clawback policy applicable to incentive-based compensation." : "The company does not maintain a clawback policy."),
  has_psu_plan: (v) => (v ? "Performance share units form part of the long-term incentive plan." : "The long-term incentive plan does not include performance share units."),
  penalty_count: (v) => (Number(v) > 0 ? `${Math.round(Number(v))} penalty record(s) were identified in court and agency filings.` : "No penalty records were identified in court and agency filings."),
  y02_patent_share_pct: (v) => `Y02 (climate-mitigation) classified filings represent ${Number(v).toFixed(1)}% of recent patent activity.`,
  risk_hitword_density: () => `Climate- and transition-related language appears at elevated density in Item 1A of the most recent Form 10-K.`,
};

function main() {
  mkdirSync(OUT_DIR, { recursive: true });
  const csvText = readFileSync(WIDE_CSV, "utf-8");
  const rows = parseCsv(csvText);
  if (rows.length === 0) throw new Error(`no rows parsed from ${WIDE_CSV}`);

  const urls: string[] = [];
  const urlIndex = new Map<string, number>();
  function internUrl(u: string): number {
    let idx = urlIndex.get(u);
    if (idx === undefined) { idx = urls.length; urls.push(u); urlIndex.set(u, idx); }
    return idx;
  }
  const FIXTURE_URL = "https://fixture.local/synthetic-source";

  const quotes: Record<string, Record<string, string>> = {};
  const companies = rows.map((row) => {
    const ticker = row.ticker;
    const sector = row.gics_sector || row.sector || "Unknown";
    const fields: Record<string, RawFieldRecord> = {};
    const alternatives: Record<string, RawFieldRecord[]> = {};

    // --- 1. passthrough from the CSV, keeping its own honest missingness --
    const passthrough: [string, "float" | "int" | "bool" | "str", string][] = [
      ["cik", "str", "S08"],
      ["legal_name", "str", "S08"],
      ["gics_sector", "str", "S08"],
      ["gics_sub_industry", "str", "S08"],
      ["hq_state", "str", "S08"],
      ["market_cap_usd", "float", "S07"],
      ["shares_outstanding", "float", "S01"],
      ["cogs_usd", "float", "S01"],
      ["energy_cost_usd", "float", "S02"],
      ["revenue_usd", "float", "S01"],
      ["ebit_usd", "float", "S01"],
      ["ebitda_usd", "float", "S01"],
      ["free_cash_flow_usd", "float", "S01"],
      ["capex_usd", "float", "S01"],
      ["rnd_expense_usd", "float", "S01"],
      ["sbti_target_validated", "bool", "S09"],
      ["sbti_target_type", "str", "S09"],
      ["buybacks_usd", "float", "S01"],
      ["dividends_paid_usd", "float", "S01"],
      ["target_year", "int", "S09"],
    ];
    for (const [field, dtype, src] of passthrough) {
      let v: number | string | boolean | null;
      if (dtype === "bool") v = csvBool(row, field);
      else if (dtype === "str") v = csvStr(row, field);
      else v = csvNum(row, field);
      if (v === null) continue;
      const isFlow = ["cogs_usd", "energy_cost_usd", "revenue_usd", "ebit_usd", "ebitda_usd",
        "free_cash_flow_usd", "capex_usd", "rnd_expense_usd", "buybacks_usd", "dividends_paid_usd"].includes(field);
      fields[field] = {
        v, u: FIELD_META[field].unit, fy: isFlow ? ANALYSIS_YEAR : 2025,
        src, st: "structural", c: 1.0, url: internUrl(FIXTURE_URL),
      };
    }

    // target_reduction_pct / target_baseline_year / target_scope_coverage are
    // 0/500 in data/wide_FY2025.csv (they come from a different source table
    // in the real pipeline) -- synthesise for the subset with an SBTi target
    // so p2_regulatory_momentum has honest, correlated coverage.
    const sbtiValidated = fields.sbti_target_validated?.v === true;
    const hasTarget = fields.sbti_target_validated !== undefined && draw(ticker, "has_target") < (sbtiValidated ? 0.7 : 0.15);
    if (hasTarget) {
      const reduction = 20 + draw(ticker, "target_reduction_pct") * 60;
      addField(fields, quotes, ticker, "target_reduction_pct", reduction, "S09", "quote_verified", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
      addField(fields, quotes, ticker, "target_baseline_year", 2019, "S09", "structural", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
      addField(fields, quotes, ticker, "target_scope_coverage", "1+2", "S09", "structural", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
    }

    // --- 2. synthesised fields not present in the wide export --------------
    const intensity = SECTOR_CARBON_INTENSITY[sector] ?? 1;
    const revenue = typeof fields.revenue_usd?.v === "number" ? fields.revenue_usd.v : 5e9;

    // Scope 1: ~110/500 structural (EPA GHGRP, FY2023 only) + a further
    // imputed tail of ~20 so the 'imputed' statusClass path is exercised.
    const scope1Roll = draw(ticker, "scope1_coverage");
    if (scope1Roll < 0.22) {
      const base = draw(ticker, "scope1_value");
      const tco2e = (0.3 + base * 1.4) * intensity * (revenue / 1e6);
      addField(fields, quotes, ticker, "scope1_tco2e", Math.round(tco2e), "S15", "structural", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
      addField(fields, quotes, ticker, "ghg_facility_count", 1 + Math.floor(draw(ticker, "facility_count") * 12), "S15", "structural", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
      // ~15% of covered companies also get a self-reported alternative --
      // the say-do gap export_matrix.py's `alternatives` exists to show.
      if (draw(ticker, "has_alt") < 0.15) {
        const selfReported = Math.round(tco2e * (0.7 + draw(ticker, "alt_skew") * 0.6));
        alternatives.scope1_tco2e = [{
          v: selfReported, u: "tco2e", fy: ANALYSIS_YEAR, src: "S10",
          st: "quote_verified", c: 0.85, url: internUrl(FIXTURE_URL),
        }];
      }
    } else if (scope1Roll < 0.26) {
      // imputed tail: sector median stand-in, rendered hollow, excluded from
      // the distribution -- never a substitute presented as a measurement.
      const imputedValue = Math.round(intensity * (revenue / 1e6) * 0.8);
      fields.scope1_tco2e = {
        v: imputedValue, u: "tco2e", fy: ANALYSIS_YEAR, src: "imputed",
        st: "imputed", c: CONFIDENCE_BY_STATUS.imputed, url: internUrl(FIXTURE_URL),
      };
    }

    // Scope 2 location-based: ~90/500, correlated with scope1 where present.
    if (draw(ticker, "scope2_coverage") < 0.18) {
      const scope1Val = typeof fields.scope1_tco2e?.v === "number" ? fields.scope1_tco2e.v : intensity * (revenue / 1e6) * 0.5;
      const ratio = 0.35 + draw(ticker, "scope2_ratio") * 0.5;
      addField(fields, quotes, ticker, "scope2_location_tco2e", Math.round(scope1Val * ratio), "S10", "quote_verified", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
    }

    // Renewable / total electricity: ~100/500 paired.
    if (draw(ticker, "energy_coverage") < 0.2) {
      const total = 5e5 + draw(ticker, "total_mwh") * 5e6;
      const renewShare = draw(ticker, "renew_share") * 0.8;
      addField(fields, quotes, ticker, "total_electricity_mwh", Math.round(total), "S10", "quote_verified", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
      addField(fields, quotes, ticker, "renewable_electricity_mwh", Math.round(total * renewShare), "S10", "quote_verified", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
    }

    // Waste diverted: ~80/500.
    if (draw(ticker, "waste_coverage") < 0.16) {
      const pct = draw(ticker, "waste_pct") * 95;
      addField(fields, quotes, ticker, "waste_diverted_pct", Math.round(pct * 10) / 10, "S10", "quote_verified", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
    }

    // Risk-factor hitword density: broad structural coverage (derived from
    // 10-K text, not a disclosure choice) -- ~300/500.
    if (draw(ticker, "risk_coverage") < 0.6) {
      const density = draw(ticker, "risk_density") * 10;
      addField(fields, quotes, ticker, "risk_hitword_density", Math.round(density * 100) / 100, "S02", "structural", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
    }

    // Climate-patent share: true zero for Financials/Real Estate/Comm
    // Services (per fields.py's own note), a small positive share elsewhere.
    // Broad coverage since it's derived from public patent filings.
    if (draw(ticker, "patent_coverage") < 0.75) {
      const zeroSector = sector === "Financials" || sector === "Real Estate" || sector === "Communication Services";
      const share = zeroSector ? 0 : draw(ticker, "patent_share") * 8;
      addField(fields, quotes, ticker, "y02_patent_share_pct", Math.round(share * 100) / 100, "S24", "structural", ANALYSIS_YEAR, internUrl(FIXTURE_URL));
    }

    // Governance: board composition, comp design, clawback/PSU -- ~60/500,
    // proxy-statement scraping is the slowest lane, so coverage stays thin.
    if (draw(ticker, "board_coverage") < 0.12) {
      const boardSize = 7 + Math.floor(draw(ticker, "board_size") * 8);
      const indepFrac = 0.55 + draw(ticker, "indep_frac") * 0.4;
      addField(fields, quotes, ticker, "board_size", boardSize, "S04", "structural", 2025, internUrl(FIXTURE_URL));
      addField(fields, quotes, ticker, "independent_director_count", Math.round(boardSize * indepFrac), "S04", "quote_verified", 2025, internUrl(FIXTURE_URL));
    }
    if (draw(ticker, "comp_coverage") < 0.12) {
      const tied = draw(ticker, "comp_tied") < (sbtiValidated ? 0.55 : 0.2);
      addField(fields, quotes, ticker, "comp_tied_to_emissions_target", tied, "S04", "quote_verified", 2025, internUrl(FIXTURE_URL));
    }
    if (draw(ticker, "clawback_coverage") < 0.1) {
      const has = draw(ticker, "clawback_val") < 0.85;
      addField(fields, quotes, ticker, "has_clawback_policy", has, "S04", "quote_verified", 2025, internUrl(FIXTURE_URL));
    }
    if (draw(ticker, "psu_coverage") < 0.1) {
      const has = draw(ticker, "psu_val") < 0.7;
      addField(fields, quotes, ticker, "has_psu_plan", has, "S04", "quote_verified", 2025, internUrl(FIXTURE_URL));
    }

    // Penalty count: broad coverage (court/agency records are public
    // regardless of what the company discloses) -- ~400/500, mostly zero.
    if (draw(ticker, "penalty_coverage") < 0.8) {
      const heavy = ["Energy", "Materials", "Utilities", "Financials"].includes(sector);
      const roll = draw(ticker, "penalty_roll");
      const count = roll < (heavy ? 0.5 : 0.85) ? 0 : 1 + Math.floor(draw(ticker, "penalty_count") * (heavy ? 6 : 3));
      addField(fields, quotes, ticker, "penalty_count", count, "S11", "structural", 2025, internUrl(FIXTURE_URL));
    }

    const confVals = Object.values(fields).map((f) => f.c);
    const confidence = confVals.length ? Math.round((confVals.reduce((a, b) => a + b, 0) / confVals.length) * 1000) / 1000 : 0;

    const cleanFields: Record<string, Omit<RawFieldRecord, "q">> = {};
    for (const [k, v] of Object.entries(fields)) {
      const { q, ...rest } = v;
      void q;
      cleanFields[k] = rest;
    }
    const cleanAlts: Record<string, Omit<RawFieldRecord, "q">[]> = {};
    for (const [k, arr] of Object.entries(alternatives)) {
      cleanAlts[k] = arr.map(({ q, ...rest }) => { void q; return rest; });
    }

    return {
      ticker,
      name: row.company || row.legal_name || ticker,
      sector,
      sub_industry: row.gics_sub_industry || row.sub_industry || "",
      fields: cleanFields,
      alternatives: cleanAlts,
      confidence,
    };
  });

  // --degenerate: collapse every field to one value per GICS sector -- zero
  // within-sector variance, reproducing the known-bad state where everyone
  // in a sector ties on percentile (score 50) regardless of what they
  // actually reported. Applied as a single override pass over the ALREADY
  // realistic values above (rather than a parallel code path) so degenerate
  // and normal mode share every line of generation logic except this one.
  if (DEGENERATE) collapseToSectorConstants(companies);

  const schema: Record<string, { unit: string | null; pillar: string; dtype: string; description: string }> = {};
  for (const [name, meta] of Object.entries(FIELD_META)) {
    schema[name] = { unit: meta.unit, pillar: meta.pillar, dtype: meta.dtype, description: meta.description };
  }

  const generatedAt = new Date().toISOString();
  const matrixPayload = {
    schema_version: SCHEMA_VERSION,
    generated_at: generatedAt,
    analysis_year: ANALYSIS_YEAR,
    schema,
    source_priority: SOURCE_PRIORITY,
    urls,
    companies,
  };
  const quotesPayload = { schema_version: SCHEMA_VERSION, generated_at: generatedAt, quotes };

  const matrixOut = resolve(OUT_DIR, "matrix.fixture.json");
  const quotesOut = resolve(OUT_DIR, "quotes.fixture.json");
  writeFileSync(matrixOut, JSON.stringify(matrixPayload));
  writeFileSync(quotesOut, JSON.stringify(quotesPayload));

  // --- coverage report, mirroring export_matrix.py's console summary -------
  const coverage = new Map<string, number>();
  for (const c of companies) for (const f of Object.keys(c.fields)) coverage.set(f, (coverage.get(f) ?? 0) + 1);
  const kb = (s: string) => (Buffer.byteLength(s, "utf-8") / 1024).toFixed(0);
  console.log(`wrote ${matrixOut} -- ${companies.length} companies, ${kb(JSON.stringify(matrixPayload))} KB${DEGENERATE ? " [DEGENERATE]" : ""}`);
  console.log(`wrote ${quotesOut} -- ${kb(JSON.stringify(quotesPayload))} KB`);
  console.log(`fields with real coverage: ${coverage.size} of ${Object.keys(FIELD_META).length}`);
  for (const [f, n] of [...coverage.entries()].sort((a, b) => b[1] - a[1])) {
    console.log(`  ${f.padEnd(32)} ${n}/${companies.length}`);
  }
}

interface FixtureCompany {
  ticker: string;
  sector: string;
  fields: Record<string, Omit<RawFieldRecord, "q">>;
}

/** Forces every company within a sector to share the same `v` for a given
 * field, keyed off whichever company hits that (sector, field) pair first in
 * array order -- deterministic given a fixed CSV row order. Only `v` moves;
 * status/confidence/source/year are untouched; below is that same generated
 * value re-used, not a fresh unrelated magnitude. */
function collapseToSectorConstants(companies: FixtureCompany[]): void {
  const canonical = new Map<string, RawFieldRecord["v"]>();
  for (const c of companies) {
    for (const [field, rec] of Object.entries(c.fields)) {
      const key = `${c.sector}::${field}`;
      if (!canonical.has(key)) canonical.set(key, rec.v);
    }
  }
  for (const c of companies) {
    for (const field of Object.keys(c.fields)) {
      c.fields[field].v = canonical.get(`${c.sector}::${field}`)!;
    }
  }
}

function addField(
  fields: Record<string, RawFieldRecord>,
  quotes: Record<string, Record<string, string>>,
  ticker: string,
  field: string,
  value: number | string | boolean,
  src: string,
  status: RawFieldRecord["st"],
  fy: number,
  urlIdx: number
) {
  fields[field] = {
    v: value, u: FIELD_META[field].unit, fy, src, st: status,
    c: CONFIDENCE_BY_STATUS[status], url: urlIdx,
  };
  const quoteFn = QUOTE_TEMPLATES[field];
  if (quoteFn && status !== "structural") {
    quotes[ticker] ??= {};
    quotes[ticker][field] = quoteFn(value, ticker);
  }
}

main();
