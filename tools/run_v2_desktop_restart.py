"""Restart the V2 development desktop as one owned local runtime."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_SCRIPT = (PROJECT_ROOT / "tools" / "run_v2_file_service.py").resolve()
DESKTOP_SCRIPT = (PROJECT_ROOT / "tools" / "run_v2_desktop_test.py").resolve()
V2_PORTS = (8782, 3000)


def _powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def stop_v2_processes() -> None:
    """Stop only V2 processes before starting a fresh, single-owner pair.

    The release executable and the source checkout both use port 8782. The
    old implementation stopped only the source service, leaving a Portable
    process (or Vite on port 3000) alive and causing SQLite lock contention.
    """
    project_marker = _powershell_quote(str(PROJECT_ROOT))
    service_marker = _powershell_quote(str(SERVICE_SCRIPT))
    desktop_marker = _powershell_quote(str(DESKTOP_SCRIPT))
    command = (
        f"$project = '{project_marker}'; "
        f"$service = '{service_marker}'; "
        f"$desktop = '{desktop_marker}'; "
        "$listen = @(Get-NetTCPConnection -State Listen -LocalPort 8782,3000 "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess); "
        "$target = Get-CimInstance Win32_Process | Where-Object { "
        "$cmd = [string]$_.CommandLine; "
        "$_.ProcessId -ne $PID -and ("
        "($cmd -like ('*' + $service + '*')) -or "
        "($cmd -like ('*' + $desktop + '*')) -or "
        "($cmd -like ('*' + $project + '*') -and $cmd -match 'vite[\\/]+bin[\\/]+vite\\.js') -or "
        "($_.ProcessId -in $listen -and (($cmd -like '*ShortDramaPlatform_V2*') -or "
        "$_.Name -eq 'ShortDramaPlatform.exe' -or $cmd -like '*run_v2_file_service.py*'))"
        ") "
        "}; $target | Sort-Object ProcessId -Unique | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _port_is_free(port: int) -> bool:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
         f"@(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue).Count"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() in {"", "0"}


def wait_for_ports_to_close() -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if all(_port_is_free(port) for port in V2_PORTS):
            return
        time.sleep(0.25)
    busy = ", ".join(str(port) for port in V2_PORTS if not _port_is_free(port))
    raise RuntimeError(f"无法释放 V2 端口：{busy}。请关闭残留的 V2 窗口后重试。")


def _runtime_command() -> tuple[str, list[str]]:
    """Prefer a Python installation that actually contains pywebview."""
    probe = ["-c", "import webview"]
    current = subprocess.run([sys.executable, *probe], check=False, capture_output=True)
    if current.returncode == 0:
        return sys.executable, []
    launcher = shutil.which("py.exe") or shutil.which("py")
    if launcher:
        candidate = subprocess.run([launcher, "-3.12", *probe], check=False, capture_output=True)
        if candidate.returncode == 0:
            return launcher, ["-3.12"]
    raise RuntimeError("找不到已安装 pywebview 的 Python 运行时；请使用 Python 3.12 环境启动 V2。")


def main() -> None:
    stop_v2_processes()
    wait_for_ports_to_close()
    executable, prefix = _runtime_command()
    os.execv(executable, [executable, *prefix, str(DESKTOP_SCRIPT), *sys.argv[1:]])


if __name__ == "__main__":
    main()
