"""V2 全局任务中心的最小真实调度层。

当前只调度模板草稿任务；成片和视频导出器接入前不会被伪造为可执行。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

try:
    from server import v2_file_service as service
except ModuleNotFoundError:  # 支持直接执行 V2 服务脚本
    import v2_file_service as service  # type: ignore[no-redef]


_STOP = threading.Event()
_STARTED = False
_START_LOCK = threading.Lock()
_DISPATCH_LOCK = threading.Lock()
_PAUSED = False


def _format_duration(started_at: str, finished_at: str = "") -> tuple[int, str]:
    if not started_at:
        return 0, "—"
    try:
        started = datetime.fromisoformat(started_at)
        ended = datetime.fromisoformat(finished_at) if finished_at else datetime.now()
        seconds = max(0, int((ended - started).total_seconds()))
    except ValueError:
        return 0, "—"
    if seconds < 60:
        return seconds, f"{seconds:02d}秒"
    return seconds, f"{seconds // 60}分{seconds % 60:02d}秒"


def _claim_next_template_job() -> str | None:
    if _PAUSED:
        return None
    with _DISPATCH_LOCK:
        conn = service.connection()
        try:
            row = conn.execute(
                "SELECT j.id FROM template_jobs j JOIN production_tasks t ON t.id=j.task_id "
                "WHERE j.status='queued' ORDER BY CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, "
                "t.planned_publish_at, j.created_at, j.version_no LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job_id = str(row["id"])
            updated = conn.execute(
                "UPDATE template_jobs SET status='dispatching', updated_at=? WHERE id=? AND status='queued'",
                (service.now_text(), job_id),
            ).rowcount
            conn.commit()
            return job_id if updated == 1 else None
        finally:
            conn.close()


def dispatch_once() -> bool:
    job_id = _claim_next_template_job()
    if not job_id:
        return False
    from server.template_engine.runner import run_template_job
    threading.Thread(target=run_template_job, args=(job_id,), name=f"v2-template-dispatch-{job_id[:8]}", daemon=True).start()
    return True


def _loop() -> None:
    while not _STOP.wait(0.5):
        try:
            dispatch_once()
        except Exception:
            # 单个任务的错误由 runner 写回任务；调度循环不能因一个任务退出。
            continue


def start_scheduler() -> None:
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        _STARTED = True
        threading.Thread(target=_loop, name="v2-task-center", daemon=True).start()


def stop_scheduler() -> None:
    _STOP.set()


def set_queue_paused(paused: bool) -> None:
    global _PAUSED
    _PAUSED = bool(paused)


def task_center_snapshot() -> dict[str, Any]:
    """Return the task-center view model; no Mock data is inserted."""
    conn = service.connection()
    try:
        rows = conn.execute(
            "SELECT j.*, t.account_name, t.drama_name, t.planned_publish_at "
            "FROM template_jobs j LEFT JOIN production_tasks t ON t.id=j.task_id "
            "WHERE j.version_no=(SELECT MAX(latest.version_no) FROM template_jobs latest WHERE latest.task_id=j.task_id) "
            "ORDER BY j.created_at DESC, j.version_no DESC"
        ).fetchall()
    finally:
        conn.close()
    tasks = [_task_item(row) for row in rows]
    waiting = sum(1 for item in tasks if item["status"] == "waiting")
    running = sum(1 for item in tasks if item["status"] == "running")
    completed = sum(1 for item in tasks if item["status"] == "done")
    timeout = sum(1 for item in tasks if item["status"] == "timeout")
    return {
        "executors": [{
            "id": "template_generator", "name": "模板生成器", "subtitle": "模板草稿",
            "description": "按队列顺序串行生成模板草稿", "status": "running" if running else ("waiting" if waiting else "idle"),
            "currentTaskId": next((item["id"] for item in tasks if item["status"] == "running"), None),
            "runningSeconds": 0, "isTimeout": bool(timeout), "timeoutThresholdSeconds": 900,
            "queueStats": {"completed": completed, "running": running, "waiting": waiting, "total": len(tasks), "timeoutCount": timeout},
        }],
        "tasks": tasks,
        "dramaPriorities": [],
        "isQueuePaused": _PAUSED,
    }


def _task_item(row: Any) -> dict[str, Any]:
    raw = str(row["status"])
    is_timeout = raw == "timeout"
    if raw in {"queued", "dispatching"}:
        overall, draft_status, progress = "waiting", "waiting", 0
    elif raw == "running":
        overall, draft_status, progress = "running", "running", 20
    elif raw == "draft_ready":
        overall, draft_status, progress = "waiting", "done", 60
    elif is_timeout:
        overall, draft_status, progress = "timeout", "timeout", 0
    else:
        overall, draft_status, progress = "error", "error", 0
    error = str(row["error_message"] or "")
    duration_seconds, duration_formatted = _format_duration(str(row["started_at"] or ""), str(row["finished_at"] or ""))
    return {
        "id": str(row["id"]), "taskCategory": "template", "accountName": str(row["account_name"] or "未知账号"),
        "dramaName": str(row["drama_name"] or "未知剧集"), "title": f"{row['account_name'] or '未知账号'} × 《{row['drama_name'] or '未知剧集'}》 · 模板制作",
        "draftStage": {"status": draft_status, "progress": progress, "errorDetail": error or None},
        "videoStage": {"status": "idle", "progress": 0}, "scheduledPublishTime": str(row["planned_publish_at"] or ""),
        "priorityRank": 0, "priorityTag": "模板任务", "status": overall, "progress": progress,
        "createdAt": str(row["created_at"]), "startedAt": str(row["started_at"] or "") or None,
        "completedAt": str(row["finished_at"] or "") or None, "durationSeconds": duration_seconds, "durationFormatted": duration_formatted,
        "draftDurationSeconds": duration_seconds, "draftDurationFormatted": duration_formatted,
        "isTimeout": is_timeout, "hasValidDraft": raw == "draft_ready", "hasCompletedFirstExport": False,
        "taskType": "template_draft", "executorId": "template_generator", "executorName": "模板生成器",
        "isOrphan": row["task_id"] is not None and row["account_name"] is None,
        "draftPath": str(row["draft_path"] or "") or None, "diagnosticLog": str(row["log_path"] or "") or None,
        "errorDetail": error or None,
    }
