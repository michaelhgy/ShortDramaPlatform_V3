"""Windows Jianying process discovery and startup boundary for V1 preflight."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class JianyingRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class JianyingLaunchEvidence:
    executable: str
    started: bool
    pid: int | None
    detail: str


def discover_jianying_executable(config: Any) -> Path | None:
    """Resolve an executable from explicit config or the current Windows profile."""
    if config.jianying_executable:
        return config.jianying_executable.expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    root = Path(local_app_data) / "JianyingPro" / "Apps"
    candidates = [item for item in root.glob("*/JianyingPro.exe") if item.is_file()]
    # The root-level executable is an updater/bootstrapper on some Jianying
    # versions. Prefer the versioned GUI executable when it is available.
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime_ns).resolve()
    direct = root / "JianyingPro.exe"
    if direct.is_file():
        candidates.append(direct)
    return max(candidates, key=lambda item: item.stat().st_mtime_ns).resolve() if candidates else None


class WindowsJianyingRuntime:
    """Start or reuse the installed Jianying process without UI automation clicks."""

    def __init__(
        self,
        *,
        process_path: Callable[[Path], int | None] | None = None,
        launch: Callable[[Path], subprocess.Popen] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.process_path = process_path or _find_visible_process
        self.launch = launch or (lambda executable: subprocess.Popen([str(executable)], cwd=str(executable.parent)))
        self.sleep = sleep

    def ensure_started(self, config: Any, timeout_seconds: float = 30) -> JianyingLaunchEvidence:
        executable = discover_jianying_executable(config)
        if executable is None or not executable.is_file():
            raise JianyingRuntimeError("未找到剪映可执行文件，请在设置中配置剪映路径")
        existing_pid = self.process_path(executable)
        if existing_pid:
            return JianyingLaunchEvidence(str(executable), False, existing_pid, "剪映已在运行")
        process = self.launch(executable)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            pid = self.process_path(executable)
            if pid:
                return JianyingLaunchEvidence(str(executable), True, pid, "剪映已启动")
            if process.poll() not in (None, 0):
                raise JianyingRuntimeError(f"剪映启动失败，进程退出码：{process.returncode}")
            self.sleep(0.25)
        raise JianyingRuntimeError("剪映启动后未在限定时间内出现可用窗口")


def _find_visible_process(executable: Path) -> int | None:
    """Best-effort process lookup using the Windows window list, not shell commands."""
    if os.name != "nt":
        return None
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return None
    found: list[int] = []
    expected = str(executable).casefold()

    def visit(hwnd: int, _extra: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
            try:
                actual = win32process.GetModuleFileNameEx(handle, 0)
            finally:
                win32api.CloseHandle(handle)
        except Exception:
            return True
        if str(Path(actual).resolve()).casefold() == expected:
            found.append(pid)
        return True

    win32gui.EnumWindows(visit, None)
    return found[0] if found else None
