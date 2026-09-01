"""Locate V2-managed external executables without making PATH a production prerequisite."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Mapping


class ToolResolutionError(RuntimeError):
    pass


def application_resource_root() -> Path:
    """Return read-only application resources in source and PyInstaller runs."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def resolve_ffmpeg() -> Path:
    return resolve_tool("ffmpeg")


def resolve_ffprobe() -> Path:
    return resolve_tool("ffprobe")


def resolve_tool(
    name: str,
    *,
    resource_root: Path | None = None,
    frozen: bool | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> Path:
    """Resolve a managed FFmpeg binary, with development-only fallbacks."""
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError(f"不支持的受控工具：{name}")
    root = (resource_root or application_resource_root()).resolve()
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    executable = f"{name}.exe" if os.name == "nt" else name
    bundled = root / "tools" / "ffmpeg" / "bin" / executable
    if bundled.is_file():
        return bundled
    if is_frozen:
        raise ToolResolutionError(f"正式运行包缺少受控 {executable}：{bundled}")

    values = os.environ if environ is None else environ
    override = str(values.get(f"V2_{name.upper()}_PATH") or "").strip()
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raise ToolResolutionError(f"开发环境 {name} override 不存在：{candidate}")
    located = which(executable) or which(name)
    if located:
        return Path(located).resolve()
    raise ToolResolutionError(f"未找到 {executable}；开发环境可配置 V2_{name.upper()}_PATH")
