"""Materiality matrix: how much each indicator counts, per GICS sector.

This is a JUDGEMENT, not a derivation. It follows SASB's logic — that what is
financially material differs by industry — but SASB's standards are per-industry
and we work at the 11 GICS sector level, so this is our reading, not SASB's
table. Say that plainly in the pitch and cite SASB as the source of the idea.

Why it exists at all: without it, a bank scores beautifully on carbon intensity
because its emissions are someone else's, and a utility is punished for being in
the business of generating electricity. Sector-relative percentiles fix the
comparison; materiality weights fix the question being asked.

Two properties this file is built to have:
  * Weights are written on ANY scale and normalised to 100 per sector, so
    editing one number does not force you to rebalance twelve others by hand.
  * Every sector row has a written rationale. A weight nobody can justify out
    loud is a weight a judge will find.

Edit the numbers. Then run:
    python -m pipeline.materiality --csv     # human-readable table for review
"""

from __future__ import annotations

import argparse

#: The indicators the framework scores on. `needs` lists the fields each one
#: consumes — an indicator counts as OBSERVED for a company only when every
#: field it needs is present, which is also what drives point opacity.
INDICATORS: dict[str, dict] = {
    # --- P1 Environmental & resource efficiency -------------------------
    "carbon_intensity": {
        "pillar": "P1", "direction": "lower_is_better",
        "needs": ["scope1_tco2e", "revenue_usd"],
        "optional": ["scope2_location_tco2e"],
        "what": "Scope 1 (+2 when available) per $m revenue",
    },
    "energy_mix": {
        "pillar": "P1", "direction": "higher_is_better",
        "needs": ["renewable_electricity_mwh", "total_electricity_mwh"],
        "what": "Share of electricity from low-carbon sources",
    },
    "resource_waste_intensity": {
        "pillar": "P1", "direction": "lower_is_better",
        "needs": ["waste_total_tonnes", "revenue_usd"],
        "optional": ["water_withdrawal_m3", "waste_diverted_pct"],
        "what": "Non-carbon environmental burden per $m revenue",
    },
    "input_efficiency": {
        "pillar": "P1", "direction": "lower_is_better",
        "needs": ["cogs_usd", "revenue_usd"],
        "what": "COGS/revenue — how efficiently inputs become output",
    },
    # --- P2 Transition & structural risk --------------------------------
    "carbon_price_exposure": {
        "pillar": "P2", "direction": "lower_is_better",
        "needs": ["scope1_tco2e", "ebitda_usd"],
        "what": "Margin damage at a shadow carbon price (slider, default $100)",
    },
    "transition_affordability": {
        "pillar": "P2", "direction": "higher_is_better",
        "needs": ["scope1_tco2e", "target_year", "target_reduction_pct",
                  "free_cash_flow_usd"],
        "what": "Can they pay for the transition they promised — THE FLAGSHIP",
    },
    "innovation_momentum": {
        "pillar": "P2", "direction": "higher_is_better",
        "needs": ["sbti_target_validated", "rnd_expense_usd", "revenue_usd"],
        "optional": ["y02_patent_share_pct"],
        "what": "Is capability actually being built — validated target + R&D intensity",
    },
    "structural_disruption": {
        "pillar": "P2", "direction": "lower_is_better",
        "needs": ["risk_hitword_density"],
        "what": "Non-climate shocks that could end the business (Item 1A)",
    },
    # --- P3 Governance & capital stewardship ----------------------------
    "climate_governance": {
        "pillar": "P3", "direction": "higher_is_better",
        "needs": ["has_climate_oversight_committee"],
        "optional": ["has_third_party_assurance", "emissions_boundary_stated",
                     "assurance_level"],
        "what": "Is climate actually governed, not just discussed",
    },
    "compensation_alignment": {
        "pillar": "P3", "direction": "higher_is_better",
        "needs": ["has_clawback_policy", "has_psu_plan"],
        "optional": ["performance_period_years"],
        "what": "Is pay tied to long-term outcomes",
    },
    "board_independence": {
        "pillar": "P3", "direction": "higher_is_better",
        "needs": ["independent_director_count", "board_size"],
        "optional": ["lead_independent_director"],
        "what": "Board composition. DELIBERATELY LOW WEIGHT — weakly related to "
                "sustainability, and a judge will ask why it is here at all",
    },
    "capital_stewardship": {
        "pillar": "P3", "direction": "higher_is_better",
        "needs": ["capex_usd", "buybacks_usd", "dividends_paid_usd"],
        "optional": ["rnd_expense_usd"],
        "what": "(capex + R&D) vs (buybacks + dividends) — the purest say-do test",
    },
    "controversy_record": {
        "pillar": "P3", "direction": "lower_is_better",
        "needs": ["penalty_total_usd", "revenue_usd"],
        "what": "Penalties from court and agency records, not news sentiment",
    },
}

