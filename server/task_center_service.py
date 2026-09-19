"""V2 全局任务中心的最小真实调度层。"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
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
_PRIORITY_CACHE: tuple[float, dict[str, int]] = (0.0, {})
# 手动调整排序后的顺序缓存。同一份快照里每个任务卡都要问一次顺序，不能每次都查库。
_ORDER_CACHE: tuple[float, dict[str, int]] = (0.0, {})
_ORDER_CACHE_LOCK = threading.Lock()
# 成片草稿生成器已具备真实执行入口，由任务中心统一调度。
FINAL_GENERATOR_READY = True


def _user_facing_error_detail(raw_error: str) -> str | None:
    """Turn persisted worker output into a short, safe task-card message.

    The database deliberately preserves the complete worker error for later
    diagnosis. A task card must not render a whole batch-result JSON document:
    it makes the task-centre response unnecessarily large and can make the
    browser look as if the page itself has crashed.
    """
    raw = str(raw_error or "").strip()
    if not raw:
        return None
    normalized = " ".join(raw.split())
    if "WinError 10048" in normalized or "端口正被其他程序占用" in normalized:
        return "本地分析服务启动失败：端口正被其他程序占用。请等待当前分析任务结束后再重试。"
    if any(marker in normalized for marker in ("LocalOllamaError", "OLLAMA_CHAT_FAILED", "OLLAMA_INCOMPLETE_RESPONSE")):
        return "本地视觉模型响应失败：模型没有完成返回。请确认 Ollama 正常运行后再重试。"
    # Batch generation stores individual material errors in a JSON-like result.
    # The first explicit error is useful to the operator; the rest stays in the
    # persisted log rather than flooding the card.
    marker = '\"error\"'
    start = normalized.find(marker)
    if start >= 0:
        fragment = normalized[start + len(marker):].lstrip(" :")
        if fragment.startswith('\"'):
            end = fragment.find('\"', 1)
            if end > 1:
                normalized = fragment[1:end]
    return normalized[:280] + ("…" if len(normalized) > 280 else "")


def _diagnostic_log_excerpt(raw_error: str) -> str | None:
    """Keep task-detail diagnostics readable without discarding DB evidence."""
    raw = str(raw_error or "").strip()
    if not raw:
        return None
    limit = 1600
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "\n\n（页面仅显示前 1600 个字符；完整错误已保留在任务记录和生成日志中。）"


def _executor_diagnostic(run_id: str, raw_error: str) -> str | None:
    """Prefer the real execution trail; retain the terminal error below it."""
    trace = service.executor_trace_excerpt(run_id)
    error = _diagnostic_log_excerpt(raw_error)
    if trace and error:
        return f"{trace}\n\n最终结果：{error}"
    return trace or error


def _executor_available(executor_id: str) -> bool:
    from server.executor_management import ExecutorManager
    conn = service.connection()
    try:
        state = ExecutorManager(conn).state(executor_id)
        return not bool(state.get("is_paused")) and not bool(state.get("pause_requested")) and not str(state.get("current_task_id") or "")
    finally:
        conn.close()


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
    if _PAUSED or not _executor_available("template_generator"):
        return None
    with _DISPATCH_LOCK:
        conn = service.connection()
        try:
            row = conn.execute(
                "SELECT j.id FROM template_jobs j JOIN production_tasks t ON t.id=j.task_id "
                "WHERE j.status='queued' ORDER BY " + _manual_order_key(conn) +
                "CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, "
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
            if updated != 1:
                return None
            from server.executor_management import ExecutorManager
            ExecutorManager(conn).set_current_task("template_generator", job_id)
            return job_id
        finally:
            conn.close()


def _claim_next_final_video() -> str | None:
    if _PAUSED or not _executor_available("final_generator"):
        return None
    with _DISPATCH_LOCK:
        conn = service.connection()
        try:
            from server.executor_management import ExecutorManager
            if not _executor_available("final_generator"):
                return None
            has_export_tables = bool(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name IN ('export_jobs','export_attempts')"
            ).fetchall())
            template_ready_clause = (
                "AND EXISTS (SELECT 1 FROM template_jobs j "
                " JOIN export_jobs ej ON ej.subject_type='template' AND ej.subject_id=j.id AND ej.status='completed' "
                " JOIN export_attempts ea ON ea.job_id=ej.id "
                " WHERE j.task_id=t.id AND j.status='draft_ready' AND ea.status='completed' "
                " AND ea.attempt_no=(SELECT MAX(latest.attempt_no) FROM export_attempts latest WHERE latest.job_id=ej.id)) "
                if has_export_tables else
                "AND EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=t.id AND j.status='draft_ready') "
            )
            query = (
                "SELECT v.id FROM production_video_tasks v JOIN production_tasks t ON t.id=v.task_id "
                "JOIN production_files f ON f.id=v.source_material_id "
                # A failed task is not waiting work.  It must remain visible
                # for an explicit user retry; otherwise resuming a paused
                # executor immediately retries the same failure forever.
                "WHERE v.status='pending_generation' "
                # 成片生成只能使用已完成且已校验的模板导出版本；模板草稿
                # 写出不等于模板 MP4 已就绪，不能让成片任务越过导出队列。
                + template_ready_clause
                # 同一生产任务内按素材登记序号推进。重试时创建时间不能让
                # -3 跑到 -2 前面；序号是生产素材的业务顺序，不从文件名临时解析。
                + "ORDER BY " + _manual_order_key(conn)
                + "CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at, "
                + "CASE WHEN f.sequence_no IS NULL THEN 1 ELSE 0 END, f.sequence_no, f.file_name, v.created_at LIMIT 1"
            )
            row = conn.execute(query).fetchone()
            if not row:
                return None
            video_id = str(row["id"])
            updated = conn.execute("UPDATE production_video_tasks SET status='generation_queued', updated_at=? WHERE id=? AND status='pending_generation'", (service.now_text(), video_id)).rowcount
            conn.commit()
            if updated != 1:
                return None
            ExecutorManager(conn).set_current_task("final_generator", video_id)
            return video_id
        finally:
            conn.close()


def _claim_next_export_attempt() -> str | None:
    if _PAUSED or not _executor_available("video_exporter"):
        return None
    with _DISPATCH_LOCK:
        conn = service.connection()
        try:
            from server.executor_management import ExecutorManager
            if not _executor_available("video_exporter"):
                return None
            row = conn.execute(
                "SELECT a.id FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id "
                "JOIN production_tasks t ON t.id=j.production_task_id "
                "LEFT JOIN production_video_tasks v ON j.subject_type='final' AND v.id=j.subject_id "
                "LEFT JOIN production_files f ON f.id=v.source_material_id "
                "WHERE a.status='queued' AND j.status='queued' "
                "ORDER BY CASE WHEN j.subject_type='template' THEN 0 ELSE 1 END, "
                # 模板仍是所有视频导出的最高优先级。成片则先按所属生产任务
                # 优先级，再按素材序号；首次导出和重新导出没有额外插队权。
                + _manual_order_key(conn)
                + "CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at, "
                "CASE WHEN j.subject_type='final' AND f.sequence_no IS NULL THEN 1 ELSE 0 END, "
                "CASE WHEN j.subject_type='final' THEN f.sequence_no ELSE 0 END, "
                "CASE WHEN j.subject_type='final' THEN f.file_name ELSE j.draft_name END, "
                "j.created_at, a.attempt_no LIMIT 1"
            ).fetchone()
            if not row:
                return None
            attempt_id = str(row["id"])
            updated = conn.execute("UPDATE export_jobs SET status='active',updated_at=? WHERE id=(SELECT job_id FROM export_attempts WHERE id=?) AND status='queued'", (service.now_text(), attempt_id)).rowcount
            if updated != 1:
                return None
            conn.commit()
            ExecutorManager(conn).set_current_task("video_exporter", attempt_id)
            return attempt_id
        finally:
            conn.close()


def dispatch_once() -> bool:
    dispatched = False
    job_id = _claim_next_template_job()
    if job_id:
        from server.template_engine.runner import run_template_job
        threading.Thread(target=run_template_job, args=(job_id,), name=f"v2-template-dispatch-{job_id[:8]}", daemon=True).start()
        dispatched = True
    if FINAL_GENERATOR_READY:
        video_id = _claim_next_final_video()
        if video_id:
            from server.final_engine.runner import run_finished_video
            threading.Thread(target=run_finished_video, args=(video_id,), name=f"v2-final-dispatch-{video_id[:8]}", daemon=True).start()
            dispatched = True
    attempt_id = _claim_next_export_attempt()
    if attempt_id:
        from server.v2_exporter.runner import start_attempt_in_background
        settings = service.get_v2_settings()
        start_attempt_in_background(service.connection, attempt_id=attempt_id, settings=settings)
        dispatched = True
    return dispatched


def _loop() -> None:
    last_cleanup = 0.0
    while not _STOP.wait(0.5):
        try:
            dispatch_once()
            if time.monotonic() - last_cleanup >= 30:
                service.run_due_cleanup()
                last_cleanup = time.monotonic()
        except Exception:
            # 单个任务的错误由 runner 写回任务；调度循环不能因一个任务退出。
            continue


def start_scheduler() -> None:
    global _STARTED
    with _START_LOCK:
        if _STARTED:
            return
        recovery_attempt_ids = _clear_stale_executor_claims()
        _STARTED = True
        if recovery_attempt_ids:
            from server.v2_exporter.runner import resume_passive_observation_in_background
            settings = service.get_v2_settings()
            for attempt_id in recovery_attempt_ids:
                resume_passive_observation_in_background(service.connection, attempt_id=attempt_id, settings=settings)
        threading.Thread(target=_loop, name="v2-task-center", daemon=True).start()


def _clear_stale_executor_claims() -> list[str]:
    """Recover passive output observation; fail only restart-interrupted UI work."""
    from server.executor_management import ExecutorManager
    conn = service.connection()
    try:
        # Only observation has a safe restart path: Jianying already accepted
        # the export and its exact source path was durably recorded.  It needs
        # no further UI control. Earlier UI phases cannot be safely guessed.
        conn.execute(
            "UPDATE export_attempts SET status='failed', error_code='WORKER_INTERRUPTED', "
            "error_message='服务重启时导出尚未取得剪映提交回执，请重新导出', finished_at=?, updated_at=? "
            "WHERE status IN ('preparing','awaiting_human_check','submitting','finalizing')",
            (service.now_text(), service.now_text()),
        )
        conn.execute(
            "UPDATE export_jobs SET status='failed', updated_at=? WHERE id IN "
            "(SELECT job_id FROM export_attempts WHERE status='failed' AND error_code='WORKER_INTERRUPTED')",
            (service.now_text(),),
        )
        conn.commit()
        manager = ExecutorManager(conn)
        # A generation process cannot survive a service restart. Put an
        # interrupted final generation back into the waiting queue so it can
        # be claimed again after the executor is resumed.
        conn.execute(
            "UPDATE production_video_tasks SET status='pending_generation', "
            "error_message='服务重启后已重新排队', started_at='', finished_at='', updated_at=? "
            "WHERE status='generating'",
            (service.now_text(),),
        )
        conn.commit()
        active = {
            "template_generator": {str(r[0]) for r in conn.execute("SELECT id FROM template_jobs WHERE status IN ('dispatching','running')")},
            "final_generator": {str(r[0]) for r in conn.execute("SELECT id FROM production_video_tasks WHERE status IN ('generation_queued','generating')")},
            "video_exporter": {str(r[0]) for r in conn.execute("SELECT id FROM export_attempts WHERE status IN ('preparing','awaiting_human_check','submitting','observing_output','finalizing')")},
        }
        for executor_id in ("template_generator", "final_generator", "video_exporter"):
            current = str(manager.state(executor_id).get("current_task_id") or "")
            if current and current not in active[executor_id]:
                manager.set_current_task(executor_id, None)
        return [str(row["id"]) for row in conn.execute(
            "SELECT id FROM export_attempts WHERE status='observing_output' AND source_output_path<>''"
        ).fetchall()]
    finally:
        conn.close()


def stop_scheduler() -> None:
    _STOP.set()


def set_queue_paused(paused: bool) -> None:
    global _PAUSED
    _PAUSED = bool(paused)
    from server.executor_management import EXECUTOR_IDS, ExecutorManager
    conn = service.connection()
    try:
        manager = ExecutorManager(conn)
        if paused:
            for executor_id in EXECUTOR_IDS:
                manager.request_pause(executor_id, reason="全局暂停")
        else:
            for executor_id in EXECUTOR_IDS:
                manager.resume_global_pause(executor_id)
    finally:
        conn.close()


def set_executor_paused(executor_id: str, paused: bool) -> dict[str, Any]:
    from server.executor_management import ExecutorManager
    conn = service.connection()
    try:
        manager = ExecutorManager(conn)
        return manager.request_pause(executor_id) if paused else manager.resume(executor_id)
    finally:
        conn.close()


def task_center_snapshot() -> dict[str, Any]:
    """Return the task-center view model; no Mock data is inserted."""
    conn = service.connection()
    try:
        rows = conn.execute(
            # INNER JOIN 而不是 LEFT JOIN：``production_tasks`` 行被删掉之后，挂在它
            # 下面的模板/成片/导出记录会变成**孤儿**，LEFT JOIN 会让它们的 ``t.*`` 全变
            # NULL，而 ``COALESCE(t.release_status,'unregistered')`` 恰好把 NULL 当成
            # "未登记发布"放行 —— 界面上就冒出「未知账号 ×《未知剧集》」的幽灵任务
            # （2026-09-19 实机发现：19 个组里有 10 个是这种幽灵）。
            "SELECT j.*, t.account_name, t.drama_name, t.planned_publish_at "
            "FROM template_jobs j JOIN production_tasks t ON t.id=j.task_id "
            "WHERE j.version_no=(SELECT MAX(latest.version_no) FROM template_jobs latest WHERE latest.task_id=j.task_id) "
            "AND COALESCE(t.release_status, 'unregistered') <> 'registered' "
            "ORDER BY j.created_at DESC, j.version_no DESC"
        ).fetchall()
    finally:
        conn.close()
    tasks = [_task_item(row) for row in rows]
    # Only the newest draft version is the editable business card, but an
    # older version may still be the currently accepted formal template video.
    # Keep that fact on the same card instead of emitting a second, duplicate
    # export card for the same production task.
    template_parent_by_task_id = {
        str(row["task_id"]): item
        for row, item in zip(rows, tasks)
        if str(row["task_id"] or "")
    }
    # The UI card represents one business flow. Keep draft/export records
    # independent in SQLite, but merge an export record into its parent card.
    by_id = {str(item["id"]): item for item in tasks}
    final_conn = service.connection()
    try:
        final_rows = final_conn.execute(
            "SELECT v.*, f.file_name AS material_file_name, f.sequence_no AS sequence_no, t.account_name, t.drama_name, "
            "t.planned_publish_at FROM production_video_tasks v "
            "JOIN production_tasks t ON t.id=v.task_id "
            "LEFT JOIN production_files f ON f.id=v.source_material_id "
            "WHERE v.status IN ('pending_generation','generation_queued','generating',"
            "'draft_ready','generation_failed','generation_timeout') "
            "AND COALESCE(t.release_status, 'unregistered') <> 'registered' "
            "ORDER BY CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, "
            "t.planned_publish_at, t.created_at, v.created_at"
        ).fetchall()
    finally:
        final_conn.close()
    final_items = [_final_task_item(row) for row in final_rows]
    by_id.update({str(item["id"]): item for item in final_items})
    tasks.extend(final_items)
    export_conn = service.connection()
    try:
        export_rows = export_conn.execute(
            "SELECT a.*, j.production_task_id, j.subject_type, j.subject_id, j.draft_name, j.draft_path, j.target_path, j.status AS job_status, t.account_name, t.drama_name, t.planned_publish_at "
            "FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id JOIN production_tasks t ON t.id=j.production_task_id "
            "WHERE a.attempt_no=(SELECT MAX(x.attempt_no) FROM export_attempts x WHERE x.job_id=a.job_id) "
            "AND COALESCE(t.release_status, 'unregistered') <> 'registered' "
            "AND (a.status <> 'completed' OR a.finished_at >= datetime('now', '-7 day')) "
            "ORDER BY a.created_at DESC"
        ).fetchall()
    finally:
        export_conn.close()
    standalone_exports: list[dict[str, Any]] = []
    for row in export_rows:
        export_item = _export_task_item(row)
        if str(row["subject_type"]) == "template":
            parent = template_parent_by_task_id.get(str(row["production_task_id"] or ""))
        else:
            parent = by_id.get(str(row["subject_id"]))
        if parent is None:
            standalone_exports.append(export_item)
            continue
        is_current_draft_version = str(row["subject_id"]) == str(parent["id"])
        # A completed export from any version proves that a formal video is
        # available.  It must not be hidden merely because a later R02/R03
        # attempt failed before it could replace the old formal file.
        if export_item["status"] == "done":
            parent["hasCompletedFirstExport"] = True
            parent["outputPath"] = export_item.get("outputPath")
            parent["fileSizeMb"] = export_item.get("fileSizeMb")
        if not is_current_draft_version:
            # 旧草稿版本可能仍在剪映中导出。此前这里直接跳过，会让
            # executor_controls.current_task_id 指向一个没有任务卡的导出尝试，
            # 执行器错误显示为“当前无执行中任务”。运行中或异常的旧版本
            # 导出必须以独立导出卡保留，供用户看到真实状态并在需要时重试。
            if export_item["status"] in {"running", "timeout", "error"}:
                standalone_exports.append(export_item)
            continue
        parent["videoStage"] = export_item["videoStage"]
        parent["videoExportTaskId"] = export_item["id"]
        parent["videoStage"]["durationSeconds"] = export_item.get("durationSeconds")
        parent["videoStage"]["durationFormatted"] = export_item.get("durationFormatted")
        # Preserve the draft stage as the primary stage unless export is
        # running/failed; the card then reflects the current pipeline step.
        if export_item["status"] in {"running", "timeout", "error"}:
            parent["status"] = export_item["status"]
            parent["progress"] = export_item["progress"]
            parent["startedAt"] = export_item.get("startedAt")
            parent["completedAt"] = export_item.get("completedAt")
            parent["durationSeconds"] = export_item.get("durationSeconds", 0)
            parent["durationFormatted"] = export_item.get("durationFormatted", "—")
            parent["isTimeout"] = export_item.get("isTimeout", False)
        elif export_item["status"] == "done" and parent["draftStage"]["status"] == "done":
            parent["status"] = "done"
            parent["progress"] = 100
    tasks.extend(standalone_exports)
    # 只隐藏已经登记发布的那一条生产任务。相同账号×剧集可能存在多
    # 条独立生产任务（例如不同日期），不能按业务名称整体过滤，否则
    # 未登记的异常/重试任务会被误隐藏。
    registered_conn = service.connection()
    try:
        columns = {str(row["name"]) for row in registered_conn.execute("PRAGMA table_info(production_tasks)").fetchall()}
        registered_task_ids: set[str] = set()
        if "release_status" in columns:
            registered_task_ids = {
                str(row["id"])
                for row in registered_conn.execute("SELECT id FROM production_tasks WHERE release_status='registered'").fetchall()
            }
    finally:
        registered_conn.close()
    if registered_task_ids:
        tasks = [item for item in tasks if str(item.get("productionTaskId") or "") not in registered_task_ids]
    # The list is a two-level business queue: current stage first, then the
    # production-unit priority and material sequence within that unit.
    status_order = {"running": 0, "timeout": 1, "error": 2, "waiting": 3, "done": 4}
    tasks.sort(key=lambda item: (
        status_order.get(str(item.get("status") or "waiting"), 3),
        int(item.get("priorityRank") or 0) if int(item.get("priorityRank") or 0) > 0 else 10**9,
        int(item.get("sequenceNo") or 0) if int(item.get("sequenceNo") or 0) > 0 else 10**9,
        str(item.get("createdAt") or ""),
        str(item.get("id") or ""),
    ))
    conn = service.connection()
    try:
        from server.executor_management import EXECUTOR_IDS, ExecutorManager
        manager = ExecutorManager(conn)
        executors = [_executor_snapshot(manager, executor_id, tasks) for executor_id in ("video_exporter", "final_generator", "template_generator")]
        drama_priorities = _drama_priorities(conn)
        # 手动排序位次：一次算清、贴到每张卡上。界面按它分组排序，
        # 三个执行器也按同一个数字取任务，两边不会打架。
        order_ranks = _unit_order_ranks(conn)
    finally:
        conn.close()
    for item in tasks:
        item["orderRank"] = order_ranks.get(str(item.get("productionTaskId") or ""), 0)
    return {
        "executors": executors,
        "tasks": tasks,
        "dramaPriorities": drama_priorities,
        "isQueuePaused": _PAUSED,
    }


def task_center_items_for_production_task(production_task_id: str) -> dict[str, Any]:
    """Return only the task cards belonging to one account × drama unit.

    The card-merging policy remains centralised in ``task_center_snapshot``;
    this endpoint deliberately exposes only the changed unit to the browser.
    """
    snapshot = task_center_snapshot()
    return {"items": [item for item in snapshot["tasks"] if str(item.get("productionTaskId") or "") == production_task_id]}


def _drama_priorities(conn: Any) -> list[dict[str, Any]]:
    """Return the real account × drama production order for the banner.

    The banner deliberately counts draft-production units only: the current
    template draft plus each finished-video draft. Export attempts are their
    own later phase and must not inflate a drama's production count.
    """
    columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_tasks)").fetchall()}
    release_filter = " AND COALESCE(t.release_status, 'unregistered') <> 'registered'" if "release_status" in columns else ""
    rows = conn.execute(
        "SELECT t.id, t.account_name, t.drama_name, t.planned_publish_at, t.created_at, "
        "(SELECT j.status FROM template_jobs j WHERE j.task_id=t.id "
        " ORDER BY j.version_no DESC LIMIT 1) AS latest_template_status, "
        "COUNT(v.id) AS final_total, "
        "COALESCE(SUM(CASE WHEN v.status='draft_ready' THEN 1 ELSE 0 END), 0) AS final_completed "
        "FROM production_tasks t "
        "LEFT JOIN production_video_tasks v ON v.task_id=t.id "
        "WHERE (EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=t.id) "
        "   OR EXISTS (SELECT 1 FROM production_video_tasks x WHERE x.task_id=t.id)) "
        + release_filter + " "
        "GROUP BY t.id "
        "ORDER BY CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, "
        "t.planned_publish_at, t.created_at"
    ).fetchall()
    priorities: list[dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        has_template = bool(str(row["latest_template_status"] or ""))
        total_tasks = int(row["final_total"] or 0) + int(has_template)
        completed_tasks = int(row["final_completed"] or 0) + int(str(row["latest_template_status"] or "") == "draft_ready")
        planned_publish_at = str(row["planned_publish_at"] or "")
        priorities.append({
            "productionTaskId": str(row["id"]),
            "accountName": str(row["account_name"] or "未知账号"),
            "dramaName": str(row["drama_name"]),
            "scheduledPublishTime": _priority_time_label(planned_publish_at),
            "priorityRank": rank,
            "startedAt": str(row["created_at"]),
            "totalTasks": total_tasks,
            "completedTasks": completed_tasks,
        })
    return priorities


def _priority_time_label(planned_publish_at: str) -> str:
    """Keep the compact clock label expected by the existing banner UI."""
    normalized = planned_publish_at.replace("T", " ")
    return normalized[11:16] if len(normalized) >= 16 else (planned_publish_at or "未设置")


def _executor_snapshot(manager: Any, executor_id: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
    state = manager.state(executor_id)
    # A template/final card is a business-flow card, not an executor record.
    # Once its video stage exists it must be counted by the video exporter,
    # while its completed draft remains visible in its own generator history.
    # Counting the merged card by ``executorId`` alone made an export timeout
    # appear as a "模板生成器超时" and hid the exporter queue statistics.
    executor_tasks = _executor_stage_items(executor_id, tasks)
    running = sum(1 for item in executor_tasks if item["status"] == "running")
    waiting = sum(1 for item in executor_tasks if item["status"] == "waiting")
    completed = sum(1 for item in executor_tasks if item["status"] == "done")
    timeout = sum(1 for item in executor_tasks if item["status"] == "timeout")
    control_state = str(state.get("control_state") or "idle")
    if control_state in {"manual_paused", "error_paused", "pausing"}:
        status = control_state
    elif str(state.get("current_task_id") or ""):
        status = "running"
    elif waiting:
        status = "waiting"
    else:
        status = "idle"
    names = {
        "video_exporter": ("视频导出器", "CapCut / 剪映视频渲染", "单任务串行导出；模板视频优先"),
        "final_generator": ("成片生成器", "成片剪映工程草稿装配", "单任务串行生成，按账号×剧集优先级调度"),
        "template_generator": ("模板生成器", "通用分镜与视觉模板草稿", "单任务串行生成，完成后进入视频导出"),
    }
    name, subtitle, description = names[executor_id]
    timeout_keys = {
        "template_generator": "template_timeout_min",
        "final_generator": "final_generation_timeout_min",
        "video_exporter": "video_export_timeout_min",
    }
    settings = service.get_v2_settings()
    try:
        timeout_threshold = max(1, int(settings.get(timeout_keys[executor_id], 0))) * 60
    except (KeyError, TypeError, ValueError):
        timeout_threshold = 0
    return {
        "id": executor_id, "name": name, "subtitle": subtitle, "description": description,
        "status": status, "controlState": control_state, "pauseRequested": bool(state.get("pause_requested")),
        "pauseReason": str(state.get("pause_reason") or ""), "consecutiveFailures": int(state.get("consecutive_failures") or 0),
        "lastErrorMessage": str(state.get("last_error_message") or ""),
        "currentTaskId": str(state.get("current_task_id") or "") or None, "runningSeconds": 0,
        "isTimeout": bool(timeout), "timeoutThresholdSeconds": timeout_threshold,
        "queueStats": {"completed": completed, "running": running, "waiting": waiting, "total": len(executor_tasks), "timeoutCount": timeout},
    }


def _executor_stage_items(executor_id: str, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the stage owned by one executor, with its own status only."""
    if executor_id == "video_exporter":
        result: list[dict[str, Any]] = []
        for item in tasks:
            video = item.get("videoStage") or {}
            # ``rawStatus`` exists only after a real export attempt has been
            # created.  An idle video stage is merely a placeholder.
            if not video.get("rawStatus"):
                continue
            result.append({"task": item, "status": str(video.get("status") or "waiting")})
        return result
    result = []
    for item in tasks:
        if item.get("executorId") != executor_id:
            continue
        draft = item.get("draftStage") or {}
        result.append({"task": item, "status": str(draft.get("status") or "waiting")})
    return result


