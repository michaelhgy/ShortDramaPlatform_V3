"""Helpers for child processes in source and PyInstaller runtimes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def worker_command(module: str, source_script: Path, args: Sequence[str] = ()) -> list[str]:
    """Return a child command that works both from source and frozen EXE."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--v2-worker", module, *map(str, args)]
    return [sys.executable, str(source_script), *map(str, args)]


def no_window_kwargs() -> dict[str, int]:
    """Suppress console windows for GUI-launched CLI children on Windows."""
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}