#: Weights on ANY scale; normalised to 100 per sector. Edit freely.
#: Each sector carries a one-line rationale — a weight you cannot justify out
#: loud is a weight that will be challenged.
RAW: dict[str, dict] = {
    "Energy": {
        "_why": "Emissions ARE the product. Transition risk is existential and "
                "the abatement bill is enormous relative to cash flow.",
        "carbon_intensity": 18, "energy_mix": 4, "resource_waste_intensity": 4,
        "input_efficiency": 6, "carbon_price_exposure": 16,
        "transition_affordability": 14, "innovation_momentum": 6,
        "structural_disruption": 8, "climate_governance": 10,
        "compensation_alignment": 3, "board_independence": 2,
        "capital_stewardship": 6, "controversy_record": 3,
    },
    "Utilities": {
        "_why": "Highest absolute Scope 1 in the index and the clearest capex "
                "path out of it. Energy mix is the whole strategy.",
        "carbon_intensity": 18, "energy_mix": 10, "resource_waste_intensity": 3,
        "input_efficiency": 4, "carbon_price_exposure": 14,
        "transition_affordability": 14, "innovation_momentum": 6,
        "structural_disruption": 4, "climate_governance": 10,
        "compensation_alignment": 3, "board_independence": 2,
        "capital_stewardship": 8, "controversy_record": 4,
    },
    "Materials": {
        "_why": "Process emissions are hard to abate (cement, steel). Non-carbon "
                "burden — toxics, water, tailings — matters as much as carbon.",
        "carbon_intensity": 16, "energy_mix": 4, "resource_waste_intensity": 10,
        "input_efficiency": 8, "carbon_price_exposure": 13,
        "transition_affordability": 11, "innovation_momentum": 5,
        "structural_disruption": 4, "climate_governance": 9,
        "compensation_alignment": 3, "board_independence": 2,
        "capital_stewardship": 7, "controversy_record": 8,
    },
    "Industrials": {
        "_why": "Mixed bag — transport and machinery carry real Scope 1, but the "
                "bigger story is whether capex is going into the transition.",
        "carbon_intensity": 13, "energy_mix": 3, "resource_waste_intensity": 5,
        "input_efficiency": 8, "carbon_price_exposure": 10,
        "transition_affordability": 10, "innovation_momentum": 8,
        "structural_disruption": 6, "climate_governance": 10,
        "compensation_alignment": 4, "board_independence": 2,
        "capital_stewardship": 10, "controversy_record": 6,
    },
    "Consumer Staples": {
        "_why": "Agriculture and packaging dominate; water and waste are as "
                "material as carbon. Most of the footprint is Scope 3 we cannot "
                "yet see — weight carbon intensity accordingly, not higher.",
        "carbon_intensity": 11, "energy_mix": 3, "resource_waste_intensity": 11,
        "input_efficiency": 7, "carbon_price_exposure": 8,
        "transition_affordability": 8, "innovation_momentum": 6,
        "structural_disruption": 5, "climate_governance": 11,
        "compensation_alignment": 4, "board_independence": 2,
        "capital_stewardship": 8, "controversy_record": 8,
    },
    "Consumer Discretionary": {
        "_why": "Autos sit here and are a transition story; retail is not. A "
                "sector-level weight is a compromise — flag it in the pitch.",
        "carbon_intensity": 10, "energy_mix": 3, "resource_waste_intensity": 7,
        "input_efficiency": 7, "carbon_price_exposure": 8,
        "transition_affordability": 9, "innovation_momentum": 9,
        "structural_disruption": 7, "climate_governance": 11,
        "compensation_alignment": 4, "board_independence": 2,
        "capital_stewardship": 9, "controversy_record": 6,
    },
    "Information Technology": {
        "_why": "Scope 1 is rounding error; the footprint is purchased "
                "electricity (Scope 2) we do not yet have. Weighting carbon "
                "intensity heavily here would reward asset-light accounting, "
                "not clean operations.",
        "carbon_intensity": 6, "energy_mix": 9, "resource_waste_intensity": 4,
        "input_efficiency": 5, "carbon_price_exposure": 4,
        "transition_affordability": 6, "innovation_momentum": 12,
        "structural_disruption": 8, "climate_governance": 13,
        "compensation_alignment": 5, "board_independence": 3,
        "capital_stewardship": 20, "controversy_record": 5,
    },
    "Communication Services": {
        "_why": "Networks and data centres mean electricity, not smokestacks. "
                "Same asset-light caution as IT.",
        "carbon_intensity": 6, "energy_mix": 9, "resource_waste_intensity": 3,
        "input_efficiency": 5, "carbon_price_exposure": 4,
        "transition_affordability": 6, "innovation_momentum": 10,
        "structural_disruption": 9, "climate_governance": 13,
        "compensation_alignment": 5, "board_independence": 3,
        "capital_stewardship": 18, "controversy_record": 9,
    },
    "Health Care": {
        "_why": "Moderate direct emissions from manufacturing; governance and "
                "capital allocation carry more of the signal.",
        "carbon_intensity": 9, "energy_mix": 5, "resource_waste_intensity": 8,
        "input_efficiency": 6, "carbon_price_exposure": 6,
        "transition_affordability": 7, "innovation_momentum": 9,
        "structural_disruption": 7, "climate_governance": 12,
        "compensation_alignment": 5, "board_independence": 3,
        "capital_stewardship": 15, "controversy_record": 8,
    },
    "Financials": {
        "_why": "Direct emissions are negligible and financed emissions are "
                "Scope 3 we cannot measure. Scoring banks on carbon intensity "
                "measures their office footprint, which is not the question. "
                "Governance, stewardship and enforcement record carry the weight.",
        "carbon_intensity": 4, "energy_mix": 4, "resource_waste_intensity": 2,
        "input_efficiency": 3, "carbon_price_exposure": 3,
        "transition_affordability": 4, "innovation_momentum": 8,
        "structural_disruption": 10, "climate_governance": 18,
        "compensation_alignment": 7, "board_independence": 4,
        "capital_stewardship": 20, "controversy_record": 13,
    },
    "Real Estate": {
        "_why": "Building energy is the footprint, and it is almost entirely "
                "Scope 2. Until that lands, weight energy mix and governance "
                "rather than a Scope 1 figure that says little.",
        "carbon_intensity": 8, "energy_mix": 12, "resource_waste_intensity": 5,
        "input_efficiency": 5, "carbon_price_exposure": 6,
        "transition_affordability": 9, "innovation_momentum": 6,
        "structural_disruption": 7, "climate_governance": 13,
        "compensation_alignment": 5, "board_independence": 3,
        "capital_stewardship": 15, "controversy_record": 6,
    },
}


