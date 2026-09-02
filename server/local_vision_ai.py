"""Machine-local Ollama model management for V2 settings.

Only the executable resolved from an explicit environment override or PATH is
used; no machine-specific installation path is assumed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from server.runtime_process import no_window_kwargs
from dataclasses import dataclass, asdict
from typing import Any

MODELS = {"qwen2.5vl:3b": {"label": "兼容模式", "size": "约 3.2 GB"}, "qwen2.5vl:7b": {"label": "质量模式", "size": "约 6.0 GB"}}
_LOCK = threading.Lock()


@dataclass
class _Download:
    model: str = ""
    status: str = "idle"
    progress: str = ""
    error: str = ""


_DOWNLOAD = _Download()


def _executable() -> str | None:
    override = str(os.environ.get("OLLAMA_EXECUTABLE") or "").strip()
    if override and os.path.isfile(override):
        return override
    return shutil.which("ollama")


def _installed_models(executable: str) -> list[str]:
    completed = subprocess.run([executable, "list"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False, **no_window_kwargs())
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "无法读取 Ollama 模型列表").strip()[:400])
    return [line.split()[0] for line in completed.stdout.splitlines()[1:] if line.split()]


def status() -> dict[str, Any]:
    executable = _executable()
    models: list[str] = []
    error = ""
    if executable:
        try:
            models = _installed_models(executable)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            error = str(exc)
    with _LOCK:
        download = asdict(_DOWNLOAD)
    return {"ollamaFound": bool(executable), "ollamaExecutable": executable or "", "installedModels": models,
            "supportedModels": [{"id": model, **meta, "installed": model in models} for model, meta in MODELS.items()],
            "download": download, "error": error}


def start_download(model: str) -> dict[str, Any]:
    if model not in MODELS:
        raise ValueError("不支持下载该本地视觉模型")
    executable = _executable()
    if not executable:
        raise ValueError("未检测到 Ollama。请先安装 Ollama，并确保 ollama 命令可用后再检测。")
    with _LOCK:
        if _DOWNLOAD.status in {"queued", "downloading"}:
            raise ValueError("已有模型正在下载，请等待完成")
        _DOWNLOAD.model, _DOWNLOAD.status, _DOWNLOAD.progress, _DOWNLOAD.error = model, "queued", "准备下载", ""
    threading.Thread(target=_download, args=(executable, model), name="v2-ollama-pull", daemon=True).start()
    return status()


def _download(executable: str, model: str) -> None:
    try:
        with _LOCK:
            _DOWNLOAD.status, _DOWNLOAD.progress = "downloading", "正在连接 Ollama…"
        process = subprocess.Popen([executable, "pull", model], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", **no_window_kwargs())
        assert process.stdout is not None
        for line in process.stdout:
            text = line.strip()
            if text:
                with _LOCK:
                    _DOWNLOAD.progress = text[-180:]
        if process.wait() != 0:
            raise RuntimeError("Ollama 下载模型失败")
        installed = _installed_models(executable)
        if model not in installed:
            raise RuntimeError("模型下载完成后未能在 Ollama 中确认")
        with _LOCK:
            _DOWNLOAD.status, _DOWNLOAD.progress = "completed", "模型已下载并确认可用"
    except Exception as exc:  # noqa: BLE001
        with _LOCK:
            _DOWNLOAD.status, _DOWNLOAD.error = "error", str(exc)[:400]
