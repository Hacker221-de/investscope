from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DesktopPaths:
    root_dir: Path
    database_path: Path
    logs_dir: Path
    imports_dir: Path
    backups_dir: Path


def get_desktop_paths(
    data_dir: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> DesktopPaths:
    """Resolve desktop paths without creating files or directories."""
    environment = os.environ if environ is None else environ
    configured_dir = data_dir or environment.get("INVESTSCOPE_DATA_DIR")
    if configured_dir is not None:
        root_dir = Path(configured_dir).expanduser().resolve()
    else:
        app_data = environment.get("APPDATA")
        if app_data:
            root_dir = (Path(app_data) / "InvestScope").resolve()
        else:
            # This fallback keeps tests and non-Windows development usable while
            # Windows continues to default to %APPDATA%\InvestScope.
            data_home = environment.get("XDG_DATA_HOME")
            base_dir = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
            root_dir = (base_dir / "InvestScope").resolve()

    return DesktopPaths(
        root_dir=root_dir,
        database_path=root_dir / "investscope.db",
        logs_dir=root_dir / "logs",
        imports_dir=root_dir / "imports",
        backups_dir=root_dir / "backups",
    )


def create_desktop_directories(paths: DesktopPaths) -> None:
    """Create the writable desktop directory tree explicitly."""
    for directory in (
        paths.root_dir,
        paths.logs_dir,
        paths.imports_dir,
        paths.backups_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
