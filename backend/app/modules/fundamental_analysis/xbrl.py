from datetime import date


XBRL_METRIC_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "eps_basic": ("EarningsPerShareBasic",),
    "eps_diluted": ("EarningsPerShareDiluted",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditures": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "cash_and_equivalents": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "current_assets": ("AssetsCurrent",),
    "current_liabilities": ("LiabilitiesCurrent",),
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
    "short_term_debt": (
        "ShortTermBorrowings",
        "CommercialPaper",
        "LongTermDebtCurrent",
        "CurrentPortionOfLongTermDebt",
        "ShortTermDebtCurrent",
    ),
    "long_term_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "shareholders_equity": (
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ),
    "shares_outstanding": (
        "EntityCommonStockSharesOutstanding",
        "CommonStocksIncludingAdditionalPaidInCapitalMember",
    ),
}

CONCEPT_TO_METRIC = {
    concept: metric
    for metric, concepts in XBRL_METRIC_CONCEPTS.items()
    for concept in concepts
}


def normalized_metric_for(concept: str) -> str | None:
    return CONCEPT_TO_METRIC.get(concept)


def classify_period(period_start: date | None, period_end: date) -> str:
    """Classify by duration, never by filing form alone."""
    if period_start is None:
        return "instant"
    duration_days = (period_end - period_start).days + 1
    if duration_days <= 0:
        raise ValueError("period_end must not be before period_start")
    if 70 <= duration_days <= 110:
        return "quarterly"
    if 330 <= duration_days <= 380:
        return "annual"
    if 111 <= duration_days < 330:
        return "ytd"
    return "duration_other"
