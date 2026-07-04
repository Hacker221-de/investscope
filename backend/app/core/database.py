from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import TypedDict

from alembic.migration import MigrationContext
from sqlalchemy import DateTime, MetaData, Numeric, String, create_engine, event
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import Settings, get_settings
from app.core.paths import DesktopPaths, get_desktop_paths
from app.core.time import ensure_utc, utc_now

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime persisted as a UTC instant."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        return ensure_utc(value) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return ensure_utc(value) if value.tzinfo is not None else value.replace(tzinfo=UTC)


class ExactNumeric(TypeDecorator[Decimal]):
    """Store exact fixed-scale decimals on PostgreSQL and SQLite.

    PostgreSQL retains NUMERIC(precision, scale). SQLite's NUMERIC affinity can
    silently round large fractional values through binary floating point, so a
    sortable fixed-width text encoding is used for that dialect instead.
    Negative zero is canonicalized to positive zero on storage.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int, scale: int) -> None:
        if precision <= 0 or scale < 0 or scale > precision:
            raise ValueError("Invalid decimal precision or scale")
        self.precision = precision
        self.scale = scale
        self._limit = 10**precision
        self._quantum = Decimal(1).scaleb(-scale)
        super().__init__()

    def load_dialect_impl(self, dialect: object):  # type: ignore[no-untyped-def]
        if getattr(dialect, "name", None) == "sqlite":
            return dialect.type_descriptor(String(self.precision + 1))  # type: ignore[attr-defined]
        return dialect.type_descriptor(  # type: ignore[attr-defined]
            Numeric(self.precision, self.scale, asdecimal=True)
        )

    def _normalize(self, value: Decimal | int | str) -> Decimal:
        if isinstance(value, float):
            raise TypeError("ExactNumeric does not accept float values")
        try:
            decimal_value = value if isinstance(value, Decimal) else Decimal(value)
            with localcontext() as context:
                context.prec = max(self.precision + self.scale + 4, 50)
                normalized = decimal_value.quantize(self._quantum)
        except (InvalidOperation, ValueError) as error:
            raise ValueError("Invalid decimal value") from error
        if not normalized.is_finite():
            raise ValueError("Decimal value must be finite")
        if decimal_value != normalized:
            raise ValueError(
                f"Decimal value has more than {self.scale} fractional digits"
            )
        scaled = int(normalized.scaleb(self.scale))
        if abs(scaled) >= self._limit:
            raise ValueError(
                f"Decimal value exceeds precision {self.precision} and scale {self.scale}"
            )
        return normalized

    def _encode_sqlite(self, value: Decimal) -> str:
        scaled = int(value.scaleb(self.scale))
        if scaled < 0:
            return f"0{self._limit - 1 - abs(scaled):0{self.precision}d}"
        return f"1{scaled:0{self.precision}d}"

    def _decode_sqlite(self, value: object) -> Decimal:
        encoded = str(value)
        if (
            len(encoded) == self.precision + 1
            and encoded[0] in {"0", "1"}
            and encoded[1:].isdigit()
        ):
            stored = int(encoded[1:])
            scaled = stored if encoded[0] == "1" else -(self._limit - 1 - stored)
            return Decimal(scaled).scaleb(-self.scale)
        raise ValueError("Malformed ExactNumeric database value")

    def process_bind_param(self, value: object | None, dialect: object) -> object | None:
        if value is None:
            return None
        normalized = self._normalize(value)  # type: ignore[arg-type]
        if getattr(dialect, "name", None) == "sqlite":
            return self._encode_sqlite(normalized)
        return normalized

    def process_result_value(self, value: object | None, dialect: object) -> Decimal | None:
        if value is None:
            return None
        if getattr(dialect, "name", None) == "sqlite":
            return self._decode_sqlite(value)
        return self._normalize(value)  # type: ignore[arg-type]


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def sqlite_database_url(database_path: str | Path) -> URL:
    return URL.create(
        drivername="sqlite+pysqlite",
        database=str(Path(database_path).expanduser().resolve()),
    )


def get_database_url(
    settings: Settings | None = None,
    *,
    desktop_paths: DesktopPaths | None = None,
) -> URL:
    resolved_settings = settings or get_settings()
    if resolved_settings.mode == "desktop":
        paths = desktop_paths or get_desktop_paths(resolved_settings.data_dir)
        return sqlite_database_url(paths.database_path)
    return make_url(resolved_settings.database_url)


def _set_sqlite_pragmas(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def configure_sqlite_engine(engine: Engine) -> None:
    if engine.dialect.name == "sqlite" and not event.contains(
        engine, "connect", _set_sqlite_pragmas
    ):
        event.listen(engine, "connect", _set_sqlite_pragmas)


def build_engine(
    database_url: str | URL | None = None,
    *,
    settings: Settings | None = None,
) -> Engine:
    url = make_url(database_url) if database_url is not None else get_database_url(settings)
    options: dict[str, object] = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 10}
    database_engine = create_engine(url, **options)
    configure_sqlite_engine(database_engine)
    return database_engine


class DatabaseDiagnostics(TypedDict):
    mode: str
    dialect: str
    alembic_revision: str | None


def get_database_diagnostics(
    database_engine: Engine,
    *,
    mode: str,
) -> DatabaseDiagnostics:
    with database_engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    return DatabaseDiagnostics(
        mode=mode,
        dialect=database_engine.dialect.name,
        alembic_revision=revision,
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