def _export_task_item(row: Any) -> dict[str, Any]:
    raw = str(row["status"])
    status = "running" if raw in {"preparing", "awaiting_human_check", "submitting", "observing_output", "finalizing"} else "waiting" if raw == "queued" else "done" if raw == "completed" else "timeout" if "TIMEOUT" in str(row["error_code"] or "") else "error"
    subject = "模板视频导出" if str(row["subject_type"]) == "template" else "成片视频导出"
    raw_error = str(row["error_message"] or "")
    detail = _user_facing_error_detail(raw_error)
    stage_labels = {
        "preparing": "准备打开剪映草稿",
        "awaiting_human_check": "等待人工检查草稿",
        "submitting": "正在提交剪映导出",
        "observing_output": "剪映已提交，等待输出文件",
        "finalizing": "正在验收导出文件",
    }
    duration_seconds, duration_formatted = _format_duration(str(row["started_at"] or ""), str(row["finished_at"] or ""))
    return {
        "id": str(row["id"]), "productionTaskId": str(row["production_task_id"] or ""), "taskCategory": "template" if str(row["subject_type"]) == "template" else "final_video",
        "accountName": str(row["account_name"] or "未知账号"), "dramaName": str(row["drama_name"] or "未知剧集"),
        "title": f"{row['account_name'] or '未知账号'} × 《{row['drama_name'] or '未知剧集'}》 · {subject}",
        "draftStage": {"status": "done", "progress": 100}, "videoStage": {"status": status, "rawStatus": raw, "progress": 100 if status == "done" else 0, "durationSeconds": duration_seconds, "durationFormatted": duration_formatted, "errorDetail": detail},
        "scheduledPublishTime": str(row["planned_publish_at"] or ""), "priorityRank": _production_priority_rank(row), "priorityTag": "模板优先" if str(row["subject_type"]) == "template" else "成片导出",
        "status": status, "progress": 100 if status == "done" else 0, "createdAt": str(row["created_at"]),
        "startedAt": str(row["started_at"] or "") or None, "completedAt": str(row["finished_at"] or "") or None,
        "durationSeconds": duration_seconds, "durationFormatted": duration_formatted, "isTimeout": status == "timeout", "hasValidDraft": True,
        "hasCompletedFirstExport": status == "done", "taskType": "video_export", "taskSubType": "template_video_export" if str(row["subject_type"]) == "template" else "final_video_export",
        "executorId": "video_exporter", "executorName": "视频导出器", "draftPath": str(row["draft_path"] or "") or None,
        "outputPath": str(row["target_path"] or "") or None, "fileSizeMb": (Path(str(row["target_path"])).stat().st_size / 1024 / 1024 if Path(str(row["target_path"] or "")).is_file() else 0), "errorDetail": detail, "diagnosticLog": _executor_diagnostic(str(row["id"]), raw_error),
        "stageInfo": {"currentStage": stage_labels.get(raw, "视频导出"), "stepIndex": 3, "totalSteps": 3} if status == "running" else None,
    }


