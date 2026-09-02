"""Read-only project resources available from source and PyInstaller runtimes."""

from __future__ import annotations

import sys
from pathlib import Path


def application_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def application_resource_path(*parts: str) -> Path:
    return application_resource_root().joinpath(*parts)
