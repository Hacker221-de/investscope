from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, delete, func, insert, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine
from sqlalchemy.exc import StatementError
from sqlalchemy.schema import CreateTable

from app.core.config import Settings
from app.core.database import ExactNumeric, UTCDateTime, build_engine
from app.core.paths import create_desktop_directories, get_desktop_paths
from app.models import Asset, Portfolio, Position


def desktop_engine(tmp_path: Path) -> Engine:
    settings = Settings(mode="desktop", data_dir=tmp_path, _env_file=None)
    create_desktop_directories(get_desktop_paths(settings.data_dir))
    return build_engine(settings=settings)


def test_sqlite_engine_applies_required_pragmas(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    try:
        with engine.connect() as first_connection, engine.connect() as second_connection:
            for connection in (first_connection, second_connection):
                assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
                assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
                assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 10_000
                assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 1
    finally:
        engine.dispose()


def test_sqlite_foreign_key_cascade_is_enforced(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    try:
        Portfolio.metadata.create_all(engine)
        now = datetime.now(UTC)
        with engine.begin() as connection:
            portfolio_id = connection.execute(
                insert(Portfolio).values(
                    name="Owned assets",
                    base_currency="USD",
                    created_at=now,
                )
            ).inserted_primary_key[0]
            asset_id = connection.execute(
                insert(Asset).values(
                    symbol="AAPL",
                    name="Apple Inc.",
                    asset_type="equity",
                    currency="USD",
                    provider_symbol="AAPL",
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            ).inserted_primary_key[0]
            connection.execute(
                insert(Position).values(
                    portfolio_id=portfolio_id,
                    asset_id=asset_id,
                    symbol="AAPL",
                    quantity=Decimal("2.5"),
                    average_purchase_price=Decimal("123.45"),
                    purchase_date=now.date(),
                    currency="USD",
                    fees=Decimal("1.25"),
                    created_at=now,
                    updated_at=now,
                )
            )
            connection.execute(delete(Portfolio).where(Portfolio.id == portfolio_id))

        with engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(Position)) == 0
    finally:
        engine.dispose()


def test_sqlite_utc_datetime_round_trip(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    metadata = MetaData()
    samples = Table(
        "utc_samples",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("occurred_at", UTCDateTime(), nullable=False),
    )
    metadata.create_all(engine)
    source = datetime(2026, 7, 4, 15, 30, tzinfo=timezone(timedelta(hours=3)))
    try:
        with engine.begin() as connection:
            connection.execute(insert(samples).values(occurred_at=source))
        with engine.connect() as connection:
            restored = connection.scalar(select(samples.c.occurred_at))
        assert restored == source.astimezone(UTC)
        assert restored is not None and restored.tzinfo is UTC
    finally:
        engine.dispose()


def test_sqlite_decimal_round_trip_is_exact(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    metadata = MetaData()
    samples = Table(
        "decimal_samples",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", ExactNumeric(38, 10), nullable=False),
    )
    metadata.create_all(engine)
    expected = [
        Decimal("0"),
        Decimal("0.1"),
        Decimal("-0.1"),
        Decimal("1"),
        Decimal("-1"),
        Decimal("999999999999999.9999999999"),
        Decimal("-999999999999999.9999999999"),
        Decimal("123456789012345.1234567890"),
        Decimal("-123456789012345.1234567890"),
        Decimal("265595000000.0000000000"),
        Decimal("0.0000000001"),
        Decimal("-0.0000000001"),
    ]
    stored = [*expected, Decimal("-0.0000000000")]
    try:
        with engine.begin() as connection:
            connection.execute(insert(samples), [{"value": value} for value in stored])
        with engine.connect() as connection:
            restored = list(connection.scalars(select(samples.c.value).order_by(samples.c.id)))
            storage_classes = list(
                connection.scalars(
                    select(func.typeof(samples.c.value)).order_by(samples.c.id)
                )
            )
        assert all(isinstance(value, Decimal) for value in restored)
        assert restored[:-1] == expected
        assert restored[-1] == Decimal("0")
        assert restored[-1].is_signed() is False
        assert storage_classes == ["text"] * len(stored)
    finally:
        engine.dispose()


def test_exact_numeric_sql_ordering_matches_decimal_ordering(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    metadata = MetaData()
    samples = Table(
        "ordered_decimals",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", ExactNumeric(38, 10), nullable=False),
    )
    metadata.create_all(engine)
    shuffled = [
        Decimal("10"), Decimal("-0.1"), Decimal("100"), Decimal("-100"),
        Decimal("2"), Decimal("-2"), Decimal("0"), Decimal("1"),
        Decimal("-10"), Decimal("0.1"), Decimal("-1"),
    ]
    expected = sorted(shuffled)
    try:
        with engine.begin() as connection:
            connection.execute(insert(samples), [{"value": value} for value in shuffled])
        with engine.connect() as connection:
            ascending = list(connection.scalars(select(samples.c.value).order_by(samples.c.value)))
            descending = list(
                connection.scalars(select(samples.c.value).order_by(samples.c.value.desc()))
            )
        assert ascending == expected
        assert descending == list(reversed(expected))
    finally:
        engine.dispose()


def test_exact_numeric_sql_comparisons_use_decimal_semantics(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    metadata = MetaData()
    samples = Table(
        "compared_decimals",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", ExactNumeric(38, 10), nullable=False),
    )
    metadata.create_all(engine)
    values = [
        Decimal("-100"), Decimal("-10"), Decimal("-2"), Decimal("-1"),
        Decimal("-0.1"), Decimal("0"), Decimal("0.1"), Decimal("1"),
        Decimal("2"), Decimal("10"), Decimal("100"),
    ]

    def selected(connection, condition):  # type: ignore[no-untyped-def]
        return list(
            connection.scalars(
                select(samples.c.value).where(condition).order_by(samples.c.value)
            )
        )

    try:
        with engine.begin() as connection:
            connection.execute(insert(samples), [{"value": value} for value in values])
        with engine.connect() as connection:
            assert selected(connection, samples.c.value == Decimal("0.1")) == [Decimal("0.1")]
            assert selected(connection, samples.c.value < Decimal("0")) == values[:5]
            assert selected(connection, samples.c.value <= Decimal("-1")) == values[:4]
            assert selected(connection, samples.c.value > Decimal("1")) == values[-3:]
            assert selected(
                connection,
                samples.c.value.between(Decimal("-2"), Decimal("10")),
            ) == values[2:10]
    finally:
        engine.dispose()


def test_exact_numeric_rejects_unsafe_or_malformed_values(tmp_path: Path) -> None:
    engine = desktop_engine(tmp_path)
    metadata = MetaData()
    samples = Table(
        "validated_decimals",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", ExactNumeric(38, 10), nullable=True),
    )
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.execute(insert(samples).values(value=None))
        with engine.connect() as connection:
            assert connection.scalar(select(samples.c.value)) is None

        for invalid_value, message in (
            (0.1, "does not accept float"),
            (Decimal("1.00000000001"), "more than 10 fractional digits"),
            (Decimal("10000000000000000000000000000.0000000000"), "exceeds precision"),
        ):
            with pytest.raises(StatementError, match=message):
                with engine.begin() as connection:
                    connection.execute(insert(samples).values(value=invalid_value))

        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO validated_decimals (value) VALUES ('not-an-exact-decimal')"
            )
        with engine.connect() as connection:
            with pytest.raises(ValueError, match="Malformed ExactNumeric database value"):
                list(connection.scalars(select(samples.c.value).where(samples.c.id == 2)))
    finally:
        engine.dispose()


def test_exact_numeric_uses_numeric_on_postgresql_and_text_on_sqlite() -> None:
    metadata = MetaData()
    samples = Table(
        "typed_decimals",
        metadata,
        Column("value", ExactNumeric(38, 10), nullable=False),
    )

    postgresql_ddl = str(CreateTable(samples).compile(dialect=postgresql.dialect()))
    sqlite_ddl = str(CreateTable(samples).compile(dialect=sqlite.dialect()))

    assert "NUMERIC(38, 10)" in postgresql_ddl
    assert "VARCHAR(39)" in sqlite_ddl