def _final_task_item(row: Any) -> dict[str, Any]:
    raw = str(row["status"] or "")
    if raw in {"pending_generation", "generation_queued"}:
        overall, draft_status, progress = "waiting", "waiting", 0
    elif raw == "generating":
        overall, draft_status, progress = "running", "running", 20
    elif raw == "draft_ready":
        overall, draft_status, progress = "waiting", "done", 60
    elif raw == "generation_timeout":
        overall, draft_status, progress = "timeout", "timeout", 0
    else:
        overall, draft_status, progress = "error", "error", 0
    started_at = str(row["started_at"] or "")
    finished_at = str(row["finished_at"] or "")
    duration_seconds, duration_formatted = _format_duration(started_at, finished_at)
    raw_error = str(row["error_message"] or "")
    error = _user_facing_error_detail(raw_error)
    material_name = str(row["material_file_name"] or "") or None
    return {
        "id": str(row["id"]), "productionTaskId": str(row["task_id"] or ""), "taskCategory": "final_video",
        "accountName": str(row["account_name"] or "未知账号"), "dramaName": str(row["drama_name"] or "未知剧集"),
        "materialName": material_name, "materialFullName": material_name,
        "title": f"{row['account_name'] or '未知账号'} × 《{row['drama_name'] or '未知剧集'}》 · 成片制作",
        "draftStage": {"status": draft_status, "progress": progress, "durationSeconds": duration_seconds, "durationFormatted": duration_formatted, "errorDetail": error or None},
        "videoStage": {"status": "idle", "progress": 0},
        "scheduledPublishTime": str(row["planned_publish_at"] or ""), "priorityRank": _production_priority_rank(row), "priorityTag": "成片制作",
        "status": overall, "progress": progress, "createdAt": str(row["created_at"]),
        "startedAt": started_at or None, "completedAt": finished_at or None,
        "durationSeconds": duration_seconds, "durationFormatted": duration_formatted,
        "draftDurationSeconds": duration_seconds, "draftDurationFormatted": duration_formatted,
        "isTimeout": raw == "generation_timeout", "hasValidDraft": raw == "draft_ready" and bool(str(row["draft_path"] or "")),
        "hasCompletedFirstExport": False, "taskType": "final_draft", "executorId": "final_generator", "executorName": "成片生成器",
        "isOrphan": False, "draftPath": str(row["draft_path"] or "") or None, "outputPath": str(row["output_path"] or "") or None,
        "diagnosticLog": _executor_diagnostic(str(row["id"]), raw_error), "errorDetail": error, "sequenceNo": int(row["sequence_no"] or 0) if row["sequence_no"] is not None else None,
    }


