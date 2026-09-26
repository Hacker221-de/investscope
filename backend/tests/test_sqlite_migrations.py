from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, inspect, select, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import ExactNumeric, build_engine, sqlite_database_url
from app.models import Asset, MarketBar, Portfolio

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def migration_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["database_url"] = sqlite_database_url(database_path)
    return config


def current_revision(database_path: Path) -> str | None:
    engine = build_engine(sqlite_database_url(database_path))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def test_sqlite_alembic_base_to_head_and_back_to_base(tmp_path: Path) -> None:
    database_path = tmp_path / "migrations.db"
    config = migration_config(database_path)

    command.upgrade(config, "head")
    assert current_revision(database_path) == "0008"
    engine = build_engine(sqlite_database_url(database_path))
    try:
        columns = {
            column["name"]: str(column["type"])
            for column in inspect(engine).get_columns("financial_facts")
        }
        assert columns["value"] == "VARCHAR(39)"
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    assert current_revision(database_path) is None


def test_migration_0002_keeps_each_logical_group_and_rescales_exact_decimals(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deduplication.db"
    config = migration_config(database_path)
    command.upgrade(config, "0001")
    engine = build_engine(sqlite_database_url(database_path))
    event_time = datetime(2026, 1, 2, tzinfo=UTC)
    legacy_metadata = MetaData()
    price_points = Table(
        "price_points",
        legacy_metadata,
        Column("id", Integer, primary_key=True),
        Column("asset_id", Integer, nullable=False),
        Column("timestamp", DateTime(timezone=True), nullable=False),
        Column("close", ExactNumeric(20, 6), nullable=False),
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets "
                    "(id, symbol, name, asset_type, currency, sector, created_at) "
                    "VALUES "
                    "(1, 'AAPL', 'Apple Inc.', 'equity', 'USD', 'Technology', :created_at), "
                    "(2, 'MSFT', 'Microsoft Corp.', 'equity', 'USD', 'Technology', :created_at)"
                ),
                {"created_at": event_time},
            )
            connection.execute(
                price_points.insert(),
                [
                    {"id": 1, "asset_id": 1, "timestamp": event_time, "close": Decimal("10.000001")},
                    {"id": 2, "asset_id": 2, "timestamp": event_time, "close": Decimal("50.000001")},
                    {"id": 3, "asset_id": 1, "timestamp": event_time, "close": Decimal("20.654321")},
                    {"id": 4, "asset_id": 2, "timestamp": event_time, "close": Decimal("-40.123456")},
                ],
            )
    finally:
        engine.dispose()

    command.upgrade(config, "0002")
    engine = build_engine(sqlite_database_url(database_path))
    try:
        with Session(engine) as session:
            rows = list(session.scalars(select(MarketBar).order_by(MarketBar.asset_id)))
            assert [(row.asset_id, row.close, row.provider, row.timeframe) for row in rows] == [
                (1, Decimal("20.65432100"), "legacy", "1d"),
                (2, Decimal("-40.12345600"), "legacy", "1d"),
            ]
            session.add_all([
                MarketBar(
                    asset_id=1,
                    timeframe=timeframe,
                    event_time=event_time,
                    close=close,
                    provider=provider,
                    received_at=event_time,
                    inserted_at=event_time,
                )
                for provider, timeframe, close in (
                    ("demo", "1d", Decimal("21")),
                    ("demo", "1h", Decimal("22")),
                    ("alpha_vantage", "1d", Decimal("23")),
                )
            ])
            session.commit()
            logical_keys = set(session.execute(
                select(
                    MarketBar.asset_id,
                    MarketBar.provider,
                    MarketBar.timeframe,
                    MarketBar.event_time,
                ).where(MarketBar.asset_id == 1)
            ).all())
        assert len(logical_keys) == 4
    finally:
        engine.dispose()

    command.downgrade(config, "0001")
    assert current_revision(database_path) == "0001"


