"""Local Ollama lifecycle and request helpers for finished-video detection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "qwen2.5vl:7b"
VISION_CONTEXT_TOKENS = 8192
TAGS_URL = "http://127.0.0.1:11434/api/tags"
CHAT_URL = "http://127.0.0.1:11434/api/chat"
GENERATE_URL = "http://127.0.0.1:11434/api/generate"
_CHAT_LOCK = threading.Lock()


@contextmanager
def _vision_process_lock():
    """Serialize image inference across the generator subprocesses."""
    lock_path = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".") / "short_drama_v2_ollama.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    try:
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class LocalOllamaError(RuntimeError):
    """A local Ollama error with enough detail for a recoverable task record."""


def _error_detail(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        try:
            body = error.read().decode("utf-8", errors="replace").strip()
        except OSError:
            body = ""
        return f"HTTP {error.code}: {body or error.reason}"
    return str(error)


def _request_json(url: str, payload: dict[str, Any] | None = None, *, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _find_ollama() -> str | None:
    explicit = str(os.environ.get("OLLAMA_EXECUTABLE") or "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    located = shutil.which("ollama")
    return located or None


def _start_ollama(executable: str) -> None:
    try:
        subprocess.Popen(
            [executable, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise LocalOllamaError(f"OLLAMA_START_FAILED: {error}") from error


def _unload_other_models(selected: str) -> None:
    """Free stale vision models before loading the selected one."""
    try:
        running = _request_json("http://127.0.0.1:11434/api/ps", timeout=5.0).get("models", [])
        for item in running if isinstance(running, list) else []:
            name = str(item.get("name") or "") if isinstance(item, dict) else ""
            if name and name != selected:
                _request_json(GENERATE_URL, {"model": name, "prompt": "", "stream": False, "keep_alive": 0}, timeout=15.0)
    except Exception:
        # The selected model request below remains authoritative; an inability
        # to inspect the process list must not turn a healthy Ollama into a
        # false setup failure.
        return


def ensure_local_ollama(
    model: str = DEFAULT_MODEL,
    *,
    startup_timeout: float = 30.0,
    context_tokens: int = VISION_CONTEXT_TOKENS,
) -> dict[str, Any]:
    """Start Ollama when needed, then prove the requested local model is usable."""
    executable = _find_ollama()
    if not executable:
        raise LocalOllamaError("OLLAMA_EXECUTABLE_NOT_FOUND: 未找到本机 ollama.exe")
    started = False
    try:
        tags = _request_json(TAGS_URL, timeout=5.0)
    except Exception:
        _start_ollama(executable)
        started = True
        deadline = time.monotonic() + startup_timeout
        while True:
            try:
                tags = _request_json(TAGS_URL, timeout=5.0)
                break
            except Exception as error:
                if time.monotonic() >= deadline:
                    raise LocalOllamaError(f"OLLAMA_SERVICE_TIMEOUT: {_error_detail(error)}") from error
                time.sleep(0.5)
    models = [str(item.get("name", "")) for item in tags.get("models", []) if isinstance(item, dict)]
    if model not in models:
        raise LocalOllamaError(f"OLLAMA_MODEL_MISSING: 未安装模型 {model}；已有模型：{', '.join(models) or '无'}")
    _unload_other_models(model)
    if context_tokens < VISION_CONTEXT_TOKENS:
        raise LocalOllamaError(f"OLLAMA_CONTEXT_INVALID: 本地视觉检测至少需要 {VISION_CONTEXT_TOKENS} 上下文")
    request_chat({
        "model": model,
        "stream": False,
        "keep_alive": "10m",
        "options": {"num_predict": 1, "num_ctx": context_tokens},
        "messages": [{"role": "user", "content": "ping"}],
    }, timeout=45.0)
    return {"executable": executable, "model": model, "started": started, "context_tokens": context_tokens}


def request_chat(payload: dict[str, Any], *, timeout: float = 180.0, attempts: int = 3) -> dict[str, Any]:
    """Send a chat request, allowing a just-started Ollama process to settle."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    last_error: BaseException | None = None
    # Vision inference is GPU/memory heavy.  Ollama may return done=false
    # with an empty message when several generators submit images together,
    # so serialize requests across all V2 generator processes.
    with _CHAT_LOCK, _vision_process_lock():
        for attempt in range(1, attempts + 1):
            try:
                response = _request_json(CHAT_URL, payload, timeout=timeout)
                # Ollama can occasionally return a syntactically valid but
                # unfinished response while loading a vision model (done=false
                # and an empty message).  Treat that as a retriable model/runtime
                # failure instead of passing it to the JSON parser as if it were
                # a valid inference result.
                message = response.get("message") if isinstance(response, dict) else None
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(response, dict) or response.get("done") is False or not str(content or "").strip():
                    raise LocalOllamaError(
                        f"OLLAMA_INCOMPLETE_RESPONSE: 模型未完成响应（done={response.get('done') if isinstance(response, dict) else None!r}）"
                    )
                return response
            except (LocalOllamaError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
                if attempt < attempts:
                    time.sleep(float(attempt))
    assert last_error is not None
    raise LocalOllamaError(
        f"OLLAMA_CHAT_FAILED after {attempts} attempts: {_error_detail(last_error)}"
    ) from last_error
