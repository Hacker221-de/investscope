import importlib
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.database import get_database_url
from app.core.paths import create_desktop_directories, get_desktop_paths


@pytest.mark.parametrize("configured_dir", [None, "", "   "], ids=["unset", "empty", "whitespace"])
@pytest.mark.parametrize("has_appdata", [True, False], ids=["appdata", "no-appdata"])
def test_unconfigured_data_dir_uses_platform_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_dir: str | None,
    has_appdata: bool,
) -> None:
    home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    backend_cwd = tmp_path / "backend"
    backend_cwd.mkdir()
    monkeypatch.chdir(backend_cwd)
    environment = {"APPDATA": str(home / "AppData" / "Roaming")} if has_appdata else {}
    if configured_dir is not None:
        environment["INVESTSCOPE_DATA_DIR"] = configured_dir

    paths = get_desktop_paths(environ=environment)

    expected_base = home / "AppData" / "Roaming" if has_appdata else home / ".local" / "share"
    assert paths.root_dir == (expected_base / "InvestScope").resolve()
    assert paths.root_dir != Path.cwd()
    assert not home.exists()


@pytest.mark.parametrize("configured_dir", [None, "", "   "], ids=["unset", "empty", "whitespace"])
def test_settings_and_database_url_ignore_blank_data_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_dir: str | None,
) -> None:
    home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    environment = {} if configured_dir is None else {"INVESTSCOPE_DATA_DIR": configured_dir}
    # Explicit environment also isolates BaseSettings and get_database_url from the host.
    with patch.dict(os.environ, environment, clear=True):
        settings = Settings(mode="desktop", _env_file=None)
        assert settings.data_dir is None
        paths = get_desktop_paths(settings.data_dir, environ=environment)
        assert Path(get_database_url(settings).database or "") == paths.database_path
    assert paths.root_dir == (home / ".local" / "share" / "InvestScope").resolve()
    assert paths.root_dir != Path.cwd()
    assert not home.exists()


@pytest.mark.parametrize("data_dir", ["", "   "])
def test_explicit_blank_data_dir_is_not_a_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data_dir: str,
) -> None:
    home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert Settings(data_dir=data_dir, _env_file=None).data_dir is None
    assert get_desktop_paths(data_dir, environ={}).root_dir == (
        home / ".local" / "share" / "InvestScope"
    ).resolve()
    override = tmp_path / "explicit-env-dir"
    assert get_desktop_paths(data_dir, environ={"INVESTSCOPE_DATA_DIR": str(override)}).root_dir == override.resolve()
    assert not home.exists()
    assert not override.exists()


def test_blank_platform_environment_paths_do_not_resolve_to_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    paths = get_desktop_paths(environ={"APPDATA": "   ", "XDG_DATA_HOME": ""})
    assert paths.root_dir == (home / ".local" / "share" / "InvestScope").resolve()
    assert paths.root_dir != Path.cwd()
    assert not home.exists()


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
    environment = {"INVESTSCOPE_DATA_DIR": str(data_dir)}
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "fake-home"))

    import app.core.paths as paths_module

    with patch.dict(os.environ, environment, clear=True):
        with patch.object(Path, "mkdir", side_effect=AssertionError("implicit directory creation")):
            importlib.reload(paths_module)
            paths = paths_module.get_desktop_paths(environ=environment)

    assert paths.root_dir == data_dir.resolve()
    assert not data_dir.exists()

    create_desktop_directories(paths)
    assert paths.root_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.imports_dir.is_dir()
    assert paths.backups_dir.is_dir()


def test_default_directories_created_only_explicitly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "fake-home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    import app.core.paths as paths_module

    with patch.dict(os.environ, {"INVESTSCOPE_DATA_DIR": "   "}, clear=True):
        with patch.object(Path, "mkdir", side_effect=AssertionError("implicit directory creation")):
            importlib.reload(paths_module)
            paths = paths_module.get_desktop_paths(environ={"INVESTSCOPE_DATA_DIR": "   "})
    assert not home.exists()

    paths_module.create_desktop_directories(paths)

    assert all(directory.is_dir() for directory in (
        paths.root_dir, paths.logs_dir, paths.imports_dir, paths.backups_dir,
    ))
    assert not paths.database_path.exists()
