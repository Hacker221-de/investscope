from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import tempfile

from alembic import command
from alembic.config import Config

from app.core.config import Settings, get_settings
from app.core.database import build_engine, get_database_diagnostics, sqlite_database_url
from app.core.paths import DesktopPaths, create_desktop_directories, get_desktop_paths

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class DesktopBootstrapError(RuntimeError):
    """Raised when the local desktop database cannot be initialized safely."""


class DesktopBootstrapBusyError(DesktopBootstrapError):
    """Raised when another process is already initializing the desktop database."""


@dataclass(frozen=True, slots=True)
class DesktopBootstrapResult:
    paths: DesktopPaths
    database_created: bool
    mode: str
    database_dialect: str
    alembic_revision: str | None


def _alembic_config(database_path: Path) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.attributes["database_url"] = sqlite_database_url(database_path)
    return config


def _upgrade_database(database_path: Path) -> str | None:
    database_url = sqlite_database_url(database_path)
    engine = build_engine(database_url)
    config = _alembic_config(database_path)
    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            try:
                command.upgrade(config, "head")
            finally:
                config.attributes.pop("connection", None)
        with engine.connect() as connection:
            check_query = connection.exec_driver_sql("PRAGMA quick_check")
            check_result = check_query.scalar_one()
            check_query.close()
            if check_result != "ok":
                raise DesktopBootstrapError("SQLite integrity check failed after migrations")
            checkpoint_query = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            checkpoint_query.all()
            checkpoint_query.close()
        return get_database_diagnostics(engine, mode="desktop")["alembic_revision"]
    finally:
        engine.dispose()


def _copy_existing_database(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source)) as source_connection:
        checkpoint = source_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is not None and checkpoint[0] != 0:
            raise DesktopBootstrapError("Desktop database is busy")
        with closing(sqlite3.connect(destination)) as destination_connection:
            source_connection.backup(destination_connection)


def _remove_database_files(database_path: Path) -> None:
    for path in (
        database_path,
        Path(f"{database_path}-wal"),
        Path(f"{database_path}-shm"),
    ):
        path.unlink(missing_ok=True)


@contextmanager
def _desktop_bootstrap_lock(lock_path: Path) -> Iterator[None]:
    lock_file = lock_path.open("a+b")
    try:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DesktopBootstrapBusyError("Desktop bootstrap is already running") from error

        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    finally:
        lock_file.close()


def bootstrap_desktop(settings: Settings | None = None) -> DesktopBootstrapResult:
    """Create directories and atomically migrate the local SQLite database."""
    resolved_settings = settings or get_settings()
    if resolved_settings.mode != "desktop":
        raise DesktopBootstrapError("Desktop bootstrap requires INVESTSCOPE_MODE=desktop")

    paths = get_desktop_paths(resolved_settings.data_dir)
    create_desktop_directories(paths)
    with _desktop_bootstrap_lock(paths.root_dir / ".bootstrap.lock"):
        database_created = not paths.database_path.exists()

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".investscope-",
            suffix=".db.tmp",
            dir=paths.root_dir,
        )
        os.close(descriptor)
        temporary_database = Path(temporary_name)

        try:
            if not database_created:
                _copy_existing_database(paths.database_path, temporary_database)
            revision = _upgrade_database(temporary_database)
            os.replace(temporary_database, paths.database_path)
        except Exception as error:
            _remove_database_files(temporary_database)
            if isinstance(error, DesktopBootstrapError):
                raise
            raise DesktopBootstrapError("Desktop database initialization failed") from error
        finally:
            _remove_database_files(temporary_database)

    return DesktopBootstrapResult(
        paths=paths,
        database_created=database_created,
        mode="desktop",
        database_dialect="sqlite",
        alembic_revision=revision,
    )