def matrix() -> dict[str, dict[str, float]]:
    """{sector: {indicator: weight}}, each row normalised to sum to 100."""
    out = {}
    for sector, row in RAW.items():
        ws = {k: float(v) for k, v in row.items() if not k.startswith("_")}
        unknown = set(ws) - set(INDICATORS)
        if unknown:
            raise ValueError(f"{sector}: unknown indicator(s) {sorted(unknown)}")
        missing = set(INDICATORS) - set(ws)
        if missing:
            raise ValueError(f"{sector}: no weight given for {sorted(missing)} "
                             f"— a missing weight is silently zero, so say 0 explicitly")
        total = sum(ws.values()) or 1.0
        out[sector] = {k: round(100 * v / total, 2) for k, v in ws.items()}
    return out


def pillar_weights() -> dict[str, dict[str, float]]:
    """Implied P1/P2/P3 split per sector — the sanity check people will look at."""
    m = matrix()
    out = {}
    for sector, ws in m.items():
        agg: dict[str, float] = {}
        for ind, w in ws.items():
            p = INDICATORS[ind]["pillar"]
            agg[p] = round(agg.get(p, 0) + w, 1)
        out[sector] = agg
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="materiality matrix")
    ap.add_argument("--csv", action="store_true", help="write data/materiality.csv")
    a = ap.parse_args()
    m, pw = matrix(), pillar_weights()
    inds = list(INDICATORS)

    print(f"{'sector':<24}" + "".join(f"{i[:11]:>12}" for i in inds))
    print("-" * (24 + 12 * len(inds)))
    for sector in RAW:
        print(f"{sector:<24}" + "".join(f"{m[sector][i]:>12.1f}" for i in inds))
    print(f"\n{'sector':<24}{'P1':>8}{'P2':>8}{'P3':>8}")
    print("-" * 48)
    for sector, p in pw.items():
        print(f"{sector:<24}{p.get('P1',0):>8.1f}{p.get('P2',0):>8.1f}{p.get('P3',0):>8.1f}")

    if a.csv:
        import csv as _csv
        from .common.paths import DATA
        path = DATA / "materiality.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["sector", "rationale"] + inds)
            for sector in RAW:
                w.writerow([sector, RAW[sector]["_why"]] +
                           [m[sector][i] for i in inds])
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
