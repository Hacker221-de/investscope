import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.database import get_database_url
from app.core.paths import create_desktop_directories, get_desktop_paths


def test_default_mode_is_server_and_invalid_mode_is_rejected() -> None:
    assert Settings(_env_file=None).mode == "server"

    with pytest.raises(ValidationError, match="server.*desktop"):
        Settings(mode="unsupported", _env_file=None)  # type: ignore[arg-type]


def test_desktop_sqlite_url_uses_full_overridden_path(tmp_path: Path) -> None:
    data_dir = tmp_path / "desktop data"
    settings = Settings(mode="desktop", data_dir=data_dir, _env_file=None)

    url = get_database_url(settings)

    assert url.drivername == "sqlite+pysqlite"
    assert Path(url.database or "") == (data_dir / "investscope.db").resolve()
    assert not data_dir.exists()


def test_server_mode_keeps_configured_postgresql_url() -> None:
    configured_url = "postgresql+psycopg://investscope:secret@db:5432/investscope"
    settings = Settings(
        mode="server",
        database_url=configured_url,
        _env_file=None,
    )

    url = get_database_url(settings)

    assert url.drivername == "postgresql+psycopg"
    assert url.host == "db"
    assert url.database == "investscope"


def test_import_and_path_resolution_do_not_create_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "not-created-on-import"
    monkeypatch.setenv("INVESTSCOPE_DATA_DIR", str(data_dir))

    import app.core.paths as paths_module

    importlib.reload(paths_module)
    paths = get_desktop_paths()

    assert paths.root_dir == data_dir.resolve()
    assert not data_dir.exists()

    create_desktop_directories(paths)
    assert paths.root_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.imports_dir.is_dir()
    assert paths.backups_dir.is_dir()
