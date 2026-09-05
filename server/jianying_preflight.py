"""Conservative, side-effect-free readiness checks for the V2 Jianying runtime."""

from __future__ import annotations

import ctypes
import os
import re
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Mapping


class JianyingPreflightStatus(StrEnum):
    READY = "READY"
    NEED_CONFIGURATION = "NEED_CONFIGURATION"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    UNSUPPORTED_OR_UNVERIFIED_VERSION = "UNSUPPORTED_OR_UNVERIFIED_VERSION"
    MISSING_RESOURCE = "MISSING_RESOURCE"
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"


@dataclass(frozen=True)
class JianyingPreflightResult:
    status: JianyingPreflightStatus
    message: str
    version: str = ""
    version_source: str = ""
    details: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "message": self.message,
            "version": self.version,
            "version_source": self.version_source,
            "details": self.details or {},
        }


class JianyingPreflightError(RuntimeError):
    def __init__(self, result: JianyingPreflightResult) -> None:
        self.result = result
        super().__init__(result.message)


def _result(status: JianyingPreflightStatus, message: str, *, version: str = "", version_source: str = "",
            details: dict[str, object] | None = None) -> JianyingPreflightResult:
    return JianyingPreflightResult(status, message, version, version_source, details)


def _read_file_version(executable: Path) -> tuple[str, str]:
    """Use Windows file metadata; the install-directory name is only a fallback."""
    try:
        import win32api

        info = win32api.GetFileVersionInfo(str(executable), "\\")
        ms, ls = int(info["FileVersionMS"]), int(info["FileVersionLS"])
        version = f"{ms >> 16}.{ms & 0xffff}.{ls >> 16}.{ls & 0xffff}"
        if version != "0.0.0.0":
            return version, "file_version"
    except Exception:
        pass
    if re.fullmatch(r"\d+\.\d+(?:\.\d+){0,2}", executable.parent.name):
        return executable.parent.name, "install_directory"
    return "", ""


def _check_interactive_desktop() -> None:
    if not ctypes.windll.user32.GetDesktopWindow():
        raise RuntimeError("未检测到可交互的 Windows 桌面")


def _check_automation_imports() -> None:
    # Import only: this must not create a window or send any UI input.
    import uiautomation  # noqa: F401
    import win32api  # noqa: F401
    from server.windows_automation.jianying59_exporter.upstream_adapter import PyJianyingUpstreamAdapter  # noqa: F401
    from server.windows_automation.jianying_adapter import WindowsInputLeaseAdapter  # noqa: F401
    from server.windows_automation.jianying_runtime import WindowsJianyingRuntime  # noqa: F401


def _probe_draft_root(draft_root: Path) -> None:
    # The directory is created and removed immediately; no production draft is touched.
    with tempfile.TemporaryDirectory(prefix=".v2-preflight-", dir=draft_root):
        pass


def _valid_executable(executable: Path) -> bool:
    return (executable.is_file() and executable.suffix.lower() == ".exe" and executable.name.lower() == "jianyingpro.exe"
            and any(part.lower() == "jianyingpro" for part in executable.parts[:-1]))


def run_jianying_preflight(
    settings: Mapping[str, object],
    *,
    environ: Mapping[str, str] | None = None,
    is_windows: bool | None = None,
    version_reader: Callable[[Path], tuple[str, str]] = _read_file_version,
    interactive_checker: Callable[[], None] = _check_interactive_desktop,
    automation_checker: Callable[[], None] = _check_automation_imports,
    draft_probe: Callable[[Path], None] = _probe_draft_root,
) -> JianyingPreflightResult:
    """Check only the configured runtime. Candidate installations are never adopted."""
    executable_text = str(settings.get("jianying_executable") or "").strip()
    draft_root_text = str(settings.get("jianying_draft_root") or "").strip()
    if not executable_text or not draft_root_text:
        missing = "、".join(name for name, value in (("剪映程序", executable_text), ("剪映草稿目录", draft_root_text)) if not value)
        return _result(JianyingPreflightStatus.NEED_CONFIGURATION, f"请先在系统设置中配置{missing}")

    executable = Path(executable_text).expanduser()
    draft_root = Path(draft_root_text).expanduser()
    if not _valid_executable(executable):
        return _result(JianyingPreflightStatus.INVALID_CONFIGURATION, "已配置的剪映程序无效：需要可访问的 JianyingPro.exe，未自动改用其他安装路径")
    if not draft_root.is_dir():
        return _result(JianyingPreflightStatus.INVALID_CONFIGURATION, "已配置的剪映草稿目录不存在或不是目录")
    try:
        draft_probe(draft_root)
    except OSError as exc:
        return _result(JianyingPreflightStatus.INVALID_CONFIGURATION, f"已配置的剪映草稿目录不可写入临时探测：{exc}")

    version, version_source = version_reader(executable)
    if not version or not (version == "5.9" or version.startswith("5.9.")):
        shown = f"（检测到 {version}）" if version else ""
        return _result(JianyingPreflightStatus.UNSUPPORTED_OR_UNVERIFIED_VERSION,
                       f"无法确认受支持的剪映专业版 5.9{shown}；V2 当前仅验证 5.9", version=version,
                       version_source=version_source)

    environment = dict(os.environ if environ is None else environ)
    local_app_data = Path(str(environment.get("LOCALAPPDATA") or "")).expanduser()
    user_data = local_app_data / "JianyingPro" / "User Data"
    app_root = executable.parent
    required = {
        "剪映用户数据目录": user_data,
        "默认调节资源 combine_adjust": app_root / "Resources" / "DefaultAdjustBundle" / "combine_adjust",
        "默认调节资源 hsl_v1": app_root / "Resources" / "DefaultAdjustBundle" / "hsl_v1",
        "中文系统字体 zh-hans.ttf": app_root / "Resources" / "Font" / "SystemFont" / "zh-hans.ttf",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        return _result(JianyingPreflightStatus.MISSING_RESOURCE, f"剪映 5.9 缺少运行资源：{'、'.join(missing)}",
                       version=version, version_source=version_source, details={"missing_resources": missing})

    if not (os.name == "nt" if is_windows is None else is_windows):
        return _result(JianyingPreflightStatus.ENVIRONMENT_ERROR, "剪映自动化只能在 Windows 交互式桌面运行", version=version, version_source=version_source)
    try:
        interactive_checker()
        automation_checker()
    except Exception as exc:
        return _result(JianyingPreflightStatus.ENVIRONMENT_ERROR, f"Windows 剪映自动化运行环境不可用：{exc}",
                       version=version, version_source=version_source)
    return _result(JianyingPreflightStatus.READY, "剪映 5.9 运行环境已就绪", version=version,
                   version_source=version_source, details={"required_resource_count": len(required)})


def require_jianying_ready(settings: Mapping[str, object]) -> JianyingPreflightResult:
    result = run_jianying_preflight(settings)
    if result.status is not JianyingPreflightStatus.READY:
        raise JianyingPreflightError(result)
    return result
