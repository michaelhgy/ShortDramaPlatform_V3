"""Resolve the configured Jianying runtime without assuming a fixed install tree."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class JianyingRuntimePaths:
    executable: Path
    draft_root: Path
    user_data_root: Path
    app_root: Path


def _user_data_from_draft_root(draft_root: Path) -> Path | None:
    """Use the configured draft path first; do not infer a fixed parent depth."""
    resolved = draft_root.resolve()
    for candidate in (resolved, *resolved.parents):
        if candidate.name.casefold() == "user data" and candidate.is_dir():
            return candidate
    return None


def _default_user_data_root(environ: Mapping[str, str] | None) -> Path | None:
    environment = os.environ if environ is None else environ
    local_app_data = str(environment.get("LOCALAPPDATA") or "").strip()
    if not local_app_data:
        return None
    candidate = Path(local_app_data).expanduser() / "JianyingPro" / "User Data"
    return candidate if candidate.is_dir() else None


def resolve_jianying_runtime_paths(
    settings: Mapping[str, object], *, environ: Mapping[str, str] | None = None,
) -> JianyingRuntimePaths:
    executable_text = str(settings.get("jianying_executable") or "").strip()
    draft_root_text = str(settings.get("jianying_draft_root") or "").strip()
    if not executable_text or not draft_root_text:
        raise RuntimeError("请先在系统设置中配置剪映程序和剪映草稿目录")

    executable = Path(executable_text).expanduser()
    draft_root = Path(draft_root_text).expanduser()
    if not executable.is_file():
        raise RuntimeError("已配置的剪映程序不存在或不可访问")
    if not draft_root.is_dir():
        raise RuntimeError("已配置的剪映草稿目录不存在或不是目录")

    user_data_text = str(settings.get("jianying_user_data_root") or "").strip()
    user_data_root = Path(user_data_text).expanduser() if user_data_text else None
    if user_data_root is not None and not user_data_root.is_dir():
        raise RuntimeError("已配置的剪映用户数据目录不存在或不是目录")
    if user_data_root is None:
        user_data_root = _user_data_from_draft_root(draft_root)
    if user_data_root is None:
        user_data_root = _default_user_data_root(environ)
    if user_data_root is None:
        raise RuntimeError(
            "未找到剪映用户数据目录；请先在系统设置中配置，或确认当前 Windows 用户已启动过剪映"
        )

    return JianyingRuntimePaths(
        executable=executable.resolve(),
        draft_root=draft_root.resolve(),
        user_data_root=user_data_root.resolve(),
        app_root=executable.resolve().parent,
    )