# 「账号 × 剧集」单位的排序键。手动顺序与显示顺序必须**用同一个函数**算，
# 否则界面显示的位次和实际取任务的顺序会不一致（"手动排序 = 最高调度优先"就落空了）。
MANUAL_ORDER_FIRST_SQL = "CASE WHEN t.manual_order > 0 THEN 0 ELSE 1 END, t.manual_order, "
_DEFAULT_UNIT_ORDER = (
    "CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at"
)


def _manual_order_key(conn: Any) -> str:
    """手动位次的排序键；列还不存在的库（旧库首次连接、测试用的精简表）自动降级为不排序。

    这不是为了兼容测试而妥协：真实数据库的列由 ``v2_file_service`` 的 DDL 迁移补上，
    但迁移发生在**第一次建立连接**时，而调度循环和快照都可能先跑那一步。
    """
    try:
        columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_tasks)").fetchall()}
    except Exception:  # noqa: BLE001
        return ""
    return MANUAL_ORDER_FIRST_SQL if "manual_order" in columns else ""


def _unit_is_complete(conn: Any, task_id: str) -> bool:
    """全部已提交成片都导出完成，且没有草稿/视频异常 → 这部剧做完了。"""
    row = conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id "
        " AND v.status NOT IN ('cancelled','cancellation_requested','invalidated')) AS total, "
        "(SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id "
        " AND v.status IN ('generation_failed','generation_timeout')) AS draft_bad, "
        "(SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id "
        " AND (SELECT a.status FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id "
        "      WHERE j.subject_type='final' AND j.subject_id=v.id "
        "      ORDER BY a.attempt_no DESC LIMIT 1) = 'completed') AS exported "
        "FROM production_tasks t WHERE t.id=?",
        (task_id,),
    ).fetchone()
    if row is None:
        return False
    total = int(row["total"] or 0)
    return total > 0 and int(row["exported"] or 0) == total and int(row["draft_bad"] or 0) == 0


