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
    "revenue_usd": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
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