def test_migration_0004_preserves_existing_request_log(tmp_path: Path) -> None:
    database_path = tmp_path / "provider-timing.db"
    config = migration_config(database_path)
    command.upgrade(config, "0003")
    engine = build_engine(sqlite_database_url(database_path))
    requested_values = [
        "2026-07-04 12:00:00",
        "2026-07-04 12:00:01",
        "2026-07-04 12:00:02",
    ]
    try:
        with engine.begin() as connection:
            for index, requested_at in enumerate(requested_values, start=1):
                connection.execute(
                    text(
                        "INSERT INTO provider_request_logs "
                        "(provider, endpoint, symbol, requested_at, status_code, successful, "
                        "error_type, request_group_id) VALUES "
                        "('alpha_vantage', 'GLOBAL_QUOTE', 'AAPL', :requested_at, :status, "
                        ":successful, NULL, :request_group_id)"
                    ),
                    {
                        "requested_at": requested_at,
                        "status": 200 if index < 3 else 429,
                        "successful": index < 3,
                        "request_group_id": f"group-{index}",
                    },
                )
        indexes_before = {index["name"] for index in inspect(engine).get_indexes(
            "provider_request_logs"
        )}
        foreign_keys_before = inspect(engine).get_foreign_keys("provider_request_logs")
    finally:
        engine.dispose()

    command.upgrade(config, "0004")
    engine = build_engine(sqlite_database_url(database_path))
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT requested_at, started_at, completed_at, status_code "
                    "FROM provider_request_logs ORDER BY id"
                )
            ).all()
            columns = {column[1]: column for column in connection.exec_driver_sql(
                "PRAGMA table_info(provider_request_logs)"
            )}
            indexes_after = {index["name"] for index in inspect(connection).get_indexes(
                "provider_request_logs"
            )}
            foreign_keys_after = inspect(connection).get_foreign_keys("provider_request_logs")
        assert len(rows) == 3
        assert all(row.started_at == row.requested_at for row in rows)
        assert all(row.completed_at == row.requested_at for row in rows)
        assert [row.status_code for row in rows] == [200, 200, 429]
        assert columns["started_at"][3] == 1
        assert columns["completed_at"][3] == 1
        assert indexes_after == indexes_before | {"ix_provider_request_logs_started_at"}
        assert foreign_keys_after == foreign_keys_before == []
    finally:
        engine.dispose()

    command.downgrade(config, "0003")
    engine = build_engine(sqlite_database_url(database_path))
    try:
        inspector = inspect(engine)
        assert "started_at" not in {column["name"] for column in inspector.get_columns(
            "provider_request_logs"
        )}
        assert {index["name"] for index in inspector.get_indexes(
            "provider_request_logs"
        )} == indexes_before
        assert inspector.get_foreign_keys("provider_request_logs") == foreign_keys_before
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM provider_request_logs")) == 3
    finally:
        engine.dispose()


@pytest.fixture
def legacy_portfolio_database(tmp_path: Path) -> Iterator[tuple[Path, Config, Engine, Table]]:
    database_path = tmp_path / "legacy-portfolio.db"
    config = migration_config(database_path)
    command.upgrade(config, "0007")
    engine = build_engine(sqlite_database_url(database_path))
    try:
        # Reflection sees VARCHAR on SQLite; supply the real processors for every Decimal field.
        positions = Table(
            "positions",
            MetaData(),
            Column("quantity", ExactNumeric(20, 8), nullable=False),
            Column("average_purchase_price", ExactNumeric(20, 6), nullable=False),
            Column("fees", ExactNumeric(20, 4), nullable=True),
            autoload_with=engine,
        )
        with engine.begin() as connection:
            connection.execute(Portfolio.__table__.insert(), [
                {"id": 1, "name": "Legacy portfolio", "base_currency": "USD"},
                {"id": 2, "name": "Another portfolio", "base_currency": "USD"},
            ])
            connection.execute(Asset.__table__.insert(), {
                "id": 42, "symbol": "AAPL", "name": "Apple Inc.",
                "asset_type": "equity", "currency": "USD", "provider_symbol": "AAPL",
            })
        yield database_path, config, engine, positions
    finally:
        engine.dispose()


