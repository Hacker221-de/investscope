from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
from threading import Event

from alembic import command
import pytest

from app.core.config import Settings
from app.core.database import build_engine, get_database_diagnostics, sqlite_database_url
from app.desktop import bootstrap as bootstrap_module
from app.desktop.bootstrap import (
    DesktopBootstrapBusyError,
    DesktopBootstrapError,
    bootstrap_desktop,
)


def desktop_settings(data_dir: Path) -> Settings:
    return Settings(mode="desktop", data_dir=data_dir, _env_file=None)


def test_first_bootstrap_creates_directories_and_migrated_database(tmp_path: Path) -> None:
    result = bootstrap_desktop(desktop_settings(tmp_path / "InvestScope"))

    assert result.database_created is True
    assert result.mode == "desktop"
    assert result.database_dialect == "sqlite"
    assert result.alembic_revision == "0008"
    assert result.paths.database_path.is_file()
    assert result.paths.logs_dir.is_dir()
    assert result.paths.imports_dir.is_dir()
    assert result.paths.backups_dir.is_dir()

    engine = build_engine(sqlite_database_url(result.paths.database_path))
    try:
        diagnostics = get_database_diagnostics(engine, mode="desktop")
    finally:
        engine.dispose()
    assert diagnostics == {
        "mode": "desktop",
        "dialect": "sqlite",
        "alembic_revision": "0008",
    }
    assert str(result.paths.root_dir) not in str(diagnostics)


def test_second_bootstrap_is_idempotent_and_preserves_existing_data(tmp_path: Path) -> None:
    settings = desktop_settings(tmp_path / "InvestScope")
    first = bootstrap_desktop(settings)
    with closing(sqlite3.connect(first.paths.database_path)) as connection:
        connection.execute("CREATE TABLE desktop_bootstrap_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO desktop_bootstrap_marker VALUES ('preserved')")
        connection.commit()

    second = bootstrap_desktop(settings)

    assert second.database_created is False
    assert second.alembic_revision == "0008"
    with closing(sqlite3.connect(second.paths.database_path)) as connection:
        assert connection.execute(
            "SELECT value FROM desktop_bootstrap_marker"
        ).fetchone() == ("preserved",)


def test_failed_initial_migration_does_not_create_or_replace_main_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = desktop_settings(tmp_path / "InvestScope")

    def migration_failure(_database_path: Path) -> str:
        raise RuntimeError("migration failed")

    monkeypatch.setattr(bootstrap_module, "_upgrade_database", migration_failure)

    with pytest.raises(DesktopBootstrapError, match="initialization failed"):
        bootstrap_desktop(settings)

    assert not (tmp_path / "InvestScope" / "investscope.db").exists()
    assert list((tmp_path / "InvestScope").glob(".investscope-*.tmp")) == []


def test_existing_database_on_old_revision_is_upgraded_and_preserved(tmp_path: Path) -> None:
    settings = desktop_settings(tmp_path / "InvestScope")
    paths = bootstrap_module.get_desktop_paths(settings.data_dir)
    bootstrap_module.create_desktop_directories(paths)
    command.upgrade(bootstrap_module._alembic_config(paths.database_path), "0003")
    requested_at = "2026-07-04 12:00:00"
    with closing(sqlite3.connect(paths.database_path)) as connection:
        connection.execute(
            "INSERT INTO provider_request_logs "
            "(provider, endpoint, symbol, requested_at, status_code, successful, "
            "error_type, request_group_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "alpha_vantage", "GLOBAL_QUOTE", "AAPL", requested_at,
                200, 1, None, "old-revision-group",
            ),
        )
        connection.commit()

    result = bootstrap_desktop(settings)

    assert result.database_created is False
    assert result.alembic_revision == "0008"
    with closing(sqlite3.connect(paths.database_path)) as connection:
        row = connection.execute(
            "SELECT requested_at, started_at, completed_at FROM provider_request_logs"
        ).fetchone()
    assert row == (requested_at, requested_at, requested_at)


def test_failed_existing_database_migration_does_not_replace_main_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = desktop_settings(tmp_path / "InvestScope")
    first = bootstrap_desktop(settings)
    with closing(sqlite3.connect(first.paths.database_path)) as connection:
        connection.execute("CREATE TABLE preserved_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO preserved_marker VALUES ('original')")
        connection.commit()

    def migration_failure(_database_path: Path) -> str:
        raise RuntimeError("migration failed")

    monkeypatch.setattr(bootstrap_module, "_upgrade_database", migration_failure)
    with pytest.raises(DesktopBootstrapError, match="initialization failed"):
        bootstrap_desktop(settings)

    with closing(sqlite3.connect(first.paths.database_path)) as connection:
        assert connection.execute("SELECT value FROM preserved_marker").fetchone() == (
            "original",
        )
    assert list(first.paths.root_dir.glob(".investscope-*.tmp")) == []


def test_parallel_bootstrap_returns_controlled_busy_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = desktop_settings(tmp_path / "InvestScope")
    migration_started = Event()
    allow_migration = Event()
    original_upgrade = bootstrap_module._upgrade_database

    def held_upgrade(database_path: Path) -> str | None:
        migration_started.set()
        if not allow_migration.wait(timeout=10):
            raise RuntimeError("test timed out waiting to release migration")
        return original_upgrade(database_path)

    monkeypatch.setattr(bootstrap_module, "_upgrade_database", held_upgrade)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_bootstrap = executor.submit(bootstrap_desktop, settings)
        assert migration_started.wait(timeout=10)
        with pytest.raises(DesktopBootstrapBusyError, match="already running"):
            bootstrap_desktop(settings)
        allow_migration.set()
        result = first_bootstrap.result(timeout=20)

    assert result.database_created is True
    assert result.alembic_revision == "0008"


def test_bootstrap_rejects_server_mode(tmp_path: Path) -> None:
    settings = Settings(mode="server", data_dir=tmp_path, _env_file=None)
    with pytest.raises(DesktopBootstrapError, match="MODE=desktop"):
        bootstrap_desktop(settings)
