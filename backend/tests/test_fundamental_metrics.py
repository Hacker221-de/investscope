from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import count
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.main import app
from app.models import Asset, CompanyFiling, FinancialFact, MarketBar
from app.modules.fundamental_analysis.metrics import FundamentalMetricsService, MetricValue

IDENTITIES = count(1)


def seed_asset(session: Session) -> Asset:
    asset = Asset(
        symbol="AAPL",
        name="Apple Inc.",
        asset_type="Equity",
        exchange="Nasdaq",
        currency="USD",
        sector="Technology",
        industry="Consumer Electronics",
        provider_symbol="AAPL",
        is_active=True,
    )
    session.add(asset)
    session.flush()
    return asset


def add_filing(
    session: Session,
    asset: Asset,
    *,
    accession: str,
    form: str,
    accepted: datetime,
) -> CompanyFiling:
    filing = CompanyFiling(
        asset_id=asset.id,
        provider="sec_edgar",
        accession_number=accession,
        form=form,
        filing_date=accepted.date(),
        report_date=None,
        acceptance_datetime=accepted,
        primary_document="report.htm",
        primary_doc_description=None,
        file_number=None,
        film_number=None,
        items=None,
        is_inline_xbrl=True,
        is_xbrl=True,
        is_amendment=form.endswith("/A"),
        amended_form=form[:-2] if form.endswith("/A") else None,
        filing_url=f"https://www.sec.gov/{accession}",
        ingestion_method="manual_json",
        source_filename="submissions.json",
        imported_at=accepted,
        received_at=accepted,
    )
    session.add(filing)
    return filing


def add_fact(
    session: Session,
    asset: Asset,
    *,
    metric: str,
    concept: str,
    value: str,
    unit: str,
    start: date | None,
    end: date,
    period_type: str,
    accession: str,
    filed: datetime,
    form: str = "10-Q",
    fiscal_year: int | None = 2025,
    fiscal_period: str | None = "Q2",
    frame: str | None = "CY2025Q1",
) -> FinancialFact:
    fact = FinancialFact(
        asset_id=asset.id,
        provider="sec_edgar",
        taxonomy="us-gaap",
        concept=concept,
        label=metric,
        description=None,
        normalized_metric=metric,
        unit=unit,
        value=Decimal(value),
        period_start=start,
        period_end=end,
        filed_at=filed,
        frame=frame,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        accession_number=accession,
        is_instant=start is None,
        period_type=period_type,
        ingestion_method="manual_json",
        source_filename="companyfacts.json",
        imported_at=filed,
        received_at=filed,
        fact_identity=f"metric-test-{next(IDENTITIES):040d}",
    )
    session.add(fact)
    return fact


def service(session: Session, provider: str = "alpha_vantage") -> FundamentalMetricsService:
    return FundamentalMetricsService(
        session,
        market_provider=provider,
        market_stale_after_hours=36,
        market_session_close_hour_utc=21,
    )


def build(session: Session, **kwargs):
    session.commit()
    return service(session).build_metrics(
        symbol="AAPL",
        period_type=kwargs.pop("period_type", "quarterly"),
        as_of=kwargs.pop("as_of", datetime(2027, 1, 1, tzinfo=UTC)),
        limit=kwargs.pop("limit", 12),
        offset=kwargs.pop("offset", 0),
        include_alternatives=kwargs.pop("include_alternatives", True),
        annual_fallback=kwargs.pop("annual_fallback", False),
        **kwargs,
    )


def test_same_period_comparative_fact_does_not_create_new_quarter(db_session: Session) -> None:
    asset = seed_asset(db_session)
    original = datetime(2025, 5, 2, 16, tzinfo=UTC)
    comparative = datetime(2026, 5, 1, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=original)
    add_filing(db_session, asset, accession="0000320193-26-000001", form="10-Q", accepted=comparative)
    for accession, filed, fiscal_year in (
        ("0000320193-25-000001", original, 2025),
        ("0000320193-26-000001", comparative, 2026),
    ):
        add_fact(
            db_session, asset, metric="revenue",
            concept="RevenueFromContractWithCustomerExcludingAssessedTax",
            value="95359000000", unit="USD", start=date(2024, 12, 29),
            end=date(2025, 3, 29), period_type="quarterly", accession=accession,
            filed=filed, fiscal_year=fiscal_year, fiscal_period="Q2",
        )

    result = build(db_session)
    points = result["metrics"]["revenue"]
    assert len(result["periods"]) == 1
    assert len(points) == 1
    assert points[0]["value"] == Decimal("95359000000")
    assert points[0]["is_repeated_comparative"] is True
    assert points[0]["is_restated"] is False
    assert points[0]["selected_fact"]["fiscal_year"] == 2025
    assert len(points[0]["alternative_facts"]) == 1


