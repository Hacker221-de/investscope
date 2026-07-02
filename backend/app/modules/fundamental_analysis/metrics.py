from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.time import ensure_utc, utc_now
from app.models import CompanyFiling, FinancialFact
from app.modules.data_sources.freshness import evaluate_market_data_freshness
from app.modules.fundamental_analysis.xbrl import (
    XBRL_METRIC_CONCEPTS,
    normalized_metric_for,
)
from app.modules.fundamental_analysis.parsing import normalize_fiscal_year
from app.repositories.fundamentals import FundamentalRepository
from app.repositories.market_data import MarketDataRepository

PeriodType = Literal["quarterly", "annual", "ttm"]

CANONICAL_METRICS = tuple(XBRL_METRIC_CONCEPTS) + (
    "free_cash_flow",
    "total_debt",
)
DERIVED_METRICS = (
    "revenue_growth_yoy",
    "net_income_growth_yoy",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "free_cash_flow_margin",
    "current_ratio",
    "debt_to_equity",
    "return_on_assets",
    "return_on_equity",
    "shares_dilution_yoy",
)
VALUATION_METRICS = (
    "market_cap",
    "price_to_earnings",
    "price_to_sales",
    "price_to_free_cash_flow",
)
FLOW_METRICS = {
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "eps_basic",
    "eps_diluted",
    "operating_cash_flow",
    "capital_expenditures",
}
INSTANT_METRICS = {
    "cash_and_equivalents",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "short_term_debt",
    "long_term_debt",
    "shareholders_equity",
    "shares_outstanding",
}
CONCEPT_PRIORITY = {
    metric: {concept: index for index, concept in enumerate(concepts)}
    for metric, concepts in XBRL_METRIC_CONCEPTS.items()
}
DERIVABLE_QUARTER_METRICS = FLOW_METRICS
CASH_FLOW_METRICS = {"operating_cash_flow", "capital_expenditures"}
SHORT_BORROWING_CONCEPTS = {"ShortTermBorrowings", "CommercialPaper"}
CURRENT_DEBT_CONCEPTS = {
    "LongTermDebtCurrent",
    "CurrentPortionOfLongTermDebt",
    "ShortTermDebtCurrent",
}
NONCURRENT_DEBT_CONCEPTS = {"LongTermDebtNoncurrent"}
AGGREGATE_LONG_DEBT_CONCEPTS = {"LongTermDebt"}


@dataclass(slots=True)
class CanonicalSelection:
    fact: FinancialFact
    alternatives: list[FinancialFact]
    selection_reason: str
    is_repeated_comparative: bool
    is_restated: bool
    has_conflict: bool
    warnings: list[str]
    repeated_comparative_facts: list[FinancialFact]


@dataclass(slots=True)
class MetricValue:
    value: Decimal | None
    unit: str | None
    source_facts: list[FinancialFact]
    warnings: list[str]
    calculation: str | None = None
    selection: CanonicalSelection | None = None
    derived: bool = False
    derivation_method: str | None = None
    confidence: str | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    frame: str | None = None
    calculation_facts: list[FinancialFact] = field(default_factory=list)
    is_repeated_comparative: bool = False
    is_restated: bool = False
    has_conflict: bool = False
    excluded_comparative_identities: set[str] = field(default_factory=set)


@dataclass(slots=True)
class PeriodBucket:
    start: date
    end: date
    period_type: str
    values: dict[str, MetricValue]
    representative: FinancialFact | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    frame: str | None = None


def _publication_time(fact: FinancialFact, filing: CompanyFiling | None) -> datetime:
    if filing is not None and filing.acceptance_datetime is not None:
        return ensure_utc(filing.acceptance_datetime)
    if filing is not None:
        return datetime.combine(filing.filing_date, time.min, tzinfo=UTC)
    return ensure_utc(fact.filed_at)


def _concept_rank(fact: FinancialFact) -> tuple[int, int]:
    priority = CONCEPT_PRIORITY.get(_fact_metric(fact) or "", {})
    return (
        priority.get(fact.concept, len(priority) + 100),
        0 if fact.taxonomy == "us-gaap" else 1,
    )


def _fact_metric(fact: FinancialFact) -> str | None:
    return fact.normalized_metric or normalized_metric_for(fact.concept)


def select_canonical_fact(
    facts: list[FinancialFact],
    filings: dict[str, CompanyFiling],
) -> CanonicalSelection:
    if not facts:
        raise ValueError("Canonical selection requires at least one fact")
    ordered = sorted(
        facts,
        key=lambda fact: (
            _publication_time(fact, filings.get(fact.accession_number)),
            _concept_rank(fact),
            fact.id,
        ),
    )
    best_rank = min(_concept_rank(fact) for fact in ordered)
    preferred = [fact for fact in ordered if _concept_rank(fact) == best_rank]
    selected = preferred[0]
    is_restated = False
    repeated_candidates: list[FinancialFact] = []
    previous_by_concept: dict[str, list[Decimal]] = defaultdict(list)

    for candidate in ordered:
        previous_values = previous_by_concept[candidate.concept]
        filing = filings.get(candidate.accession_number)
        if candidate.value in previous_values and filing is not None and not filing.is_amendment:
            repeated_candidates.append(candidate)
        previous_values.append(candidate.value)

    selected_publication = _publication_time(
        selected, filings.get(selected.accession_number)
    )
    for candidate in preferred[1:]:
        filing = filings.get(candidate.accession_number)
        candidate_publication = _publication_time(candidate, filing)
        if candidate.value != selected.value and candidate_publication > selected_publication:
            selected = candidate
            selected_publication = candidate_publication
            is_restated = True
        elif (
            candidate.value == selected.value
            and filing is not None
            and filing.is_amendment
            and candidate_publication >= selected_publication
        ):
            selected = candidate
            selected_publication = candidate_publication

    selected_filing = filings.get(selected.accession_number)
    if selected_filing is not None and selected_filing.is_amendment:
        first_value = preferred[0].value
        is_restated = is_restated or selected.value != first_value

    repeated_candidates = [
        fact for fact in repeated_candidates if fact.id != selected.id
    ]
    is_repeated = bool(repeated_candidates)

    distinct_values = {fact.value for fact in ordered}
    has_conflict = len(distinct_values) > 1
    warnings: list[str] = []
    if has_conflict:
        warnings.append("conflicting_facts")
    if is_repeated:
        warnings.append("repeated_comparative")
    if is_restated:
        warnings.append("restated_value")

    if selected_filing is not None and selected_filing.is_amendment:
        reason = "amended_filing"
    elif is_restated:
        reason = "latest_restatement"
    elif len({fact.concept for fact in ordered}) > 1:
        reason = "concept_priority"
    elif is_repeated:
        reason = "original_value_retained"
    else:
        reason = "single_source"

    return CanonicalSelection(
        fact=selected,
        alternatives=[fact for fact in ordered if fact.id != selected.id],
        selection_reason=reason,
        is_repeated_comparative=is_repeated,
        is_restated=is_restated,
        has_conflict=has_conflict,
        warnings=warnings,
        repeated_comparative_facts=repeated_candidates,
    )