def legacy_position(position_id: int, symbol: str, portfolio_id: int = 1) -> dict[str, object]:
    timestamp = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    return {
        "id": position_id,
        "portfolio_id": portfolio_id,
        "symbol": symbol,
        "quantity": Decimal("1.23456789"),
        "average_purchase_price": Decimal("123.456789"),
        "purchase_date": date(2025, 12, 15),
        "currency": "USD",
        "fees": Decimal("0.0123") if position_id % 2 else None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def portfolio_snapshot(engine: Engine) -> dict[str, list[tuple[object, ...]]]:
    with engine.connect() as connection:
        return {
            table: [tuple(row) for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY id"))]
            for table in ("positions", "portfolios", "assets")
        }


@pytest.mark.parametrize("duplicate_symbol", ["AAPL", "aapl"])
def test_migration_0008_rejects_legacy_duplicates_without_mutation(
    legacy_portfolio_database: tuple[Path, Config, Engine, Table],
    duplicate_symbol: str,
) -> None:
    database_path, config, engine, positions = legacy_portfolio_database
    with engine.begin() as connection:
        connection.execute(positions.insert(), [
            legacy_position(1, "AAPL"),
            legacy_position(2, duplicate_symbol),
            legacy_position(3, "UNKNOWN"),
        ])
    before = portfolio_snapshot(engine)
    columns_before = inspect(engine).get_columns("positions")

    with pytest.raises(RuntimeError, match="Cannot migrate duplicate portfolio positions.*deduplicate"):
        command.upgrade(config, "0008")

    assert current_revision(database_path) == "0007"
    assert portfolio_snapshot(engine) == before
    assert [column["name"] for column in inspect(engine).get_columns("positions")] == [
        column["name"] for column in columns_before
    ]


@pytest.mark.parametrize("symbol", ["AAPL", "aapl"])
def test_migration_0008_reuses_existing_asset_case_insensitively(
    legacy_portfolio_database: tuple[Path, Config, Engine, Table],
    symbol: str,
) -> None:
    database_path, config, engine, positions = legacy_portfolio_database
    with engine.begin() as connection:
        connection.execute(positions.insert(), legacy_position(1, symbol))
    before = portfolio_snapshot(engine)

    command.upgrade(config, "0008")

    assert current_revision(database_path) == "0008"
    assert portfolio_snapshot(engine)["assets"] == before["assets"]
    with engine.connect() as connection:
        row = connection.execute(text("SELECT symbol, asset_id FROM positions")).one()
        assert (row.symbol, row.asset_id) == (symbol, 42)
        assert connection.execute(select(positions.c.quantity)).scalar_one() == Decimal("1.23456789")


def test_migration_0008_creates_unknown_asset_and_links_all_positions(
    legacy_portfolio_database: tuple[Path, Config, Engine, Table],
) -> None:
    database_path, config, engine, positions = legacy_portfolio_database
    with engine.begin() as connection:
        connection.execute(positions.insert(), [
            legacy_position(1, "unknown"),
            legacy_position(2, "UNKNOWN", portfolio_id=2),
            legacy_position(3, "AAPL"),
        ])

    command.upgrade(config, "0008")

    assert current_revision(database_path) == "0008"
    with engine.connect() as connection:
        assets = connection.execute(select(Asset.__table__).order_by(Asset.id)).mappings().all()
        assert len(assets) == 2
        unknown = next(asset for asset in assets if asset["symbol"] == "UNKNOWN")
        assert unknown["asset_type"] == "unknown"
        assert unknown["name"] == unknown["provider_symbol"] == "UNKNOWN"
        assert unknown["currency"] == "USD"
        assert unknown["is_active"] is True
        assert connection.execute(text("SELECT asset_id FROM positions ORDER BY id")).scalars().all() == [
            unknown["id"], unknown["id"], 42,
        ]
        assert connection.scalar(text("SELECT COUNT(*) FROM positions WHERE asset_id IS NULL")) == 0
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_migration_0008_enforces_portfolio_asset_uniqueness(
    legacy_portfolio_database: tuple[Path, Config, Engine, Table],
) -> None:
    _, config, engine, positions = legacy_portfolio_database
    with engine.begin() as connection:
        connection.execute(positions.insert(), legacy_position(1, "AAPL"))
    command.upgrade(config, "0008")
    constraints = inspect(engine).get_unique_constraints("positions")
    assert any(constraint["column_names"] == ["portfolio_id", "asset_id"] for constraint in constraints)
    columns = {column["name"]: column for column in inspect(engine).get_columns("positions")}
    assert columns["asset_id"]["nullable"] is False
    positions.append_column(Column("asset_id", Integer, nullable=False))

    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        with engine.begin() as connection:
            connection.execute(positions.insert(), {**legacy_position(2, "aapl"), "asset_id": 42})

    with engine.begin() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM positions")) == 1
        # The same asset in another portfolio is allowed.
        connection.execute(positions.insert(), {
            **legacy_position(3, "AAPL", portfolio_id=2), "asset_id": 42,
        })


def test_migration_0008_downgrade_restores_legacy_positions_without_data_loss(
    legacy_portfolio_database: tuple[Path, Config, Engine, Table],
) -> None:
    database_path, config, engine, positions = legacy_portfolio_database
    with engine.begin() as connection:
        connection.execute(positions.insert(), [legacy_position(1, "aapl"), legacy_position(2, "UNKNOWN")])
    before = portfolio_snapshot(engine)
    columns_before = {column["name"]: (str(column["type"]), column["nullable"])
                      for column in inspect(engine).get_columns("positions")}
    indexes_before = inspect(engine).get_indexes("positions")
    foreign_keys_before = inspect(engine).get_foreign_keys("positions")
    with engine.connect() as connection:
        decoded_before = connection.execute(select(positions).order_by(positions.c.id)).all()

    command.upgrade(config, "0008")
    command.downgrade(config, "0007")

    assert current_revision(database_path) == "0007"
    columns_after = {column["name"]: (str(column["type"]), column["nullable"])
                     for column in inspect(engine).get_columns("positions")}
    assert "asset_id" not in columns_after
    assert columns_after == columns_before
    assert inspect(engine).get_indexes("positions") == indexes_before
    assert inspect(engine).get_foreign_keys("positions") == foreign_keys_before
    assert inspect(engine).get_unique_constraints("positions") == []
    after = portfolio_snapshot(engine)
    assert after["positions"] == before["positions"]
    assert after["portfolios"] == before["portfolios"]
    # 0008 intentionally retains assets created to resolve unknown legacy symbols.
    with engine.connect() as connection:
        assert connection.execute(select(positions).order_by(positions.c.id)).all() == decoded_before
        assert connection.scalar(text("SELECT COUNT(*) FROM assets WHERE symbol = 'UNKNOWN'")) == 1
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    # Downgrade restores the legacy shape, which allows duplicate symbols.
    with engine.begin() as connection:
        connection.execute(positions.insert(), legacy_position(3, "aapl"))


def test_postgresql_offline_ddl_keeps_real_numeric_types() -> None:
    output = io.StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["database_url"] = URL.create(
        "postgresql+psycopg",
        username="investscope",
        password="not-a-real-secret",
        host="localhost",
        database="investscope_test",
    )

    command.upgrade(config, "head", sql=True)
    ddl = output.getvalue()

    assert "NUMERIC(38, 10)" in ddl
    assert "NUMERIC(20, 8)" in ddl
    assert "VARCHAR(39)" not in ddl
