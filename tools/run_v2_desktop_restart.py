"""Restart only the V2 local data service, then open the V2 desktop test window."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_SCRIPT = (PROJECT_ROOT / "tools" / "run_v2_file_service.py").resolve()
DESKTOP_SCRIPT = (PROJECT_ROOT / "tools" / "run_v2_desktop_test.py").resolve()


def stop_v2_service() -> None:
    """Stop processes whose command line points to this V2 service only."""
    marker = str(SERVICE_SCRIPT).replace("'", "''")
    command = (
        "$target = Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.CommandLine -like '*{marker}*' }}; "
        "$target | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    stop_v2_service()
    os.execv(sys.executable, [sys.executable, str(DESKTOP_SCRIPT), *sys.argv[1:]])


if __name__ == "__main__":
    main()
