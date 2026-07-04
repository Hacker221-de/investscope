"""Desktop-only initialization helpers."""

from app.desktop.bootstrap import (
    DesktopBootstrapBusyError,
    DesktopBootstrapError,
    DesktopBootstrapResult,
    bootstrap_desktop,
)

__all__ = [
    "DesktopBootstrapBusyError",
    "DesktopBootstrapError",
    "DesktopBootstrapResult",
    "bootstrap_desktop",
]
