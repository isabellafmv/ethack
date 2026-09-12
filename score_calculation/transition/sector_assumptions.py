"""Documented assumptions used by transition_score.py that aren't backed by
a live data source in data_sources/. Every number here is an estimate --
change it when you have a real one (same convention as the "blue text"
assumptions in the project's own data-source register).
"""

# Illustrative marginal abatement cost per tCO2e, by GICS sector, loosely
# based on published abatement-cost-curve literature (McKinsey's Global GHG
# Abatement Cost Curve, IEA Net Zero Roadmap sectoral cost ranges): power-
# sector decarbonization (renewables/storage) is among the cheapest near-term
# levers, while hard-to-abate heavy industry (steel, cement, chemicals) and
# deep oil & gas decarbonization (CCS) are markedly more expensive. Not a
# per-company or per-project estimate -- a single order-of-magnitude number
# per sector to make the affordability metric's arithmetic transparent.
SECTOR_ABATEMENT_COST_USD_PER_TCO2E = {
    "Utilities": 30,
    "Energy": 100,
    "Materials": 120,
    "Industrials": 75,
    "Consumer Staples": 60,
    "Consumer Discretionary": 50,
    "Health Care": 50,
    "Information Technology": 40,
    "Financials": 40,
    "Real Estate": 45,
    "Communication Services": 40,
}
DEFAULT_ABATEMENT_COST_USD_PER_TCO2E = 60  # fallback for any unmapped sector

# Implied absolute Scope 1+2 reduction required by target year, by SBTi
# near-term ambition tier. The 1.5C figure (42% by the target year) is SBTi's
# own published minimum-ambition criterion for near-term targets under the
# Corporate Net-Zero Standard; well-below-2C and 2C figures are approximate
# mid-points of their respective (looser, retired-criteria-era) trajectories
# and are the least certain numbers in this module.
TARGET_REDUCTION_PCT_BY_TIER = {
    "targets_set_1.5c": 0.42,
    "targets_set_2c": 0.30,   # covers both "Well-below 2°C" and "2°C" classifications
    "net_zero_validated": 0.42,  # near-term glidepath; net_zero_year itself implies ~90%+ by its own year
    "committed": None,   # ambition not yet quantified -- treated like no_target
    "no_target": None,
}
