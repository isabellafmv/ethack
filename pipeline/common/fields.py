"""THE CONTRACT. The canonical field vocabulary.

This matters more than the record shape. If one agent emits `scope1_tco2e` and
another emits `scope_1_emissions`, the join silently produces two half-empty
columns and nobody notices until the dashboard looks wrong at hour 20.

Rules:
  * A source may only emit fields listed here.
  * To add a field, add it HERE first, then declare it in the source's fields.py.
  * Never rename a field mid-build. Add a new one and deprecate the old.

`unit` is a canonical token, not free text. Unit conversion happens in the
source package, before the record is written -- never downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- canonical units -------------------------------------------------------
UNITS = {
    "tco2e",              # tonnes CO2 equivalent
    "usd",                # US dollars, absolute (not millions)
    "mwh",
    "m3",                 # cubic metres
    "tonnes",
    "pct",                # 0-100, NOT 0-1
    "count",
    "years",
    "year",               # a calendar year used as a value, e.g. target_year
    "kgco2e_per_mwh",
    "index",              # unitless score from an external methodology
    None,                 # bool / str fields
}

PILLARS = {"P1", "P2", "P3", "X"}


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    dtype: type
    unit: str | None
    pillar: str
    description: str
    sources: tuple[str, ...]      # which source IDs are allowed to emit this
    timeless: bool = False        # if True, fiscal_year must be 0
    #: A SNAPSHOT is true as of a date, not for a period: market cap, an SBTi
    #: status, an agency rating. Pinning an analysis year must constrain annual
    #: FLOWS (revenue, capex, Scope 1) so ratios stay within one period — but
    #: blanking snapshots would throw away data that has no period to mismatch.
    snapshot: bool = False

    def check(self, obs) -> None:
        from .schema import SchemaError, TIMELESS

        if self.dtype is float:
            if isinstance(obs.value, bool) or not isinstance(obs.value, (int, float)):
                raise SchemaError(f"{obs.ticker}/{self.name}: expected number, got {obs.value!r}")
        elif self.dtype is int:
            if isinstance(obs.value, bool) or not isinstance(obs.value, int):
                raise SchemaError(f"{obs.ticker}/{self.name}: expected int, got {obs.value!r}")
        elif not isinstance(obs.value, self.dtype):
            raise SchemaError(
                f"{obs.ticker}/{self.name}: expected {self.dtype.__name__}, got {obs.value!r}"
            )

        if obs.unit != self.unit:
            raise SchemaError(
                f"{obs.ticker}/{self.name}: unit must be {self.unit!r}, got {obs.unit!r}. "
                f"Convert in the source package, not downstream."
            )

        if self.unit == "pct" and not (0 <= float(obs.value) <= 100):
            raise SchemaError(f"{obs.ticker}/{self.name}: pct is 0-100, got {obs.value!r}")

        if self.timeless and obs.fiscal_year != TIMELESS:
            raise SchemaError(f"{obs.ticker}/{self.name}: timeless field needs fiscal_year=0")
        if not self.timeless and obs.fiscal_year == TIMELESS:
            raise SchemaError(f"{obs.ticker}/{self.name}: needs a real fiscal_year, got 0")

        # A derived source is written "<origin>~<who>", e.g. "S15~team" for a
        # teammate's own GHGRP matching. It validates against its origin but
        # keeps a distinct identity in the primary key, so the derived value and
        # our own extraction coexist and can be compared rather than one
        # silently overwriting the other.
        origin = obs.source.split("~")[0]
        if origin not in self.sources and obs.source != "imputed":
            raise SchemaError(
                f"{obs.ticker}/{self.name}: source {obs.source} is not declared for this "
                f"field (allowed: {', '.join(self.sources)}, or <one of those>~derived). "
                f"Widen the spec deliberately."
            )


def _f(name, dtype, unit, pillar, description, sources, timeless=False,
       snapshot=False):
    return FieldSpec(name, dtype, unit, pillar, description, tuple(sources),
                     timeless, snapshot)


_SPECS = [
    # === X  identity & universe ===========================================
    _f("cik", str, None, "X", "SEC Central Index Key, zero-padded to 10", ["S08"], True),
    _f("legal_name", str, None, "X", "Registrant legal name as filed", ["S05", "S06", "S08"], True),
    _f("lei", str, None, "X", "Legal Entity Identifier", ["S06"], True),
    _f("ultimate_parent_lei", str, None, "X", "GLEIF Level 2 ultimate parent", ["S06"], True),
    _f("gics_sector", str, None, "X", "One of 11 GICS sectors; the normalisation bucket", ["S08"], True),
    _f("gics_sub_industry", str, None, "X", "GICS sub-industry", ["S08"], True),
    _f("hq_state", str, None, "X", "HQ state, used to constrain entity matching", ["S08"], True),
    _f("subsidiary_count", int, "count", "X", "Subsidiaries listed in Exhibit 21", ["S05"]),
    _f("market_cap_usd", float, "usd", "X", "Market cap; bubble size on the 3D map", ["S07"], snapshot=True),
    _f("shares_outstanding", float, "count", "X", "Shares outstanding", ["S01", "S07"], snapshot=True),

    # === X  validation only -- NEVER an input =============================
    _f("esg_risk_score_external", float, "index", "X",
       "Sustainalytics-derived risk score. VALIDATION ONLY: this is the thing we "
       "are trying to beat. Must never enter a pillar score.", ["S14"], snapshot=True),
    _f("esg_controversy_level_external", str, None, "X",
       "External controversy band. VALIDATION ONLY.", ["S14"], snapshot=True),

    # === P1  environmental & resource efficiency ==========================
    _f("scope1_tco2e", float, "tco2e", "P1",
       "Scope 1. EPA-measured (S15) and self-reported (S10) coexist by design -- "
       "the gap between them is the say-do signal.", ["S15", "S10"]),
    _f("scope2_location_tco2e", float, "tco2e", "P1", "Scope 2, location-based", ["S10", "S19"]),
    _f("scope2_market_tco2e", float, "tco2e", "P1",
       "Scope 2, market-based. A renewable claim that moves this but NOT the "
       "location-based figure is an unbundled REC purchase -- flag, do not credit.", ["S10"]),
    _f("scope3_tco2e", float, "tco2e", "P1", "Scope 3, as disclosed", ["S10", "S13"]),
    _f("ghg_facility_count", int, "count", "P1",
       "Reporting facilities in GHGRP. Track YoY: a divestiture looks identical to "
       "an emissions cut. Movement excludes the company from trajectory scoring.", ["S15"]),
    _f("renewable_electricity_mwh", float, "mwh", "P1", "Renewable electricity procured/generated", ["S10", "S21"]),
    _f("total_electricity_mwh", float, "mwh", "P1", "Total electricity consumed", ["S10"]),
    _f("grid_intensity_kgco2e_per_mwh", float, "kgco2e_per_mwh", "P1",
       "eGRID subregion intensity for the company's facility footprint", ["S19"]),
    _f("water_withdrawal_m3", float, "m3", "P1", "Total water withdrawn", ["S10"]),
    _f("waste_total_tonnes", float, "tonnes", "P1", "Total waste generated", ["S10"]),
    _f("waste_diverted_pct", float, "pct", "P1", "Share of waste diverted from landfill", ["S10"]),
    _f("cogs_usd", float, "usd", "P1", "Cost of goods sold; input efficiency numerator", ["S01"]),
    _f("energy_cost_usd", float, "usd", "P1", "Energy cost where separately disclosed", ["S01", "S02"]),

    # === P2  transition & structural risk =================================
    _f("revenue_usd", float, "usd", "P2",
       "Revenue. Splits across 4+ XBRL tags -- the fallback chain lives in "
       "sources/s01_sec_xbrl/fields.py, not in caller code.", ["S01"]),
    _f("ebit_usd", float, "usd", "P2", "Operating income", ["S01"]),
    _f("ebitda_usd", float, "usd", "P2", "EBIT + D&A; carbon-price exposure denominator", ["S01"]),
    _f("free_cash_flow_usd", float, "usd", "P2",
       "CFO - capex. The affordability denominator: can they pay for what they promised.", ["S01"]),
    _f("capex_usd", float, "usd", "P2", "PaymentsToAcquirePropertyPlantAndEquipment", ["S01"]),
    _f("clean_capex_usd", float, "usd", "P2",
       "Low-carbon portion of capex, from Item 7 MD&A. Expect ~1/3 hit rate -- "
       "the low rate is itself a finding, report it.", ["S02"]),
    _f("rnd_expense_usd", float, "usd", "P2", "R&D expense", ["S01"]),
    _f("green_revenue_share_pct", float, "pct", "P2",
       "Revenue from low-carbon segments. The classification is OURS, not the "
       "company's -- per-segment rationale must be published alongside.", ["S02"]),
    _f("sbti_target_validated", bool, None, "P2", "Has an SBTi-validated target", ["S09"], snapshot=True),
    _f("sbti_target_type", str, None, "P2", "near-term | net-zero | commitment", ["S09"], snapshot=True),
    _f("target_year", int, "year", "P2", "Stated target year", ["S09", "S10", "S02"], snapshot=True),
    _f("target_baseline_year", int, "year", "P2", "Baseline year for the target", ["S09", "S10"], snapshot=True),
    _f("target_reduction_pct", float, "pct", "P2", "Stated reduction vs baseline", ["S09", "S10"], snapshot=True),
    _f("target_scope_coverage", str, None, "P2", "Which scopes the target covers", ["S09", "S10"], snapshot=True),
    _f("risk_hitword_density", float, "index", "P2",
       "Item 1A hitwords weighted by POSITION and proximity to intensifiers. "
       "Raw counts measure document length -- ship the text-vs-XBRL discrepancy, "
       "not the count. No negation handling: name that limit in the pitch.", ["S02", "S03"]),
    _f("risk_first_factor_topic", str, None, "P2",
       "Topic of the FIRST risk factor. What comes first is what management fears.", ["S02"]),
    _f("y02_patent_share_pct", float, "pct", "P2",
       "Y02 (climate-mitigation) share of recent filings. True zero for financials "
       "and services -- report as zero-with-explanation, never null.", ["S24"]),
    _f("lobbying_spend_usd", float, "usd", "P2", "Senate LDA reported spend", ["S12"]),
    _f("lobbying_climate_flag", bool, None, "P2",
       "Lobbied on a climate-relevant issue code. A flag, not a score -- "
       "attribution via trade associations is messy.", ["S12"]),

    # === P3  governance & capital stewardship =============================
    _f("has_climate_oversight_committee", bool, None, "P3",
       "Named board committee with explicit climate oversight", ["S04", "S10"]),
    _f("comp_tied_to_emissions_target", bool, None, "P3",
       "Executive comp linked to an emissions metric", ["S04", "S10"]),
    _f("has_third_party_assurance", bool, None, "P3", "Emissions externally assured", ["S04", "S10"]),
    _f("assurance_level", str, None, "P3", "limited | reasonable | none", ["S04", "S10"]),
    _f("emissions_boundary_stated", bool, None, "P3",
       "Reporting boundary explicitly stated (operational/equity control)", ["S04", "S10"]),
    _f("has_clawback_policy", bool, None, "P3",
       "Clawback provision. WATCH NEGATION: 'we do not maintain a clawback policy' "
       "contains the keyword and means the opposite.", ["S04"]),
    _f("has_psu_plan", bool, None, "P3", "Performance share units in the LTI plan", ["S04"]),
    _f("performance_period_years", float, "years", "P3", "LTI performance period", ["S04"]),
    _f("independent_director_count", int, "count", "P3", "Independent directors", ["S04"]),
    _f("board_size", int, "count", "P3", "Total directors", ["S04"]),
    _f("lead_independent_director", bool, None, "P3", "Lead independent director present", ["S04"]),
    _f("buybacks_usd", float, "usd", "P3", "Share repurchases", ["S01"]),
    _f("dividends_paid_usd", float, "usd", "P3", "Dividends paid", ["S01"]),
    _f("penalty_total_usd", float, "usd", "P3",
       "Penalties from COURT AND AGENCY RECORDS, not news sentiment. News-based "
       "controversy scores measure media volume, which tracks company size.", ["S11", "S18"]),
    _f("penalty_count", int, "count", "P3", "Number of penalty records", ["S11", "S18"]),
]

FIELDS: dict[str, FieldSpec] = {s.name: s for s in _SPECS}

#: Fields that must never enter a pillar score, only the validation slide.
VALIDATION_ONLY = {"esg_risk_score_external", "esg_controversy_level_external"}


def fields_for_source(source_id: str) -> list[FieldSpec]:
    return [s for s in _SPECS if source_id in s.sources]


def fields_for_pillar(pillar: str) -> list[FieldSpec]:
    return [s for s in _SPECS if s.pillar == pillar]