def _ordered_units(conn: Any) -> tuple[list[str], list[str]]:
    """返回 (显示顺序, 未完成单位的顺序)。

    显示顺序规则（2026-09-19 用户拍板）：
      1. 已做完的整部剧沉到最后
      2. 手动调过的按 manual_order 从小到大
      3. 没调过的按业务规则：计划发布时间早 → 开工时间早

    手动调整只在**未完成**的单位之间进行 —— 已完成的根本不需要排优先级，
    让它们参与手动排序会让用户点了"置顶"却看不到任何变化。
    """
    rows = conn.execute(
        "SELECT t.id, t.manual_order, t.planned_publish_at, t.created_at FROM production_tasks t "
        "WHERE (EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=t.id) "
        "   OR EXISTS (SELECT 1 FROM production_video_tasks v WHERE v.task_id=t.id)) "
        "AND COALESCE(t.release_status, 'unregistered') <> 'registered'"
    ).fetchall()
    incomplete: list[tuple[int, str, str, str]] = []
    complete: list[tuple[str, str, str]] = []
    for row in rows:
        planned = str(row["planned_publish_at"] or "") or "9999-12-31"
        created = str(row["created_at"] or "")
        task_id = str(row["id"])
        if _unit_is_complete(conn, task_id):
            complete.append((planned, created, task_id))
            continue
        manual = int(row["manual_order"] or 0)
        incomplete.append((manual if manual > 0 else 10**9, planned, created, task_id))
    incomplete.sort()
    complete.sort()
    active_order = [item[3] for item in incomplete]
    return active_order + [item[2] for item in complete], active_order


