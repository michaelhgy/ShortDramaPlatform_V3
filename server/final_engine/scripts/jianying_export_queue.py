"""V2-owned filesystem queue writer for prepared finished-video jobs."""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

READY = "READY_FOR_EXPORT"
SCHEMA_VERSION = 1
VALID_KINDS = {"template", "finished_video"}
VALID_MODES = {"MANUAL_CONFIRM", "AUTO_COUNTDOWN_3S", "CONTINUOUS_AUTO"}
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$")


class QueueError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextlib.contextmanager
def _queue_lock(queue_path: Path, timeout_seconds: float = 10.0):
    lock_path = queue_path.with_suffix(queue_path.suffix + ".lock")
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > 120
            except FileNotFoundError:
                continue
            if stale:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise QueueError(f"Timed out waiting for queue lock: {lock_path}")
            time.sleep(.1)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_queue(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Queue does not exist: {path}")
    payload = read_json(path)
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(payload.get("jobs"), list):
        raise QueueError(f"Unsupported or malformed queue: {path}")
    if payload.get("mode") not in VALID_MODES:
        raise QueueError(f"Unsupported queue mode: {payload.get('mode')}")
    return payload


def save_queue(path: Path, payload: dict[str, Any], event: dict[str, Any] | None = None) -> None:
    if event is not None:
        payload.setdefault("events", []).append({"at": now(), **event})
    write_json(path, payload)


def enqueue_job(queue_path: Path, job: dict[str, Any]) -> None:
    """Append a validated prepared job without overwriting an existing output."""
    with _queue_lock(queue_path):
        queue = load_queue(queue_path)
        job_id = str(job.get("job_id", ""))
        if not JOB_ID_RE.fullmatch(job_id):
            raise QueueError("job-id must use only letters, digits, dot, dash or underscore")
        if str(job.get("kind", "")) not in VALID_KINDS:
            raise QueueError(f"Unsupported job kind: {job.get('kind')}")
        if job.get("status") != READY:
            raise QueueError("New queue jobs must start in READY_FOR_EXPORT")
        output = Path(str(job.get("output_path", ""))).resolve()
        if output.suffix.casefold() != ".mp4":
            raise QueueError("output-path must end in .mp4")
        if output.exists():
            raise FileExistsError(f"Refusing to queue an overwrite: {output}")
        if any(existing.get("job_id") == job_id for existing in queue["jobs"]):
            raise QueueError(f"Duplicate job-id: {job_id}")
        if any(Path(str(existing.get("output_path", ""))).resolve() == output for existing in queue["jobs"]):
            raise QueueError(f"Another job already owns output-path: {output}")
        queue["jobs"].append(job)
        save_queue(queue_path, queue, {"kind": "job_enqueued", "job_id": job_id})
