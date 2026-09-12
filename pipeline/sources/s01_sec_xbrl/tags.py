"""XBRL tag fallback chains. HAND-WRITTEN — the scaffold generator never
touches this file (fields.py is generated and will be overwritten).

Revenue splits across 4+ tags depending on the registrant's taxonomy choices.
The chain lives here as DATA so caller code never grows an if-ladder and the
order stays reviewable in one place. First tag that yields a value wins, and
`extracted_by` records which one did — that choice is a judgement and someone
will need to audit it.
"""

from __future__ import annotations

TAG_CHAINS: dict[str, list[str]] = {
    # Order is preference, and preference means TOP LINE first. The ASC 606
    # "RevenueFromContractWithCustomer*" tags are a SUBSET of total revenue for
    # utilities and insurers (they exclude lease, derivative and premium
    # income), so the sector-specific total-revenue concepts sit ahead of them.
    # For companies that have no such concept the extra entries simply miss.
    "revenue_usd": [
        # `Revenues` FIRST. RevenueFromContractWithCustomer* is by definition a
        # COMPONENT of total revenue — revenue from contracts with customers —
        # so for REITs (rental income) and insurers (premiums) it captures a
        # sliver. Measured on the real cache: of 210 companies tagging both,
        # 42 were understated, ESS by 201x and MET by 32x. Every one of them was
        # Real Estate or Financials.
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RegulatedAndUnregulatedOperatingRevenue",   # utilities (NEE, DUK, SO...)
        "RevenuesNetOfInterestExpense",              # banks
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "InterestAndDividendIncomeOperating",        # banks, fallback
        "PremiumsEarnedNet",                         # insurers, fallback
    ],
    "ebit_usd": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "capex_usd": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "rnd_expense_usd": ["ResearchAndDevelopmentExpense"],
    "cogs_usd": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "buybacks_usd": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends_paid_usd": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
    "energy_cost_usd": ["UtilitiesOperatingExpense", "FuelCosts"],
}

# Derived, not tagged. BOTH legs must be present or the field is not_disclosed:
# a partial FCF is worse than none, because the affordability ratio divides by
# it and a half-number becomes a confident wrong answer.
DERIVED = {
    "free_cash_flow_usd": {
        "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities",
                                "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
        "minus_capex": TAG_CHAINS["capex_usd"],
    },
    "ebitda_usd": {
        "ebit": TAG_CHAINS["ebit_usd"],
        "plus_dep_amort": ["DepreciationDepletionAndAmortization",
                           "DepreciationAmortizationAndAccretionNet",
                           "DepreciationAndAmortization"],
    },
}