def _ordered_unit_ids(conn: Any) -> list[str]:
    """当前「账号 × 剧集」的完整显示顺序。"""
    return _ordered_units(conn)[0]


def _unit_order_ranks(conn: Any) -> dict[str, int]:
    global _ORDER_CACHE
    now = time.monotonic()
    with _ORDER_CACHE_LOCK:
        if now - _ORDER_CACHE[0] < 2 and _ORDER_CACHE[1]:
            return _ORDER_CACHE[1]
    ranks = {task_id: index for index, task_id in enumerate(_ordered_unit_ids(conn), start=1)}
    with _ORDER_CACHE_LOCK:
        _ORDER_CACHE = (now, ranks)
    return ranks


def task_center_reorder(production_task_id: str, action: str) -> dict[str, Any]:
    """手动调整一个「账号 × 剧集」的生产顺序。

    action：``top`` 置顶 / ``up`` 上移一位 / ``down`` 下移一位。

    首次调整时把**所有未完成单位**的位次一次性落库（materialize），之后调整只改数字。
    这样"界面显示第几 = 执行器第几个做"永远成立，不会出现界面第一、实际最后跑。
    """
    if action not in {"top", "up", "down"}:
        raise ValueError("排序动作只能是 top、up 或 down")
    conn = service.connection()
    try:
        _, active_order = _ordered_units(conn)
        if production_task_id not in active_order:
            # 整部剧已完成（或不属于任何在做任务）：它已经沉底，不需要也不该占手动位次。
            raise ValueError("这部剧已经做完了，不需要调整顺序（已完成的会自动沉到列表最后）")
        index = active_order.index(production_task_id)
        if action == "top":
            target = 0
        elif action == "up":
            target = max(0, index - 1)
        else:
            target = min(len(active_order) - 1, index + 1)
        if target != index:
            active_order.pop(index)
            active_order.insert(target, production_task_id)
        # 把未完成单位的位次整份重写：位次 = 显示顺序 = 执行器取任务顺序。
        # 只写未登记发布的那些行 —— 历史任务不该被这次调整碰到。
        stamp = service.now_text()
        for position, task_id in enumerate(active_order, start=1):
            conn.execute(
                "UPDATE production_tasks SET manual_order=?, updated_at=? WHERE id=? "
                "AND COALESCE(release_status, 'unregistered') <> 'registered'",
                (position, stamp, task_id),
            )
        conn.commit()
        global _ORDER_CACHE
        with _ORDER_CACHE_LOCK:
            _ORDER_CACHE = (0.0, {})
        return {"order": _ordered_unit_ids(conn)}
    finally:
        conn.close()


