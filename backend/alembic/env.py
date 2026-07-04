from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.database import Base, configure_sqlite_engine, get_database_url
from app import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

configured_url = config.attributes.get("database_url") or get_database_url(get_settings())
url = make_url(configured_url)
config.set_main_option(
    "sqlalchemy.url",
    url.render_as_string(hide_password=False).replace("%", "%%"),
)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=url.get_backend_name() == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    is_sqlite = connection.dialect.name == "sqlite"
    migration_succeeded = False
    if is_sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()
        migration_succeeded = True
    finally:
        if is_sqlite:
            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    if is_sqlite and migration_succeeded:
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        if violations:
            raise RuntimeError("SQLite foreign key check failed after migrations")


def run_migrations_online() -> None:
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_migrations(supplied_connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    configure_sqlite_engine(connectable)
    with connectable.connect() as connection:
        _run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