class FundamentalMetricsService:
    def __init__(
        self,
        session: Session,
        *,
        market_provider: str,
        market_stale_after_hours: int,
        market_session_close_hour_utc: int,
    ) -> None:
        self.session = session
        self.fundamentals = FundamentalRepository(session)
        self.market = MarketDataRepository(session)
        self.market_provider = market_provider
        self.market_stale_after_hours = market_stale_after_hours
        self.market_session_close_hour_utc = market_session_close_hour_utc
        self._derivation_warnings: list[str] = []
        self._fiscal_year_end: str | None = None
        self._filings_context: dict[str, CompanyFiling] = {}

    def _canonical_selections(
        self,
        *,
        asset_id: int,
        as_of: datetime,
    ) -> tuple[list[CanonicalSelection], dict[str, CompanyFiling]]:
        facts = self.fundamentals.list_facts(
            asset_id=asset_id,
            as_of=as_of,
            limit=1_000_000,
        )
        facts = [fact for fact in facts if _fact_metric(fact) is not None]
        filings_list = self.fundamentals.list_filings(
            asset_id=asset_id,
            as_of=as_of,
            limit=100_000,
        )
        filings = {filing.accession_number: filing for filing in filings_list}
        grouped: dict[
            tuple[str, str, date | None, date, str], list[FinancialFact]
        ] = defaultdict(list)
        for fact in facts:
            metric = _fact_metric(fact)
            assert metric is not None
            grouped[(
                metric,
                fact.unit,
                fact.period_start,
                fact.period_end,
                fact.period_type,
            )].append(fact)
        return [select_canonical_fact(group, filings) for group in grouped.values()], filings

    def _effective_fiscal_year(self, fact: FinancialFact) -> int:
        return normalize_fiscal_year(
            fact.fiscal_year,
            period_end=fact.period_end,
            period_type=fact.period_type,
            fiscal_period=fact.fiscal_period,
            form=fact.form,
            filing=self._filings_context.get(fact.accession_number),
            fiscal_year_end=self._fiscal_year_end,
        )

    def _selection_value(self, selection: CanonicalSelection) -> MetricValue:
        return MetricValue(
            value=selection.fact.value,
            unit=selection.fact.unit,
            source_facts=[selection.fact, *selection.alternatives],
            warnings=list(selection.warnings),
            selection=selection,
            fiscal_year=self._effective_fiscal_year(selection.fact),
            fiscal_period=selection.fact.fiscal_period,
            frame=selection.fact.frame,
            calculation_facts=[selection.fact],
            is_repeated_comparative=selection.is_repeated_comparative,
            is_restated=selection.is_restated,
            has_conflict=selection.has_conflict,
            excluded_comparative_identities={
                fact.fact_identity
                for fact in selection.repeated_comparative_facts
            },
        )

    def _period_buckets(
        self,
        selections: list[CanonicalSelection],
        period_type: Literal["quarterly", "annual"],
    ) -> list[PeriodBucket]:
        buckets: dict[tuple[date, date], PeriodBucket] = {}
        instant: list[CanonicalSelection] = []
        for selection in selections:
            fact = selection.fact
            if fact.period_type == "instant":
                instant.append(selection)
                continue
            if fact.period_type != period_type or fact.period_start is None:
                continue
            key = (fact.period_start, fact.period_end)
            bucket = buckets.setdefault(
                key,
                PeriodBucket(
                    start=fact.period_start,
                    end=fact.period_end,
                    period_type=period_type,
                    values={},
                    representative=fact,
                    fiscal_year=self._effective_fiscal_year(fact),
                    fiscal_period=fact.fiscal_period,
                    frame=fact.frame,
                ),
            )
            metric = _fact_metric(fact)
            if metric is not None:
                current = bucket.values.get(metric)
                candidate = self._selection_value(selection)
                if current is None or _concept_rank(fact) < _concept_rank(current.source_facts[0]):
                    bucket.values[metric] = candidate
                    if metric == "revenue":
                        bucket.representative = fact

        for selection in instant:
            fact = selection.fact
            metric = _fact_metric(fact)
            if metric is None:
                continue
            for bucket in buckets.values():
                if bucket.end == fact.period_end:
                    bucket.values[metric] = self._selection_value(selection)

        instant_by_metric: dict[str, list[CanonicalSelection]] = defaultdict(list)
        for selection in instant:
            metric = _fact_metric(selection.fact)
            if metric is not None:
                instant_by_metric[metric].append(selection)
        for bucket in buckets.values():
            for metric, candidates in instant_by_metric.items():
                if metric in bucket.values:
                    continue
                nearest = min(
                    candidates,
                    key=lambda candidate: abs((candidate.fact.period_end - bucket.end).days),
                )
                if abs((nearest.fact.period_end - bucket.end).days) <= 45:
                    bucket.values[metric] = self._selection_value(nearest)

        result = sorted(buckets.values(), key=lambda bucket: (bucket.end, bucket.start))
        for bucket in result:
            self._add_base_computed_metrics(bucket)
        return result

    @staticmethod
    def _dedupe_facts(values: list[MetricValue]) -> list[FinancialFact]:
        facts: list[FinancialFact] = []
        seen: set[str] = set()
        for value in values:
            for fact in value.source_facts:
                if fact.fact_identity not in seen:
                    facts.append(fact)
                    seen.add(fact.fact_identity)
        return facts

    @staticmethod
    def _dedupe_calculation_facts(values: list[MetricValue]) -> list[FinancialFact]:
        facts: list[FinancialFact] = []
        seen: set[str] = set()
        for value in values:
            for fact in value.calculation_facts:
                if fact.fact_identity not in seen:
                    facts.append(fact)
                    seen.add(fact.fact_identity)
        return facts

    def _assert_derived_value_invariants(self, value: MetricValue) -> None:
        if value.value is None or not value.derived:
            return
        if not value.calculation_facts:
            raise ValueError(
                f"Available derived metric {value.derivation_method!r} has no calculation components"
            )
        component_ids = [fact.fact_identity for fact in value.calculation_facts]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("Derived metric contains duplicate calculation components")
        source_ids = {fact.fact_identity for fact in value.source_facts}
        if not set(component_ids).issubset(source_ids):
            raise ValueError("Calculation component is missing from source facts audit")
        offending = set(component_ids) & value.excluded_comparative_identities
        if offending:
            raise ValueError(
                "Repeated comparative fact entered a calculation: "
                f"method={value.derivation_method!r} identities={sorted(offending)}"
            )

    @staticmethod
    def _combined_flags(values: list[MetricValue]) -> tuple[bool, bool, bool]:
        return (
            any(value.is_repeated_comparative for value in values),
            any(value.is_restated for value in values),
            any(value.has_conflict for value in values),
        )

    @staticmethod
    def _combined_excluded_comparatives(values: list[MetricValue]) -> set[str]:
        return set().union(*(
            value.excluded_comparative_identities for value in values
        )) if values else set()

    @staticmethod
    def _combined_warnings(
        values: list[MetricValue], *additional: str
    ) -> list[str]:
        repeated = any(value.is_repeated_comparative for value in values)
        warnings = [
            warning
            for value in values
            for warning in value.warnings
            if warning != "repeated_comparative"
        ]
        warnings.extend(additional)
        if repeated:
            warnings.append("repeated_comparative")
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _selection_is_unambiguous(value: MetricValue) -> bool:
        selection = value.selection
        if selection is None:
            return "conflicting_facts" not in value.warnings
        if not selection.has_conflict:
            return True
        return selection.selection_reason in {
            "amended_filing",
            "latest_restatement",
            "concept_priority",
        }

    def _validate_derivation_operands(
        self,
        metric: str,
        values: list[MetricValue],
    ) -> tuple[bool, list[str], str | None]:
        if any(value.value is None for value in values):
            return False, ["derived_quarter_missing_source"], None
        units = {value.unit for value in values}
        if len(units) != 1:
            return False, ["derived_quarter_unit_mismatch"], None
        if not all(self._selection_is_unambiguous(value) for value in values):
            return False, ["derived_quarter_conflict"], None
        allowed = set(XBRL_METRIC_CONCEPTS.get(metric, ()))
        concepts = {
            fact.concept
            for value in values
            for fact in value.source_facts
        }
        if not concepts or not concepts.issubset(allowed):
            return False, ["derived_quarter_incompatible_concepts"], None
        warnings: list[str] = []
        confidence = "high"
        if len(concepts) > 1:
            warnings.append("mixed_concepts")
            confidence = "medium"
        if metric in {"eps_basic", "eps_diluted"}:
            unit = next(iter(units)) or ""
            if "share" not in unit.lower():
                return False, ["derived_quarter_incompatible_units"], None
            warnings.append("eps_aggregation")
            confidence = "medium"
        return True, warnings, confidence

    @staticmethod
    def _fiscal_value(
        buckets: list[PeriodBucket],
        *,
        metric: str,
        fiscal_year: int,
        fiscal_period: str,
    ) -> tuple[PeriodBucket, MetricValue] | None:
        matches: list[tuple[PeriodBucket, MetricValue]] = []
        for bucket in buckets:
            value = bucket.values.get(metric)
            if value is None or value.value is None:
                continue
            year = value.fiscal_year
            period = value.fiscal_period
            if year == fiscal_year and period == fiscal_period:
                matches.append((bucket, value))
        if len(matches) != 1:
            return None
        return matches[0]

    def _selection_for_fiscal_period(
        self,
        selections: list[CanonicalSelection],
        *,
        metric: str,
        period_type: str,
        fiscal_year: int,
        fiscal_period: str,
    ) -> CanonicalSelection | None:
        matches = [
            selection
            for selection in selections
            if _fact_metric(selection.fact) == metric
            and selection.fact.period_type == period_type
            and self._effective_fiscal_year(selection.fact) == fiscal_year
            and selection.fact.fiscal_period == fiscal_period
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    @staticmethod
    def _quarter_bucket(
        quarterly: list[PeriodBucket],
        *,
        start: date,
        end: date,
        fiscal_year: int,
        fiscal_period: str,
    ) -> PeriodBucket:
        for bucket in quarterly:
            if bucket.start == start and bucket.end == end:
                if bucket.fiscal_year is None:
                    bucket.fiscal_year = fiscal_year
                if bucket.fiscal_period is None:
                    bucket.fiscal_period = fiscal_period
                return bucket
        bucket = PeriodBucket(
            start=start,
            end=end,
            period_type="quarterly",
            values={},
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
        )
        quarterly.append(bucket)
        return bucket

    def _derived_quarter_value(
        self,
        *,
        metric: str,
        operands: list[MetricValue],
        result: Decimal,
        calculation: str,
        derivation_method: str,
        fiscal_year: int,
        fiscal_period: str,
    ) -> MetricValue | None:
        valid, warnings, confidence = self._validate_derivation_operands(
            metric, operands
        )
        if not valid:
            self._derivation_warnings.extend(warnings)
            return None
        repeated, restated, conflict = self._combined_flags(operands)
        return MetricValue(
            value=result,
            unit=operands[0].unit,
            source_facts=self._dedupe_facts(operands),
            warnings=self._combined_warnings(operands, *warnings),
            calculation=calculation,
            derived=True,
            derivation_method=derivation_method,
            confidence=confidence,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            calculation_facts=self._dedupe_calculation_facts(operands),
            is_repeated_comparative=repeated,
            is_restated=restated,
            has_conflict=conflict,
            excluded_comparative_identities=self._combined_excluded_comparatives(
                operands
            ),
        )

    def _derive_cash_flow_quarters(
        self,
        quarterly: list[PeriodBucket],
        annual: list[PeriodBucket],
        selections: list[CanonicalSelection],
    ) -> None:
        fiscal_years = {
            self._effective_fiscal_year(selection.fact)
            for selection in selections
            if _fact_metric(selection.fact) in CASH_FLOW_METRICS
        }
        for fiscal_year in sorted(fiscal_years):
            for metric in CASH_FLOW_METRICS:
                q1_match = self._fiscal_value(
                    quarterly,
                    metric=metric,
                    fiscal_year=fiscal_year,
                    fiscal_period="Q1",
                )
                six_month = self._selection_for_fiscal_period(
                    selections,
                    metric=metric,
                    period_type="ytd",
                    fiscal_year=fiscal_year,
                    fiscal_period="Q2",
                )
                nine_month = self._selection_for_fiscal_period(
                    selections,
                    metric=metric,
                    period_type="ytd",
                    fiscal_year=fiscal_year,
                    fiscal_period="Q3",
                )
                annual_match = self._fiscal_value(
                    annual,
                    metric=metric,
                    fiscal_year=fiscal_year,
                    fiscal_period="FY",
                )
                definitions: list[
                    tuple[str, date, date, list[MetricValue], Decimal, str]
                ] = []
                if six_month is not None:
                    if q1_match is None:
                        self._derivation_warnings.append("derived_quarter_missing_source")
                    else:
                        q1_bucket, q1_value = q1_match
                        if (
                            six_month.fact.period_start != q1_bucket.start
                            or q1_bucket.end >= six_month.fact.period_end
                            or not 70 <= (
                                six_month.fact.period_end - q1_bucket.end
                            ).days <= 110
                        ):
                            self._derivation_warnings.append("derived_quarter_invalid_periods")
                        else:
                            six_value = self._selection_value(six_month)
                            definitions.append((
                                "Q2",
                                q1_bucket.end + timedelta(days=1),
                                six_month.fact.period_end,
                                [six_value, q1_value],
                                six_value.value - q1_value.value,
                                "six_month_ytd - three_month_ytd",
                            ))
                if nine_month is not None:
                    if six_month is None:
                        self._derivation_warnings.append("derived_quarter_missing_source")
                    elif (
                        nine_month.fact.period_start != six_month.fact.period_start
                        or six_month.fact.period_end >= nine_month.fact.period_end
                        or not 70 <= (
                            nine_month.fact.period_end - six_month.fact.period_end
                        ).days <= 110
                    ):
                        self._derivation_warnings.append("derived_quarter_invalid_periods")
                    else:
                        six_value = self._selection_value(six_month)
                        nine_value = self._selection_value(nine_month)
                        definitions.append((
                            "Q3",
                            six_month.fact.period_end + timedelta(days=1),
                            nine_month.fact.period_end,
                            [nine_value, six_value],
                            nine_value.value - six_value.value,
                            "nine_month_ytd - six_month_ytd",
                        ))
                if annual_match is not None:
                    annual_bucket, annual_value = annual_match
                    if nine_month is None:
                        self._derivation_warnings.append("derived_quarter_missing_source")
                    elif (
                        annual_bucket.start != nine_month.fact.period_start
                        or nine_month.fact.period_end >= annual_bucket.end
                        or not 70 <= (
                            annual_bucket.end - nine_month.fact.period_end
                        ).days <= 110
                    ):
                        self._derivation_warnings.append("derived_quarter_invalid_periods")
                    else:
                        nine_value = self._selection_value(nine_month)
                        definitions.append((
                            "Q4",
                            nine_month.fact.period_end + timedelta(days=1),
                            annual_bucket.end,
                            [annual_value, nine_value],
                            annual_value.value - nine_value.value,
                            "annual - nine_month_ytd",
                        ))
                for fiscal_period, start, end, operands, result, calculation in definitions:
                    target = self._quarter_bucket(
                        quarterly,
                        start=start,
                        end=end,
                        fiscal_year=fiscal_year,
                        fiscal_period=fiscal_period,
                    )
                    existing = target.values.get(metric)
                    if existing is not None and existing.value is not None:
                        continue
                    derived = self._derived_quarter_value(
                        metric=metric,
                        operands=operands,
                        result=result,
                        calculation=calculation,
                        derivation_method="ytd_difference",
                        fiscal_year=fiscal_year,
                        fiscal_period=fiscal_period,
                    )
                    if derived is not None:
                        target.values[metric] = derived

    def _derive_fiscal_q4(
        self,
        quarterly: list[PeriodBucket],
        annual: list[PeriodBucket],
    ) -> None:
        for annual_bucket in annual:
            for metric in DERIVABLE_QUARTER_METRICS:
                annual_value = annual_bucket.values.get(metric)
                if annual_value is None or annual_value.value is None:
                    continue
                fiscal_year = annual_value.fiscal_year
                if fiscal_year is None:
                    self._derivation_warnings.append("derived_quarter_missing_fiscal_year")
                    continue
                quarter_matches = [
                    self._fiscal_value(
                        quarterly,
                        metric=metric,
                        fiscal_year=fiscal_year,
                        fiscal_period=f"Q{index}",
                    )
                    for index in range(1, 4)
                ]
                if any(match is None for match in quarter_matches):
                    self._derivation_warnings.append("derived_quarter_missing_source")
                    continue
                resolved = [match for match in quarter_matches if match is not None]
                quarter_buckets = [match[0] for match in resolved]
                quarter_values = [match[1] for match in resolved]
                if (
                    annual_bucket.start != quarter_buckets[0].start
                    or any(
                        current.start <= previous.end
                        for previous, current in zip(quarter_buckets, quarter_buckets[1:])
                    )
                    or any(
                        not 1 <= (current.start - previous.end).days <= 14
                        for previous, current in zip(quarter_buckets, quarter_buckets[1:])
                    )
                    or quarter_buckets[-1].end >= annual_bucket.end
                    or not 70 <= (
                        annual_bucket.end - quarter_buckets[-1].end
                    ).days <= 110
                ):
                    self._derivation_warnings.append("derived_quarter_invalid_periods")
                    continue
                start = quarter_buckets[-1].end + timedelta(days=1)
                target = self._quarter_bucket(
                    quarterly,
                    start=start,
                    end=annual_bucket.end,
                    fiscal_year=fiscal_year,
                    fiscal_period="Q4",
                )
                existing = target.values.get(metric)
                if existing is not None and existing.value is not None:
                    continue
                operands = [annual_value, *quarter_values]
                result = annual_value.value - sum(
                    (value.value for value in quarter_values if value.value is not None),
                    Decimal(0),
                )
                derived = self._derived_quarter_value(
                    metric=metric,
                    operands=operands,
                    result=result,
                    calculation="annual - q1 - q2 - q3",
                    derivation_method="annual_minus_three_quarters",
                    fiscal_year=fiscal_year,
                    fiscal_period="Q4",
                )
                if derived is not None:
                    target.values[metric] = derived

    def _derive_missing_quarters(
        self,
        quarterly: list[PeriodBucket],
        annual: list[PeriodBucket],
        selections: list[CanonicalSelection],
    ) -> None:
        self._derive_cash_flow_quarters(quarterly, annual, selections)
        self._derive_fiscal_q4(quarterly, annual)
        annual_by_end = {bucket.end: bucket for bucket in annual}
        for bucket in quarterly:
            if bucket.fiscal_period != "Q4":
                continue
            annual_bucket = annual_by_end.get(bucket.end)
            if annual_bucket is None:
                continue
            for metric in INSTANT_METRICS:
                if metric not in bucket.values and metric in annual_bucket.values:
                    bucket.values[metric] = annual_bucket.values[metric]
        quarterly.sort(key=lambda bucket: (bucket.end, bucket.start))
        for bucket in quarterly:
            self._add_base_computed_metrics(bucket)

    @staticmethod
    def _unavailable(*warnings: str, calculation: str | None = None) -> MetricValue:
        return MetricValue(
            value=None,
            unit=None,
            source_facts=[],
            warnings=list(warnings),
            calculation=calculation,
        )

    def _add_base_computed_metrics(self, bucket: PeriodBucket) -> None:
        operating = bucket.values.get("operating_cash_flow")
        capex = bucket.values.get("capital_expenditures")
        if operating and capex and operating.value is not None and capex.value is not None:
            if operating.unit == capex.unit:
                repeated, restated, conflict = self._combined_flags(
                    [operating, capex]
                )
                bucket.values["free_cash_flow"] = MetricValue(
                    value=operating.value - capex.value,
                    unit=operating.unit,
                    source_facts=self._dedupe_facts([operating, capex]),
                    warnings=self._combined_warnings([operating, capex]),
                    calculation="operating_cash_flow - capital_expenditures",
                    derived=True,
                    derivation_method=(
                        "free_cash_flow_from_derived_quarters"
                        if operating.derivation_method in {
                            "annual_minus_three_quarters", "ytd_difference"
                        } or capex.derivation_method in {
                            "annual_minus_three_quarters", "ytd_difference"
                        }
                        else "free_cash_flow"
                    ),
                    confidence=(
                        "medium"
                        if "medium" in {operating.confidence, capex.confidence}
                        else "high"
                    ),
                    fiscal_year=operating.fiscal_year or capex.fiscal_year,
                    fiscal_period=operating.fiscal_period or capex.fiscal_period,
                    calculation_facts=self._dedupe_calculation_facts(
                        [operating, capex]
                    ),
                    is_repeated_comparative=repeated,
                    is_restated=restated,
                    has_conflict=conflict,
                    excluded_comparative_identities=self._combined_excluded_comparatives(
                        [operating, capex]
                    ),
                )
            else:
                bucket.values["free_cash_flow"] = self._unavailable(
                    "unit_mismatch", calculation="free_cash_flow"
                )
        else:
            bucket.values["free_cash_flow"] = self._unavailable(
                "missing_metric", calculation="free_cash_flow"
            )

        bucket.values["total_debt"] = self._total_debt(bucket)

    @staticmethod
    def _debt_facts(bucket: PeriodBucket) -> dict[str, FinancialFact]:
        by_concept: dict[str, FinancialFact] = {}
        excluded = set().union(*(
            value.excluded_comparative_identities
            for metric in ("short_term_debt", "long_term_debt")
            if (value := bucket.values.get(metric)) is not None
        ))
        for metric in ("short_term_debt", "long_term_debt"):
            value = bucket.values.get(metric)
            if value is None:
                continue
            candidates = list(value.source_facts)
            if value.selection is not None:
                candidates.extend(value.selection.alternatives)
            for fact in candidates:
                if fact.fact_identity in excluded:
                    continue
                existing = by_concept.get(fact.concept)
                if existing is None or (fact.filed_at, fact.id) > (
                    existing.filed_at, existing.id
                ):
                    by_concept[fact.concept] = fact
        return by_concept

    @staticmethod
    def _first_debt_fact(
        facts: dict[str, FinancialFact], concepts: tuple[str, ...]
    ) -> FinancialFact | None:
        return next((facts[concept] for concept in concepts if concept in facts), None)

    def _total_debt(self, bucket: PeriodBucket) -> MetricValue:
        facts = self._debt_facts(bucket)
        input_values = [
            value
            for metric in ("short_term_debt", "long_term_debt")
            if (value := bucket.values.get(metric)) is not None
        ]
        short = self._first_debt_fact(
            facts, ("ShortTermBorrowings", "CommercialPaper")
        )
        current = self._first_debt_fact(
            facts,
            (
                "LongTermDebtCurrent",
                "CurrentPortionOfLongTermDebt",
                "ShortTermDebtCurrent",
            ),
        )
        aggregate = self._first_debt_fact(facts, ("LongTermDebt",))
        noncurrent = self._first_debt_fact(facts, ("LongTermDebtNoncurrent",))

        components: list[FinancialFact]
        calculation: str
        if aggregate is not None:
            # LongTermDebt is an aggregate. Its current/non-current disclosures
            # are provenance alternatives, never extra addends.
            components = [aggregate]
            calculation = "LongTermDebt"
            if short is not None:
                components.append(short)
                calculation = "LongTermDebt + short_term_borrowings"
        elif noncurrent is not None and current is not None:
            components = [noncurrent, current]
            calculation = "LongTermDebtNoncurrent + current_portion_of_long_term_debt"
            if short is not None:
                components.append(short)
                calculation += " + short_term_borrowings"
        else:
            return self._unavailable("missing_metric", calculation="total_debt")

        if len({fact.unit for fact in components}) != 1:
            return self._unavailable("unit_mismatch", calculation="total_debt")
        repeated, restated, conflict = self._combined_flags(input_values)
        return MetricValue(
            value=sum((fact.value for fact in components), Decimal(0)),
            unit=components[0].unit,
            source_facts=self._dedupe_facts(input_values),
            warnings=self._combined_warnings(input_values),
            calculation=calculation,
            derived=True,
            derivation_method="non_overlapping_debt_components",
            confidence="high",
            fiscal_year=(bucket.fiscal_year or (
                bucket.representative.fiscal_year if bucket.representative else None
            )),
            fiscal_period=(bucket.fiscal_period or (
                bucket.representative.fiscal_period if bucket.representative else None
            )),
            calculation_facts=components,
            is_repeated_comparative=repeated,
            is_restated=restated,
            has_conflict=conflict,
            excluded_comparative_identities=self._combined_excluded_comparatives(
                input_values
            ),
        )

    @staticmethod
    def _valid_quarter_window(window: list[PeriodBucket]) -> bool:
        if len(window) != 4 or len({bucket.end for bucket in window}) != 4:
            return False
        span_days = (window[-1].end - window[0].start).days + 1
        if span_days < 330 or span_days > 385:
            return False
        for previous, current in zip(window, window[1:]):
            if current.start <= previous.end:
                return False
            gap = (current.start - previous.end).days
            if gap < 1 or gap > 14:
                return False
        return True

    @staticmethod
    def _valid_fiscal_sequence(values: list[MetricValue]) -> bool:
        if len(values) != 4:
            return False
        labels = [(value.fiscal_year, value.fiscal_period) for value in values]
        if any(year is None or period not in {"Q1", "Q2", "Q3", "Q4"}
               for year, period in labels):
            return False
        order = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}
        for (previous_year, previous_period), (year, period) in zip(labels, labels[1:]):
            assert previous_year is not None and previous_period is not None
            assert year is not None and period is not None
            previous_index = order[previous_period]
            expected_index = previous_index % 4 + 1
            expected_year = previous_year + (1 if previous_index == 4 else 0)
            if order[period] != expected_index or year != expected_year:
                return False
        return True

    def _ttm_buckets(
        self,
        quarterly: list[PeriodBucket],
        annual: list[PeriodBucket],
        *,
        annual_fallback: bool,
    ) -> list[PeriodBucket]:
        result: list[PeriodBucket] = []
        for index in range(3, len(quarterly)):
            window = quarterly[index - 3:index + 1]
            if not self._valid_quarter_window(window):
                continue
            bucket = PeriodBucket(
                start=window[0].start,
                end=window[-1].end,
                period_type="ttm",
                values={},
                representative=window[-1].representative,
                fiscal_year=window[-1].fiscal_year,
                fiscal_period=window[-1].fiscal_period,
                frame=window[-1].frame,
            )
            for metric in FLOW_METRICS:
                values = [item.values.get(metric) for item in window]
                if (
                    all(value is not None and value.value is not None for value in values)
                    and len({value.unit for value in values if value is not None}) == 1
                    and self._valid_fiscal_sequence(
                        [value for value in values if value is not None]
                    )
                ):
                    available = [value for value in values if value is not None]
                    repeated, restated, conflict = self._combined_flags(available)
                    bucket.values[metric] = MetricValue(
                        value=sum((value.value for value in available if value.value is not None), Decimal(0)),
                        unit=available[0].unit,
                        source_facts=self._dedupe_facts(available),
                        warnings=self._combined_warnings(available),
                        calculation="sum of four non-overlapping canonical quarters",
                        derived=True,
                        derivation_method="ttm_four_quarters",
                        confidence=(
                            "medium"
                            if any(value.confidence == "medium" for value in available)
                            else "high"
                        ),
                        fiscal_year=available[-1].fiscal_year,
                        fiscal_period=available[-1].fiscal_period,
                        calculation_facts=self._dedupe_calculation_facts(available),
                        is_repeated_comparative=repeated,
                        is_restated=restated,
                        has_conflict=conflict,
                        excluded_comparative_identities=self._combined_excluded_comparatives(
                            available
                        ),
                    )
                else:
                    bucket.values[metric] = self._unavailable(
                        "incomplete_ttm", calculation="ttm"
                    )
            for metric in INSTANT_METRICS:
                if metric in window[-1].values:
                    bucket.values[metric] = window[-1].values[metric]
            self._add_base_computed_metrics(bucket)
            result.append(bucket)

        if not result and annual_fallback and annual:
            latest = annual[-1]
            fallback = PeriodBucket(
                start=latest.start,
                end=latest.end,
                period_type="ttm",
                values={},
                representative=latest.representative,
                fiscal_year=latest.fiscal_year,
                fiscal_period=latest.fiscal_period,
                frame=latest.frame,
            )
            for metric, value in latest.values.items():
                fallback.values[metric] = MetricValue(
                    value=value.value,
                    unit=value.unit,
                    source_facts=value.source_facts,
                    warnings=list(dict.fromkeys(value.warnings + ["annual_fallback"])),
                    calculation=value.calculation or "annual fallback",
                    selection=value.selection,
                    derived=value.derived,
                    derivation_method=value.derivation_method,
                    confidence=value.confidence,
                    fiscal_year=value.fiscal_year,
                    fiscal_period=value.fiscal_period,
                    frame=value.frame,
                    calculation_facts=value.calculation_facts,
                    is_repeated_comparative=value.is_repeated_comparative,
                    is_restated=value.is_restated,
                    has_conflict=value.has_conflict,
                    excluded_comparative_identities=set(
                        value.excluded_comparative_identities
                    ),
                )
            result.append(fallback)
        return result

    @staticmethod
    def _previous_year_bucket(
        buckets: list[PeriodBucket], current: PeriodBucket
    ) -> PeriodBucket | None:
        candidates = [
            bucket for bucket in buckets
            if bucket.end < current.end and 330 <= (current.end - bucket.end).days <= 400
        ]
        return max(candidates, key=lambda bucket: bucket.end, default=None)

    def _ratio(
        self,
        numerator: MetricValue | None,
        denominator: MetricValue | None,
        *,
        multiplier: Decimal,
        calculation: str,
        require_positive_denominator: bool = True,
    ) -> MetricValue:
        inputs = [value for value in (numerator, denominator) if value is not None]
        source = self._dedupe_facts(inputs)
        calculation_facts = self._dedupe_calculation_facts(inputs)
        repeated, restated, conflict = self._combined_flags(inputs)
        common = {
            "calculation_facts": calculation_facts,
            "is_repeated_comparative": repeated,
            "is_restated": restated,
            "has_conflict": conflict,
            "excluded_comparative_identities": self._combined_excluded_comparatives(
                inputs
            ),
        }
        if numerator is None or denominator is None or numerator.value is None or denominator.value is None:
            return MetricValue(
                None, None, source,
                self._combined_warnings(inputs, "missing_metric"), calculation,
                **common,
            )
        if denominator.value == 0:
            return MetricValue(
                None, None, source,
                self._combined_warnings(inputs, "zero_denominator"), calculation,
                **common,
            )
        if require_positive_denominator and denominator.value < 0:
            return MetricValue(
                None, None, source,
                self._combined_warnings(inputs, "invalid_denominator"), calculation,
                **common,
            )
        return MetricValue(
            numerator.value / denominator.value * multiplier,
            "%" if multiplier == Decimal(100) else "ratio",
            source,
            self._combined_warnings(inputs),
            calculation,
            derived=True,
            derivation_method="ratio",
            calculation_facts=calculation_facts,
            is_repeated_comparative=repeated,
            is_restated=restated,
            has_conflict=conflict,
            excluded_comparative_identities=self._combined_excluded_comparatives(
                inputs
            ),
        )

    def _add_derived_metrics(self, buckets: list[PeriodBucket]) -> None:
        for bucket in buckets:
            values = bucket.values
            previous = self._previous_year_bucket(buckets, bucket)
            previous_values = previous.values if previous else {}
            values["revenue_growth_yoy"] = self._growth(
                values.get("revenue"), previous_values.get("revenue"), "revenue_growth_yoy"
            )
            values["net_income_growth_yoy"] = self._growth(
                values.get("net_income"),
                previous_values.get("net_income"),
                "net_income_growth_yoy",
            )
            values["gross_margin"] = self._ratio(
                values.get("gross_profit"), values.get("revenue"),
                multiplier=Decimal(100), calculation="gross_profit / revenue",
            )
            values["operating_margin"] = self._ratio(
                values.get("operating_income"), values.get("revenue"),
                multiplier=Decimal(100), calculation="operating_income / revenue",
            )
            values["net_margin"] = self._ratio(
                values.get("net_income"), values.get("revenue"),
                multiplier=Decimal(100), calculation="net_income / revenue",
            )
            values["free_cash_flow_margin"] = self._ratio(
                values.get("free_cash_flow"), values.get("revenue"),
                multiplier=Decimal(100), calculation="free_cash_flow / revenue",
            )
            values["current_ratio"] = self._ratio(
                values.get("current_assets"), values.get("current_liabilities"),
                multiplier=Decimal(1), calculation="current_assets / current_liabilities",
            )
            values["debt_to_equity"] = self._ratio(
                values.get("total_debt"), values.get("shareholders_equity"),
                multiplier=Decimal(1), calculation="total_debt / shareholders_equity",
            )
            values["return_on_assets"] = self._ratio(
                values.get("net_income"), values.get("total_assets"),
                multiplier=Decimal(100), calculation="net_income / total_assets",
            )
            values["return_on_equity"] = self._ratio(
                values.get("net_income"), values.get("shareholders_equity"),
                multiplier=Decimal(100), calculation="net_income / shareholders_equity",
            )
            values["shares_dilution_yoy"] = self._growth(
                values.get("shares_outstanding"),
                previous_values.get("shares_outstanding"),
                "shares_dilution_yoy",
            )

    def _growth(
        self,
        current: MetricValue | None,
        previous: MetricValue | None,
        calculation: str,
    ) -> MetricValue:
        inputs = [value for value in (current, previous) if value is not None]
        source = self._dedupe_facts(inputs)
        calculation_facts = self._dedupe_calculation_facts(inputs)
        repeated, restated, conflict = self._combined_flags(inputs)
        common = {
            "calculation_facts": calculation_facts,
            "is_repeated_comparative": repeated,
            "is_restated": restated,
            "has_conflict": conflict,
            "excluded_comparative_identities": self._combined_excluded_comparatives(
                inputs
            ),
        }
        if current is None or previous is None or current.value is None or previous.value is None:
            return MetricValue(
                None, None, source,
                self._combined_warnings(inputs, "missing_metric"), calculation,
                **common,
            )
        if previous.value == 0:
            return MetricValue(
                None, None, source,
                self._combined_warnings(inputs, "zero_denominator"), calculation,
                **common,
            )
        if previous.value < 0:
            return MetricValue(
                None, None, source,
                self._combined_warnings(inputs, "invalid_denominator"), calculation,
                **common,
            )
        return MetricValue(
            (current.value - previous.value) / previous.value * Decimal(100),
            "%",
            source,
            self._combined_warnings(inputs),
            calculation,
            derived=True,
            derivation_method="growth",
            calculation_facts=calculation_facts,
            is_repeated_comparative=repeated,
            is_restated=restated,
            has_conflict=conflict,
            excluded_comparative_identities=self._combined_excluded_comparatives(
                inputs
            ),
        )

    def _market_price(self, *, asset_id: int, as_of: datetime) -> tuple[Any | None, bool]:
        bar = self.market.latest_at_or_before(asset_id, self.market_provider, as_of)
        if bar is None:
            return None, False
        freshness = evaluate_market_data_freshness(
            timeframe=bar.timeframe,
            event_time=bar.event_time,
            received_at=bar.received_at,
            stale_after_hours=self.market_stale_after_hours,
            session_close_hour_utc=self.market_session_close_hour_utc,
            now=as_of,
        )
        return bar, freshness.is_stale

    def _add_valuation(
        self,
        *,
        asset_id: int,
        as_of: datetime,
        buckets: list[PeriodBucket],
        ttm_buckets: list[PeriodBucket],
    ) -> dict[str, Any] | None:
        if not buckets:
            return None
        target = buckets[-1]
        bar, is_stale = self._market_price(asset_id=asset_id, as_of=as_of)
        price_view = None
        if bar is not None and bar.close is not None:
            price_view = {
                "value": bar.close,
                "provider": bar.provider,
                "event_time": bar.event_time,
                "received_at": bar.received_at,
                "is_stale": is_stale,
            }
            if is_stale:
                target.values.setdefault(
                    "market_cap", self._unavailable("stale_market_price")
                )
        shares = target.values.get("shares_outstanding")
        if shares is None and ttm_buckets:
            shares = ttm_buckets[-1].values.get("shares_outstanding")
        if bar is None or bar.close is None:
            for metric in VALUATION_METRICS:
                target.values[metric] = self._unavailable("missing_market_price", calculation=metric)
            return price_view
        if shares is None or shares.value is None:
            for metric in VALUATION_METRICS:
                target.values[metric] = self._unavailable("missing_shares", calculation=metric)
            return price_view

        market_cap = bar.close * shares.value
        price_warnings = ["stale_market_price"] if is_stale else []
        shares_flags = self._combined_flags([shares])
        target.values["market_cap"] = MetricValue(
            value=market_cap,
            unit="USD",
            source_facts=shares.source_facts,
            warnings=self._combined_warnings([shares], *price_warnings),
            calculation="market_price * shares_outstanding",
            derived=True,
            derivation_method="market_valuation",
            calculation_facts=shares.calculation_facts,
            is_repeated_comparative=shares_flags[0],
            is_restated=shares_flags[1],
            has_conflict=shares_flags[2],
            excluded_comparative_identities=set(
                shares.excluded_comparative_identities
            ),
        )
        ttm = ttm_buckets[-1] if ttm_buckets else None
        denominators = {
            "price_to_earnings": ttm.values.get("net_income") if ttm else None,
            "price_to_sales": ttm.values.get("revenue") if ttm else None,
            "price_to_free_cash_flow": ttm.values.get("free_cash_flow") if ttm else None,
        }
        for metric, denominator in denominators.items():
            inputs = [value for value in (shares, denominator) if value is not None]
            source = self._dedupe_facts(inputs)
            calculation_facts = self._dedupe_calculation_facts(inputs)
            repeated, restated, conflict = self._combined_flags(inputs)
            if denominator is None or denominator.value is None:
                target.values[metric] = MetricValue(
                    value=None,
                    unit=None,
                    source_facts=source,
                    warnings=self._combined_warnings(inputs, "incomplete_ttm"),
                    calculation=metric,
                    calculation_facts=calculation_facts,
                    is_repeated_comparative=repeated,
                    is_restated=restated,
                    has_conflict=conflict,
                    excluded_comparative_identities=self._combined_excluded_comparatives(
                        inputs
                    ),
                )
            elif denominator.value <= 0:
                warning = "negative_net_income" if metric == "price_to_earnings" else "invalid_denominator"
                target.values[metric] = MetricValue(
                    value=None,
                    unit=None,
                    source_facts=source,
                    warnings=self._combined_warnings(inputs, warning),
                    calculation=metric,
                    calculation_facts=calculation_facts,
                    is_repeated_comparative=repeated,
                    is_restated=restated,
                    has_conflict=conflict,
                    excluded_comparative_identities=self._combined_excluded_comparatives(
                        inputs
                    ),
                )
            else:
                target.values[metric] = MetricValue(
                    value=market_cap / denominator.value,
                    unit="ratio",
                    source_facts=source,
                    warnings=self._combined_warnings(inputs, *price_warnings),
                    calculation=f"market_cap / {metric.removeprefix('price_to_').replace('_', ' ')}",
                    derived=True,
                    derivation_method="market_valuation",
                    calculation_facts=calculation_facts,
                    is_repeated_comparative=repeated,
                    is_restated=restated,
                    has_conflict=conflict,
                    excluded_comparative_identities=self._combined_excluded_comparatives(
                        inputs
                    ),
                )
        return price_view

    def _fact_view(
        self, fact: FinancialFact, filing: CompanyFiling | None
    ) -> dict[str, Any]:
        return {
            "id": fact.id,
            "value": fact.value,
            "unit": fact.unit,
            "taxonomy": fact.taxonomy,
            "concept": fact.concept,
            "period_start": fact.period_start,
            "period_end": fact.period_end,
            "period_type": fact.period_type,
            "fiscal_year": self._effective_fiscal_year(fact),
            "fiscal_period": fact.fiscal_period,
            "frame": fact.frame,
            "filed_at": fact.filed_at,
            "form": fact.form,
            "accession_number": fact.accession_number,
            "acceptance_datetime": filing.acceptance_datetime if filing else None,
            "filing_url": filing.filing_url if filing else None,
            "is_amendment": filing.is_amendment if filing else fact.form.endswith("/A"),
            "ingestion_method": fact.ingestion_method,
            "source_filename": fact.source_filename,
        }

    def _calculation_component_view(
        self, fact: FinancialFact, filing: CompanyFiling | None
    ) -> dict[str, Any]:
        metric = _fact_metric(fact)
        if metric is None:
            raise ValueError("Calculation component has no normalized metric")
        return {
            "id": fact.id,
            "identity": fact.fact_identity,
            "metric": metric,
            "value": fact.value,
            "unit": fact.unit,
            "start": fact.period_start,
            "end": fact.period_end,
            "fiscal_year": self._effective_fiscal_year(fact),
            "fiscal_period": fact.fiscal_period,
            "form": fact.form,
            "accession_number": fact.accession_number,
            "filed": fact.filed_at,
            "frame": fact.frame,
            "is_amendment": (
                filing.is_amendment if filing else fact.form.endswith("/A")
            ),
            # Canonical calculation facts explicitly exclude detected repeated
            # comparative alternatives.
            "is_repeated_comparative": False,
            "source_filename": fact.source_filename,
            "ingestion_method": fact.ingestion_method,
        }

    def _metric_point(
        self,
        *,
        metric: str,
        bucket: PeriodBucket,
        value: MetricValue,
        filings: dict[str, CompanyFiling],
        include_alternatives: bool,
    ) -> dict[str, Any]:
        selection = value.selection
        self._assert_derived_value_invariants(value)
        selected_view = (
            self._fact_view(selection.fact, filings.get(selection.fact.accession_number))
            if selection else None
        )
        alternatives = (
            [self._fact_view(fact, filings.get(fact.accession_number)) for fact in selection.alternatives]
            if selection and include_alternatives else []
        )
        unique_source_facts: list[FinancialFact] = []
        seen_fact_ids: set[str] = set()
        for fact in value.source_facts:
            if fact.fact_identity not in seen_fact_ids:
                unique_source_facts.append(fact)
                seen_fact_ids.add(fact.fact_identity)
        source_facts = [
            self._fact_view(fact, filings.get(fact.accession_number))
            for fact in unique_source_facts
        ]
        calculation_components = [
            self._calculation_component_view(
                fact, filings.get(fact.accession_number)
            )
            for fact in value.calculation_facts
        ] if value.derived else []
        is_repeated = (
            selection.is_repeated_comparative
            if selection else value.is_repeated_comparative
        )
        warnings = [
            warning for warning in value.warnings
            if warning != "repeated_comparative"
        ]
        if is_repeated:
            warnings.append("repeated_comparative")
        return {
            "metric": metric,
            "value": value.value,
            "unit": value.unit,
            "period_start": selection.fact.period_start if selection else bucket.start,
            "period_end": selection.fact.period_end if selection else bucket.end,
            "period_type": selection.fact.period_type if selection else bucket.period_type,
            "fiscal_year": value.fiscal_year or bucket.fiscal_year or (
                self._effective_fiscal_year(bucket.representative)
                if bucket.representative else None
            ),
            "fiscal_period": selection.fact.fiscal_period if selection else (
                value.fiscal_period or bucket.fiscal_period or (
                    bucket.representative.fiscal_period if bucket.representative else None
                )
            ),
            "frame": selection.fact.frame if selection else (
                value.frame or bucket.frame or (
                    bucket.representative.frame if bucket.representative else None
                )
            ),
            "selected_fact": selected_view,
            "alternative_facts": alternatives,
            "source_facts": source_facts,
            "calculation_components": calculation_components,
            "selection_reason": (
                selection.selection_reason
                if selection else "derived_quarter" if bucket.period_type == "quarterly"
                and value.derived and value.fiscal_period in {
                    "Q1", "Q2", "Q3", "Q4"
                } and value.derivation_method in {
                    "annual_minus_three_quarters", "ytd_difference",
                    "free_cash_flow_from_derived_quarters",
                } else "calculated"
            ),
            "is_repeated_comparative": is_repeated,
            "is_restated": selection.is_restated if selection else value.is_restated,
            "has_conflict": selection.has_conflict if selection else value.has_conflict,
            "warnings": list(dict.fromkeys(warnings)),
            "calculation": value.calculation,
            "derived": value.derived,
            "derivation_method": value.derivation_method,
            "confidence": value.confidence,
            "status": "available" if value.value is not None else "unavailable",
        }

    def build_metrics(
        self,
        *,
        symbol: str,
        period_type: PeriodType,
        as_of: datetime | None,
        limit: int,
        offset: int,
        include_alternatives: bool,
        annual_fallback: bool,
    ) -> dict[str, Any]:
        asset = self.fundamentals.get_asset(symbol.upper())
        if asset is None:
            raise LookupError("Asset not found")
        self._derivation_warnings = []
        effective_as_of = ensure_utc(as_of) if as_of is not None else utc_now()
        selections, filings = self._canonical_selections(
            asset_id=asset.id, as_of=effective_as_of
        )
        profile = self.fundamentals.get_profile(asset.id)
        self._fiscal_year_end = profile.fiscal_year_end if profile else None
        self._filings_context = filings
        quarterly = self._period_buckets(selections, "quarterly")
        annual = self._period_buckets(selections, "annual")
        self._derive_missing_quarters(quarterly, annual, selections)
        ttm = self._ttm_buckets(
            quarterly, annual, annual_fallback=annual_fallback
        )
        all_buckets = {
            "quarterly": quarterly,
            "annual": annual,
            "ttm": ttm,
        }[period_type]
        self._add_derived_metrics(all_buckets)
        market_price = self._add_valuation(
            asset_id=asset.id,
            as_of=effective_as_of,
            buckets=all_buckets,
            ttm_buckets=ttm,
        )

        latest_first = list(reversed(all_buckets))
        selected_buckets = list(reversed(latest_first[offset:offset + limit]))
        metrics: dict[str, list[dict[str, Any]]] = defaultdict(list)
        global_warnings: list[str] = list(self._derivation_warnings)
        for bucket in selected_buckets:
            for metric, value in bucket.values.items():
                point = self._metric_point(
                    metric=metric,
                    bucket=bucket,
                    value=value,
                    filings=filings,
                    include_alternatives=include_alternatives,
                )
                metrics[metric].append(point)
                global_warnings.extend(point["warnings"])
        if market_price is not None and market_price["is_stale"]:
            global_warnings.append("stale_market_price")

        expected = set(CANONICAL_METRICS + DERIVED_METRICS + VALUATION_METRICS)
        latest_values = selected_buckets[-1].values if selected_buckets else {}
        available = {metric for metric in expected if latest_values.get(metric) and latest_values[metric].value is not None}
        missing = sorted(expected - available)
        if missing:
            global_warnings.append("missing_metric")
        if period_type == "ttm" and not ttm:
            global_warnings.append("incomplete_ttm")
        periods = [
            {
                "period_start": bucket.start,
                "period_end": bucket.end,
                "period_type": bucket.period_type,
                "fiscal_year": bucket.fiscal_year or (
                    self._effective_fiscal_year(bucket.representative)
                    if bucket.representative else None
                ),
                "fiscal_period": bucket.fiscal_period or (
                    bucket.representative.fiscal_period if bucket.representative else None
                ),
                "frame": bucket.frame or (
                    bucket.representative.frame if bucket.representative else None
                ),
            }
            for bucket in selected_buckets
        ]
        return {
            "symbol": asset.symbol,
            "provider": "sec_edgar",
            "period_type": period_type,
            "as_of": effective_as_of,
            "periods": periods,
            "metrics": dict(metrics),
            "market_price": market_price,
            "warnings": list(dict.fromkeys(global_warnings)),
            "completeness": {
                "status": "insufficient_data" if not selected_buckets else (
                    "complete" if not missing else "partial"
                ),
                "available_metrics": len(available),
                "expected_metrics": len(expected),
                "ratio": Decimal(len(available)) / Decimal(len(expected)),
                "missing_metrics": missing,
            },
        }