def _production_priority_rank(row: Any) -> int:
    global _PRIORITY_CACHE
    now = time.monotonic()
    if now - _PRIORITY_CACHE[0] < 2:
        target_id = row["task_id"] if "task_id" in row.keys() else row["production_task_id"]
        return _PRIORITY_CACHE[1].get(str(target_id), 0)
    conn = service.connection()
    try:
        rows = conn.execute(
            "SELECT t.id FROM production_tasks t WHERE EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=t.id) OR EXISTS (SELECT 1 FROM production_video_tasks v WHERE v.task_id=t.id) "
            "ORDER BY CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at"
        ).fetchall()
        ranks = {str(candidate["id"]): rank for rank, candidate in enumerate(rows, start=1)}
        _PRIORITY_CACHE = (now, ranks)
        target_id = row["task_id"] if "task_id" in row.keys() else row["production_task_id"]
        for rank, candidate in enumerate(rows, start=1):
            if str(candidate["id"]) == str(target_id):
                return rank
    finally:
        conn.close()
    return 0


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
    raw_error = str(row["error_message"] or "")
    error = _user_facing_error_detail(raw_error)
    duration_seconds, duration_formatted = _format_duration(str(row["started_at"] or ""), str(row["finished_at"] or ""))
    return {
        "id": str(row["id"]), "productionTaskId": str(row["task_id"] or ""), "taskCategory": "template", "accountName": str(row["account_name"] or "未知账号"),
        "dramaName": str(row["drama_name"] or "未知剧集"), "title": f"{row['account_name'] or '未知账号'} × 《{row['drama_name'] or '未知剧集'}》 · 模板制作",
        "draftStage": {"status": draft_status, "progress": progress, "durationSeconds": duration_seconds, "durationFormatted": duration_formatted, "errorDetail": error or None},
        "videoStage": {"status": "idle", "progress": 0}, "scheduledPublishTime": str(row["planned_publish_at"] or ""),
        "priorityRank": _production_priority_rank(row), "priorityTag": "模板任务", "status": overall, "progress": progress,
        "createdAt": str(row["created_at"]), "startedAt": str(row["started_at"] or "") or None,
        "completedAt": str(row["finished_at"] or "") or None, "durationSeconds": duration_seconds, "durationFormatted": duration_formatted,
        "draftDurationSeconds": duration_seconds, "draftDurationFormatted": duration_formatted,
        "isTimeout": is_timeout, "hasValidDraft": raw == "draft_ready", "hasCompletedFirstExport": False,
        "taskType": "template_draft", "executorId": "template_generator", "executorName": "模板生成器",
        "isOrphan": row["task_id"] is not None and row["account_name"] is None,
        "draftPath": str(row["draft_path"] or "") or None, "diagnosticLog": _executor_diagnostic(str(row["id"]), raw_error) or str(row["log_path"] or "") or None,
        "errorDetail": error,
    }