def test_changed_value_is_restatement_and_amendment_is_point_in_time(db_session: Session) -> None:
    asset = seed_asset(db_session)
    original = datetime(2025, 5, 2, 16, tzinfo=UTC)
    amended = datetime(2025, 5, 10, 18, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=original)
    add_filing(db_session, asset, accession="0000320193-25-000002", form="10-Q/A", accepted=amended)
    for accession, filed, value, form in (
        ("0000320193-25-000001", original, "100", "10-Q"),
        ("0000320193-25-000002", amended, "90", "10-Q/A"),
    ):
        add_fact(
            db_session, asset, metric="revenue", concept="Revenues", value=value,
            unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
            period_type="quarterly", accession=accession, filed=filed, form=form,
        )

    before = build(db_session, as_of=datetime(2025, 5, 5, tzinfo=UTC))
    after = build(db_session, as_of=datetime(2025, 5, 11, tzinfo=UTC))
    assert before["metrics"]["revenue"][0]["value"] == Decimal("100")
    point = after["metrics"]["revenue"][0]
    assert point["value"] == Decimal("90")
    assert point["is_restated"] is True
    assert point["selection_reason"] == "amended_filing"
    assert point["selected_fact"]["form"] == "10-Q/A"


def test_concept_priority_and_conflict_are_exposed(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    for concept, value in (("Revenues", "101"), (
        "RevenueFromContractWithCustomerExcludingAssessedTax", "100"
    )):
        add_fact(
            db_session, asset, metric="revenue", concept=concept, value=value,
            unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
            period_type="quarterly", accession="0000320193-25-000001", filed=accepted,
        )
    point = build(db_session)["metrics"]["revenue"][0]
    assert point["value"] == Decimal("100")
    assert point["selected_fact"]["concept"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert point["selection_reason"] == "concept_priority"
    assert point["has_conflict"] is True
    assert "conflicting_facts" in point["warnings"]


def test_calendar_frame_and_fiscal_period_remain_separate(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="100",
        unit="USD", start=date(2024, 12, 29), end=date(2025, 3, 29),
        period_type="quarterly", accession="0000320193-25-000001", filed=accepted,
        fiscal_year=2025, fiscal_period="Q2", frame="CY2025Q1",
    )
    point = build(db_session)["metrics"]["revenue"][0]
    assert point["fiscal_period"] == "Q2"
    assert point["frame"] == "CY2025Q1"
    assert point["period_start"] == date(2024, 12, 29)


def add_quarters(session: Session, asset: Asset, values: list[str]) -> None:
    ranges = (
        (date(2024, 1, 1), date(2024, 3, 31)),
        (date(2024, 4, 1), date(2024, 6, 30)),
        (date(2024, 7, 1), date(2024, 9, 30)),
        (date(2024, 10, 1), date(2024, 12, 31)),
    )
    for index, ((start, end), value) in enumerate(zip(ranges, values), 1):
        accepted = datetime(2024, index * 2 + 3, 1, 16, tzinfo=UTC)
        accession = f"0000320193-24-{index:06d}"
        add_filing(session, asset, accession=accession, form="10-Q", accepted=accepted)
        add_fact(
            session, asset, metric="revenue", concept="Revenues", value=value,
            unit="USD", start=start, end=end, period_type="quarterly",
            accession=accession, filed=accepted, fiscal_year=2024,
            fiscal_period=f"Q{index}", frame=f"CY2024Q{index}",
        )


def test_ttm_uses_exactly_four_non_overlapping_quarters(db_session: Session) -> None:
    asset = seed_asset(db_session)
    add_quarters(db_session, asset, ["10", "20", "30", "40"])
    result = build(db_session, period_type="ttm")
    assert len(result["periods"]) == 1
    assert result["metrics"]["revenue"][0]["value"] == Decimal("100")
    assert len(result["metrics"]["revenue"][0]["source_facts"]) == 4
    point = result["metrics"]["revenue"][0]
    assert point["is_repeated_comparative"] is False
    assert "repeated_comparative" not in point["warnings"]
    assert len(point["calculation_components"]) == 4
    assert all(component["metric"] == "revenue" for component in point["calculation_components"])
    assert all(component["ingestion_method"] == "manual_json" for component in point["calculation_components"])
    assert all(component["source_filename"] == "companyfacts.json" for component in point["calculation_components"])
    repeated_build = build(db_session, period_type="ttm")
    assert [
        component["identity"] for component in point["calculation_components"]
    ] == [
        component["identity"]
        for component in repeated_build["metrics"]["revenue"][0]["calculation_components"]
    ]


def test_ttm_does_not_count_repeated_comparative_as_fifth_quarter(db_session: Session) -> None:
    asset = seed_asset(db_session)
    add_quarters(db_session, asset, ["10", "20", "30", "40"])
    later = datetime(2025, 5, 1, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000099", form="10-Q", accepted=later)
    add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="10",
        unit="USD", start=date(2024, 1, 1), end=date(2024, 3, 31),
        period_type="quarterly", accession="0000320193-25-000099", filed=later,
        fiscal_year=2025, fiscal_period="Q2", frame="CY2024Q1",
    )
    result = build(db_session, period_type="ttm")
    assert len(result["periods"]) == 1
    assert result["metrics"]["revenue"][0]["value"] == Decimal("100")
    point = result["metrics"]["revenue"][0]
    assert len(point["source_facts"]) == 5
    assert len(point["calculation_components"]) == 4
    assert point["is_repeated_comparative"] is True
    assert "repeated_comparative" in point["warnings"]
    assert all(
        component["is_repeated_comparative"] is False
        for component in point["calculation_components"]
    )
    assert "0000320193-25-000099" not in {
        component["accession_number"]
        for component in point["calculation_components"]
    }


def test_ttm_reports_insufficient_data_for_three_quarters(db_session: Session) -> None:
    asset = seed_asset(db_session)
    add_quarters(db_session, asset, ["10", "20", "30", "40"])
    # Make the fourth period YTD so it cannot be used as a quarter.
    latest = max(asset.financial_facts, key=lambda fact: fact.period_end)
    latest.period_type = "ytd"
    result = build(db_session, period_type="ttm")
    assert result["completeness"]["status"] == "insufficient_data"
    assert "incomplete_ttm" in result["warnings"]


def test_ttm_annual_fallback_requires_explicit_flag(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 2, 1, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-K", accepted=accepted)
    add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="400",
        unit="USD", start=date(2024, 1, 1), end=date(2024, 12, 31),
        period_type="annual", accession="0000320193-25-000001", filed=accepted,
        form="10-K", fiscal_year=2024, fiscal_period="FY", frame="CY2024",
    )
    without_fallback = build(db_session, period_type="ttm")
    with_fallback = build(db_session, period_type="ttm", annual_fallback=True)
    assert without_fallback["completeness"]["status"] == "insufficient_data"
    assert with_fallback["metrics"]["revenue"][0]["value"] == Decimal("400")
    assert "annual_fallback" in with_fallback["metrics"]["revenue"][0]["warnings"]


def test_quarterly_ytd_and_annual_facts_are_not_mixed(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 11, 1, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    for start, end, value, period_type in (
        (date(2025, 7, 1), date(2025, 9, 30), "30", "quarterly"),
        (date(2025, 1, 1), date(2025, 9, 30), "90", "ytd"),
        (date(2025, 1, 1), date(2025, 12, 31), "120", "annual"),
    ):
        add_fact(
            db_session, asset, metric="revenue", concept="Revenues", value=value,
            unit="USD", start=start, end=end, period_type=period_type,
            accession="0000320193-25-000001", filed=accepted,
            form="10-K" if period_type == "annual" else "10-Q",
        )
    quarterly = build(db_session, period_type="quarterly")
    annual = build(db_session, period_type="annual")
    assert [point["value"] for point in quarterly["metrics"]["revenue"]] == [Decimal("30")]
    assert [point["value"] for point in annual["metrics"]["revenue"]] == [Decimal("120")]


def test_fcf_uses_capex_concept_as_cash_outflow(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    for metric, concept, value in (
        ("operating_cash_flow", "NetCashProvidedByUsedInOperatingActivities", "100"),
        ("capital_expenditures", "PaymentsToAcquirePropertyPlantAndEquipment", "30"),
    ):
        add_fact(
            db_session, asset, metric=metric, concept=concept, value=value,
            unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
            period_type="quarterly", accession="0000320193-25-000001", filed=accepted,
        )
    point = build(db_session)["metrics"]["free_cash_flow"][0]
    assert point["value"] == Decimal("70")
    assert len(point["source_facts"]) == 2


def test_zero_denominator_returns_null_and_warning(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    for metric, concept, value in (
        ("revenue", "Revenues", "0"),
        ("net_income", "NetIncomeLoss", "5"),
    ):
        add_fact(
            db_session, asset, metric=metric, concept=concept, value=value,
            unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
            period_type="quarterly", accession="0000320193-25-000001", filed=accepted,
        )
    point = build(db_session)["metrics"]["net_margin"][0]
    assert point["value"] is None
    assert "zero_denominator" in point["warnings"]


def test_point_in_time_valuation_uses_only_price_available_by_as_of(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="100",
        unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
        period_type="quarterly", accession="0000320193-25-000001", filed=accepted,
    )
    add_fact(
        db_session, asset, metric="shares_outstanding",
        concept="EntityCommonStockSharesOutstanding", value="10", unit="shares",
        start=None, end=date(2025, 4, 25), period_type="instant",
        accession="0000320193-25-000001", filed=accepted,
    )
    for day, received, close in (
        (date(2025, 5, 5), datetime(2025, 5, 5, 22, tzinfo=UTC), "20"),
        (date(2025, 5, 6), datetime(2025, 5, 6, 22, tzinfo=UTC), "30"),
    ):
        db_session.add(MarketBar(
            asset_id=asset.id, timeframe="1d",
            event_time=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
            open=None, high=None, low=None, close=Decimal(close), adjusted_close=None,
            volume=None, provider="alpha_vantage", published_at=None,
            received_at=received,
        ))
    result = build(db_session, as_of=datetime(2025, 5, 6, 12, tzinfo=UTC))
    assert result["market_price"]["value"] == Decimal("20")
    assert result["metrics"]["market_cap"][0]["value"] == Decimal("200")


def test_pe_is_null_for_negative_ttm_net_income(db_session: Session) -> None:
    asset = seed_asset(db_session)
    add_quarters(db_session, asset, ["100", "100", "100", "100"])
    ranges = (
        (date(2024, 1, 1), date(2024, 3, 31)),
        (date(2024, 4, 1), date(2024, 6, 30)),
        (date(2024, 7, 1), date(2024, 9, 30)),
        (date(2024, 10, 1), date(2024, 12, 31)),
    )
    for index, (start, end) in enumerate(ranges, 1):
        filed = datetime(2024, index * 2 + 3, 1, 16, tzinfo=UTC)
        add_fact(
            db_session, asset, metric="net_income", concept="NetIncomeLoss", value="-5",
            unit="USD", start=start, end=end, period_type="quarterly",
            accession=f"0000320193-24-{index:06d}", filed=filed,
            fiscal_year=2024, fiscal_period=f"Q{index}", frame=f"CY2024Q{index}",
        )
    add_fact(
        db_session, asset, metric="shares_outstanding",
        concept="EntityCommonStockSharesOutstanding", value="10", unit="shares",
        start=None, end=date(2024, 12, 31), period_type="instant",
        accession="0000320193-24-000004", filed=datetime(2024, 11, 1, 16, tzinfo=UTC),
    )
    db_session.add(MarketBar(
        asset_id=asset.id, timeframe="1d",
        event_time=datetime(2024, 12, 31, tzinfo=UTC),
        open=None, high=None, low=None, close=Decimal("20"), adjusted_close=None,
        volume=None, provider="alpha_vantage", published_at=None,
        received_at=datetime(2025, 1, 1, 1, tzinfo=UTC),
    ))
    result = build(
        db_session,
        period_type="ttm",
        as_of=datetime(2025, 1, 2, tzinfo=UTC),
    )
    point = result["metrics"]["price_to_earnings"][0]
    assert point["value"] is None
    assert "negative_net_income" in point["warnings"]


def test_metrics_api_exposes_canonical_provenance(market_client: TestClient, db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="0000320193-25-000001", form="10-Q", accepted=accepted)
    add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="100",
        unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
        period_type="quarterly", accession="0000320193-25-000001", filed=accepted,
    )
    db_session.commit()
    app.dependency_overrides[get_settings] = lambda: Settings(
        market_data_provider="alpha_vantage"
    )
    try:
        response = market_client.get(
            "/api/fundamentals/AAPL/metrics",
            params={"period_type": "quarterly", "include_alternatives": "true"},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["provider"] == "sec_edgar"
    assert payload["metrics"]["revenue"][0]["selected_fact"]["concept"] == "Revenues"


def seed_duration_fiscal_year(
    session: Session,
    asset: Asset,
    *,
    metric: str,
    concept: str,
    values: tuple[str, str, str, str],
    units: tuple[str, str, str, str] = ("USD", "USD", "USD", "USD"),
) -> list[datetime]:
    ranges = (
        (date(2024, 1, 1), date(2024, 3, 31), "Q1", "10-Q"),
        (date(2024, 4, 1), date(2024, 6, 30), "Q2", "10-Q"),
        (date(2024, 7, 1), date(2024, 9, 30), "Q3", "10-Q"),
        (date(2024, 1, 1), date(2024, 12, 31), "FY", "10-K"),
    )
    accepted_dates: list[datetime] = []
    for index, ((start, end, fiscal_period, form), value, unit) in enumerate(
        zip(ranges, values, units), 1
    ):
        accepted = datetime(2024, (3, 6, 10, 12)[index - 1], 15, 16, tzinfo=UTC)
        accession = f"0000320193-24-9{index:05d}"
        add_filing(session, asset, accession=accession, form=form, accepted=accepted)
        add_fact(
            session,
            asset,
            metric=metric,
            concept=concept,
            value=value,
            unit=unit,
            start=start,
            end=end,
            period_type="annual" if fiscal_period == "FY" else "quarterly",
            accession=accession,
            filed=accepted,
            form=form,
            fiscal_year=2024,
            fiscal_period=fiscal_period,
            frame="CY2024" if fiscal_period == "FY" else f"CY2024{fiscal_period}",
        )
        accepted_dates.append(accepted)
    return accepted_dates


def point_for(result: dict, metric: str, fiscal_period: str) -> dict:
    return next(
        point
        for point in result["metrics"][metric]
        if point["fiscal_period"] == fiscal_period
    )


def assert_derived_components(point: dict) -> None:
    assert point["status"] == "available"
    assert point["derived"] is True
    components = point["calculation_components"]
    assert components
    identities = [component["identity"] for component in components]
    assert len(identities) == len(set(identities))
    assert {component["id"] for component in components}.issubset(
        {fact["id"] for fact in point["source_facts"]}
    )
    assert all(component["is_repeated_comparative"] is False for component in components)


def test_q4_is_derived_from_annual_and_three_quarters(db_session: Session) -> None:
    asset = seed_asset(db_session)
    seed_duration_fiscal_year(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        values=("10", "20", "30", "100"),
    )

    result = build(db_session, period_type="quarterly")
    q4 = point_for(result, "revenue", "Q4")
    assert q4["value"] == Decimal("40")
    assert q4["selection_reason"] == "derived_quarter"
    assert q4["calculation"] == "annual - q1 - q2 - q3"
    assert q4["derived"] is True
    assert q4["derivation_method"] == "annual_minus_three_quarters"
    assert q4["confidence"] == "high"
    assert len(q4["source_facts"]) == 4
    assert_derived_components(q4)


def test_derived_q4_is_not_available_before_annual_filing(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = seed_duration_fiscal_year(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        values=("10", "20", "30", "100"),
    )

    result = build(
        db_session,
        period_type="quarterly",
        as_of=accepted[-1] - timedelta(days=1),
    )
    assert all(
        point["fiscal_period"] != "Q4"
        for point in result["metrics"]["revenue"]
    )


def seed_cash_flow_ytd(session: Session, asset: Asset, metric: str, values: tuple[str, str, str, str]) -> None:
    concept = (
        "NetCashProvidedByUsedInOperatingActivities"
        if metric == "operating_cash_flow"
        else "PaymentsToAcquirePropertyPlantAndEquipment"
    )
    definitions = (
        (date(2024, 1, 1), date(2024, 3, 31), "Q1", "quarterly", "10-Q"),
        (date(2024, 1, 1), date(2024, 6, 30), "Q2", "ytd", "10-Q"),
        (date(2024, 1, 1), date(2024, 9, 30), "Q3", "ytd", "10-Q"),
        (date(2024, 1, 1), date(2024, 12, 31), "FY", "annual", "10-K"),
    )
    for index, ((start, end, fiscal_period, period_type, form), value) in enumerate(
        zip(definitions, values), 1
    ):
        accession = f"0000320193-24-{metric[:3]}{index:03d}"
        accepted = datetime(2024, (4, 7, 10, 12)[index - 1], 20, 16, tzinfo=UTC)
        add_filing(session, asset, accession=accession, form=form, accepted=accepted)
        add_fact(
            session,
            asset,
            metric=metric,
            concept=concept,
            value=value,
            unit="USD",
            start=start,
            end=end,
            period_type=period_type,
            accession=accession,
            filed=accepted,
            form=form,
            fiscal_year=2024,
            fiscal_period=fiscal_period,
            frame=None,
        )


def test_cash_flow_quarters_are_derived_from_ytd_and_fcf_is_available(db_session: Session) -> None:
    asset = seed_asset(db_session)
    seed_cash_flow_ytd(db_session, asset, "operating_cash_flow", ("10", "25", "45", "70"))
    seed_cash_flow_ytd(db_session, asset, "capital_expenditures", ("2", "5", "9", "15"))

    quarterly = build(db_session, period_type="quarterly")
    assert point_for(quarterly, "operating_cash_flow", "Q2")["value"] == Decimal("15")
    assert point_for(quarterly, "operating_cash_flow", "Q3")["value"] == Decimal("20")
    assert point_for(quarterly, "operating_cash_flow", "Q4")["value"] == Decimal("25")
    assert point_for(quarterly, "capital_expenditures", "Q2")["value"] == Decimal("3")
    assert point_for(quarterly, "capital_expenditures", "Q3")["value"] == Decimal("4")
    assert point_for(quarterly, "capital_expenditures", "Q4")["value"] == Decimal("6")
    assert point_for(quarterly, "free_cash_flow", "Q2")["value"] == Decimal("12")
    assert point_for(quarterly, "free_cash_flow", "Q3")["value"] == Decimal("16")
    assert point_for(quarterly, "free_cash_flow", "Q4")["value"] == Decimal("19")
    assert point_for(quarterly, "free_cash_flow", "Q4")["selection_reason"] == "derived_quarter"
    assert_derived_components(point_for(quarterly, "operating_cash_flow", "Q2"))
    assert_derived_components(point_for(quarterly, "capital_expenditures", "Q3"))
    assert_derived_components(point_for(quarterly, "free_cash_flow", "Q4"))
    assert point_for(quarterly, "operating_cash_flow", "Q2")["calculation"] == (
        "six_month_ytd - three_month_ytd"
    )
    assert point_for(quarterly, "operating_cash_flow", "Q3")["calculation"] == (
        "nine_month_ytd - six_month_ytd"
    )
    assert point_for(quarterly, "operating_cash_flow", "Q4")["calculation"] == (
        "annual - nine_month_ytd"
    )

    ttm = build(db_session, period_type="ttm")
    assert ttm["metrics"]["operating_cash_flow"][0]["value"] == Decimal("70")
    assert ttm["metrics"]["capital_expenditures"][0]["value"] == Decimal("15")
    assert ttm["metrics"]["free_cash_flow"][0]["value"] == Decimal("55")
    assert "incomplete_ttm" not in ttm["metrics"]["free_cash_flow"][0]["warnings"]


def test_q2_cash_flow_ytd_difference_does_not_require_annual_filing(db_session: Session) -> None:
    asset = seed_asset(db_session)
    concept = "NetCashProvidedByUsedInOperatingActivities"
    q1_filed = datetime(2024, 4, 20, 16, tzinfo=UTC)
    q2_filed = datetime(2024, 7, 20, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="q1", form="10-Q", accepted=q1_filed)
    add_filing(db_session, asset, accession="q2", form="10-Q", accepted=q2_filed)
    add_fact(
        db_session, asset, metric="operating_cash_flow", concept=concept,
        value="10", unit="USD", start=date(2024, 1, 1), end=date(2024, 3, 31),
        period_type="quarterly", accession="q1", filed=q1_filed,
        fiscal_year=2024, fiscal_period="Q1", frame=None,
    )
    add_fact(
        db_session, asset, metric="operating_cash_flow", concept=concept,
        value="25", unit="USD", start=date(2024, 1, 1), end=date(2024, 6, 30),
        period_type="ytd", accession="q2", filed=q2_filed,
        fiscal_year=2024, fiscal_period="Q2", frame=None,
    )
    result = build(db_session, as_of=datetime(2024, 8, 1, tzinfo=UTC))
    q2 = point_for(result, "operating_cash_flow", "Q2")
    assert q2["value"] == Decimal("15")
    assert q2["calculation"] == "six_month_ytd - three_month_ytd"


def test_derived_q4_rejects_unit_mismatch(db_session: Session) -> None:
    asset = seed_asset(db_session)
    seed_duration_fiscal_year(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        values=("10", "20", "30", "100"),
        units=("USD", "USD", "EUR", "USD"),
    )
    result = build(db_session)
    assert all(point["fiscal_period"] != "Q4" for point in result["metrics"]["revenue"])
    assert "derived_quarter_unit_mismatch" in result["warnings"]


def test_derived_q4_rejects_missing_source(db_session: Session) -> None:
    asset = seed_asset(db_session)
    seed_duration_fiscal_year(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        values=("10", "20", "30", "100"),
    )
    q3 = next(fact for fact in asset.financial_facts if fact.fiscal_period == "Q3")
    db_session.delete(q3)
    result = build(db_session)
    assert all(point["fiscal_period"] != "Q4" for point in result["metrics"]["revenue"])
    assert "derived_quarter_missing_source" in result["warnings"]


def test_derived_q4_rejects_unresolved_conflicting_source(db_session: Session) -> None:
    asset = seed_asset(db_session)
    seed_duration_fiscal_year(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        values=("10", "20", "30", "100"),
    )
    q2 = next(fact for fact in asset.financial_facts if fact.fiscal_period == "Q2")
    add_fact(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        value="21",
        unit="USD",
        start=q2.period_start,
        end=q2.period_end,
        period_type="quarterly",
        accession=q2.accession_number,
        filed=q2.filed_at,
        fiscal_year=2024,
        fiscal_period="Q2",
        frame=q2.frame,
    )
    result = build(db_session)
    assert all(point["fiscal_period"] != "Q4" for point in result["metrics"]["revenue"])
    assert "derived_quarter_conflict" in result["warnings"]


def test_total_debt_does_not_double_count_aggregate_and_components(db_session: Session) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 2, 1, 16, tzinfo=UTC)
    accession = "0000320193-25-000777"
    add_filing(db_session, asset, accession=accession, form="10-K", accepted=accepted)
    add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="200",
        unit="USD", start=date(2024, 1, 1), end=date(2024, 12, 31),
        period_type="annual", accession=accession, filed=accepted, form="10-K",
        fiscal_year=2024, fiscal_period="FY", frame="CY2024",
    )
    for metric, concept, value in (
        ("short_term_debt", "CommercialPaper", "10"),
        ("short_term_debt", "LongTermDebtCurrent", "20"),
        ("long_term_debt", "LongTermDebtNoncurrent", "80"),
        ("long_term_debt", "LongTermDebt", "100"),
        ("shareholders_equity", "StockholdersEquity", "50"),
    ):
        add_fact(
            db_session, asset, metric=metric, concept=concept, value=value,
            unit="USD", start=None, end=date(2024, 12, 31),
            period_type="instant", accession=accession, filed=accepted, form="10-K",
            fiscal_year=2024, fiscal_period="FY", frame="CY2024I",
        )
    result = build(db_session, period_type="annual")
    debt = result["metrics"]["total_debt"][0]
    assert debt["value"] == Decimal("110")
    assert {fact["concept"] for fact in debt["source_facts"]} == {
        "LongTermDebt", "LongTermDebtNoncurrent",
        "LongTermDebtCurrent", "CommercialPaper",
    }
    assert result["metrics"]["debt_to_equity"][0]["value"] == Decimal("2.2")
    assert_derived_components(debt)
    assert_derived_components(result["metrics"]["debt_to_equity"][0])


def test_ttm_uses_derived_q4_and_is_unavailable_without_annual(db_session: Session) -> None:
    asset = seed_asset(db_session)
    seed_duration_fiscal_year(
        db_session,
        asset,
        metric="revenue",
        concept="Revenues",
        values=("10", "20", "30", "100"),
    )
    ttm = build(db_session, period_type="ttm")
    assert ttm["metrics"]["revenue"][0]["value"] == Decimal("100")
    assert any(
        fact["form"] == "10-K"
        for fact in ttm["metrics"]["revenue"][0]["source_facts"]
    )

    annual = next(fact for fact in asset.financial_facts if fact.period_type == "annual")
    db_session.delete(annual)
    no_annual = build(db_session, period_type="ttm")
    assert no_annual["periods"] == []
    assert "incomplete_ttm" in no_annual["warnings"]


def test_frontend_exposes_derived_badge_formula_and_filing_sources() -> None:
    frontend = Path(__file__).parents[2] / "frontend"
    analysis = (frontend / "components" / "fundamental-analysis.tsx").read_text(
        encoding="utf-8"
    )
    calculation_components = (
        frontend / "components" / "fundamentals" / "calculation-components.tsx"
    ).read_text(encoding="utf-8")
    metric_provenance = (
        frontend / "components" / "fundamentals" / "metric-provenance.tsx"
    ).read_text(encoding="utf-8")
    formatters = (frontend / "lib" / "fundamental-formatters.ts").read_text(
        encoding="utf-8"
    )
    types = (frontend / "lib" / "types.ts").read_text(encoding="utf-8")

    assert "point.derived &&" in analysis
    assert "quality-badge derived" in analysis
    assert "Расчётное значение" in analysis
    assert "<CalculationComponents point={point}" in analysis
    assert "<MetricProvenance point={point}" in analysis

    assert "annual_minus_three_quarters" in formatters
    assert "point.derivation_method" in calculation_components
    assert "point.calculation" in calculation_components
    assert "point.calculation_components" in calculation_components

    assert "point.source_facts" in metric_provenance
    assert "fact.filing_url" in metric_provenance
    assert "fact.accession_number" in metric_provenance
    assert "source_facts: FundamentalProvenanceFact[]" in types
    assert "calculation_components: FundamentalCalculationComponent[]" in types


def test_ttm_api_exposes_calculation_components_schema(
    market_client: TestClient, db_session: Session
) -> None:
    asset = seed_asset(db_session)
    add_quarters(db_session, asset, ["10", "20", "30", "40"])
    db_session.commit()

    response = market_client.get(
        "/api/fundamentals/AAPL/metrics",
        params={"period_type": "ttm", "limit": 1},
    )

    assert response.status_code == 200
    point = response.json()["metrics"]["revenue"][0]
    assert len(point["calculation_components"]) == 4
    assert set(point["calculation_components"][0]) == {
        "metric", "value", "unit", "start", "end", "fiscal_year",
        "fiscal_period", "form", "accession_number", "filed", "frame",
        "is_amendment", "is_repeated_comparative", "source_filename",
        "ingestion_method", "id", "identity",
    }


def test_available_derived_value_without_components_violates_invariant(
    db_session: Session,
) -> None:
    asset = seed_asset(db_session)
    accepted = datetime(2025, 5, 2, 16, tzinfo=UTC)
    add_filing(db_session, asset, accession="invariant", form="10-Q", accepted=accepted)
    fact = add_fact(
        db_session, asset, metric="revenue", concept="Revenues", value="100",
        unit="USD", start=date(2025, 1, 1), end=date(2025, 3, 31),
        period_type="quarterly", accession="invariant", filed=accepted,
    )
    db_session.flush()
    invalid = MetricValue(
        value=Decimal("10"),
        unit="%",
        source_facts=[fact],
        warnings=[],
        calculation="test",
        derived=True,
        derivation_method="ratio",
    )

    with pytest.raises(ValueError, match="has no calculation components"):
        service(db_session)._assert_derived_value_invariants(invalid)
