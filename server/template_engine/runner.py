"""V2 模板草稿执行器。

排队接口只负责领取资源和写入任务；本模块负责单独执行一个任务，写回
状态和结果。它不启动剪映，也不接触 V1 数据库。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

try:
    from server import v2_file_service as service
except ModuleNotFoundError:  # 支持直接执行 server/v2_file_service.py 的开发入口
    import v2_file_service as service  # type: ignore[no-redef]
from server.runtime_process import no_window_kwargs, worker_command


RUN_LOCK = threading.Lock()
PROCESS_LOCK = threading.Lock()
RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_LOG_TAIL_LIMIT = 64 * 1024


def _write_log_tail(path: Path, stdout: str | None, stderr: str | None) -> None:
    """Keep diagnostics useful without allowing one worker to create an unlimited log."""
    text = (stdout or "") + ("\n" + stderr if stderr else "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text[-_LOG_TAIL_LIMIT:], encoding="utf-8")


def _worker_trace_entries(path: Path) -> list[tuple[str, str, str | None]]:
    try:
        entries: list[tuple[str, str, str | None]] = []
        for line in path.read_text(encoding="utf-8")[-65536:].splitlines():
            payload = json.loads(line)
            if payload.get("phase") and payload.get("message"):
                occurred_at = payload.get("occurred_at")
                entries.append((str(payload["phase"]), str(payload["message"]),
                                str(occurred_at) if occurred_at else None))
        return entries
    except (OSError, json.JSONDecodeError):
        return []


def _start_heartbeat(*, job_id: str, task_id: str, stop: threading.Event, worker_trace: Path) -> threading.Thread:
    def heartbeat() -> None:
        seen = 0
        idle_seconds = 0
        while not stop.wait(2):
            entries = _worker_trace_entries(worker_trace)
            if len(entries) > seen:
                for phase, message, occurred_at in entries[seen:]:
                    service.record_executor_trace(executor_id="template_generator", run_id=job_id,
                                                  production_task_id=task_id, phase=phase, message=message,
                                                  created_at=occurred_at)
                seen = len(entries)
                idle_seconds = 0
                continue
            idle_seconds += 2
            if idle_seconds >= 10:
                service.record_executor_trace(executor_id="template_generator", run_id=job_id,
                                              production_task_id=task_id, phase="等待模板草稿生成",
                                              message="子程序仍在运行，等待当前步骤完成")
                idle_seconds = 0
    thread = threading.Thread(target=heartbeat, name=f"v2-template-trace-{job_id[:8]}", daemon=True)
    thread.start()
    return thread


def _set_job(job_id: str, *, status: str, **fields: str) -> None:
    conn = service.connection()
    try:
        values = {"status": status, "updated_at": service.now_text(), **fields}
        assignments = ", ".join(f"{key}=?" for key in values)
        conn.execute(f"UPDATE template_jobs SET {assignments} WHERE id=?", (*values.values(), job_id))
        conn.commit()
    finally:
        conn.close()


def _restore_reserved(reserved_json: str) -> None:
    for item in json.loads(reserved_json or "[]"):
        original = Path(str(item.get("original_path") or ""))
        reserved = Path(str(item.get("reserved_path") or ""))
        if reserved.is_file() and not original.exists():
            reserved.rename(original)


def _pairing_payload(decision: dict[str, object], draft_path: Path) -> dict[str, object]:
    track = decision.get("track01") or {}
    return {
        "schema_version": 1,
        "kind": "v2_template_pairing",
        "draft_path": str(draft_path),
        "canvas": {"width": 1080, "height": 2400},
        "central_window": {
            "width_ratio": track.get("canvas_width_ratio"),
            "height_ratio": track.get("canvas_height_ratio"),
            "mask_width_material": track.get("mask_width_material"),
            "mask_height_material": track.get("mask_height_material"),
            "feather": track.get("feather"),
        },
    }


def run_template_job(job_id: str) -> None:
    """Execute one queued job; every failure is converted to a Chinese message."""
    with RUN_LOCK:
        conn = service.connection()
        try:
            row = conn.execute(
                "SELECT j.*, t.created_date, t.material_path, t.template_path, t.account_name, t.drama_name "
                "FROM template_jobs j JOIN production_tasks t ON t.id=j.task_id WHERE j.id=?", (job_id,)
            ).fetchone()
        finally:
            conn.close()
        if not row or str(row["status"]) not in {"queued", "dispatching"}:
            return

        task_id = str(row["task_id"])
        service.clear_executor_trace(job_id)
        service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                      phase="开始", message="已领取模板任务，正在检查剪映和素材条件")

        from server.jianying_preflight import require_jianying_ready
        from server.jianying_runtime_paths import resolve_jianying_runtime_paths
        try:
            settings = service.get_v2_settings()
            require_jianying_ready(settings)
            runtime_paths = resolve_jianying_runtime_paths(settings)
        except Exception as exc:
            service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                          phase="剪映检查失败", message=str(exc))
            _fail(job_id, row, str(exc))
            return
        service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                      phase="剪映检查完成", message="剪映环境和草稿目录检查通过")
        _set_job(job_id, status="running", started_at=service.now_text())
        attempt_root = Path(str(row["template_path"])) / f"R{int(row['version_no']):02d}"
        photos = attempt_root / "模板剧照缓存"
        photo_cache = attempt_root / "照片缓存"
        draft_root = runtime_paths.draft_root
        draft_path = draft_root / str(row["draft_name"])
        reserved = json.loads(str(row["reserved_videos_json"] or "[]"))
        videos = [Path(str(item.get("reserved_path") or "")) for item in reserved]
        if len(videos) != 3 or any(not path.is_file() for path in videos):
            service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                          phase="素材检查失败", message="已领取的真人视频不完整")
            _fail(job_id, row, "模板生成所领取的真人视频不存在，任务已释放")
            return

        command = worker_command("server.template_engine.generate_v2_template", Path(__file__).with_name("generate_v2_template.py"), [
            "--stage", "final", "--seed", str(row["seed"]), "--draft-root", str(draft_root),
            "--name", str(row["draft_name"]), "--video", str(videos[0]), "--video-2", str(videos[1]),
            "--video-3", str(videos[2]), "--viral-account-day-dir", str(row["material_path"]),
            "--photo-prep-output-dir", str(photos), "--photo-cache-root", str(photo_cache),
            "--user-data-root", str(runtime_paths.user_data_root),
        ])
        worker_trace = attempt_root / "执行过程.jsonl"
        worker_trace.unlink(missing_ok=True)
        command.extend(["--trace-path", str(worker_trace)])
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = os.pathsep.join((str(Path(__file__).parents[1]), str(Path(__file__).parents[2]), env.get("PYTHONPATH", "")))
        timeout = int(service.get_v2_settings().get("template_timeout_min", 15)) * 60
        process: subprocess.Popen[str] | None = None
        heartbeat_stop = threading.Event()
        try:
            process = subprocess.Popen(command, cwd=str(Path(__file__).parent), stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=env,
                                       **no_window_kwargs())
            with PROCESS_LOCK:
                RUNNING_PROCESSES[job_id] = process
            service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                          phase="模板生成中", message="模板生成子程序已启动", detail={"pid": process.pid})
            _start_heartbeat(job_id=job_id, task_id=task_id, stop=heartbeat_stop, worker_trace=worker_trace)
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                _write_log_tail(Path(str(row["log_path"])), stdout, stderr)
                service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                              phase="超时", message="模板生成子程序超过限定时间仍未结束", detail={"pid": process.pid})
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
            with PROCESS_LOCK:
                RUNNING_PROCESSES.pop(job_id, None)
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            _write_log_tail(Path(str(row["log_path"])), result.stdout, result.stderr)
            if result.returncode != 0:
                if _is_retry_requested(job_id):
                    _requeue_after_retry(job_id, row)
                    return
                raise RuntimeError((result.stderr or result.stdout or "模板生成器退出失败").strip().splitlines()[-1])
            payload = json.loads((result.stdout or "").strip().splitlines()[-1])
            content_path = draft_path / "draft_content.json"
            if not content_path.is_file():
                raise RuntimeError("模板生成器返回成功，但未找到剪映草稿文件")
            report_path = Path(str(row["report_path"]))
            report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            decision = payload.get("templateDecision") or {}
            pairing_path = Path(str(row["template_path"])) / f"{service.template_stem(row)}-配对参数.json"
            pairing_path.write_text(json.dumps(_pairing_payload(decision, draft_path), ensure_ascii=False, indent=2), encoding="utf-8")
            _set_job(job_id, status="draft_ready", draft_path=str(draft_path), pairing_path=str(pairing_path), finished_at=service.now_text(), error_message="")
            # A ready template automatically becomes a queued template-video export.
            # The export job is idempotent per template version.
            service.ensure_export_job_for_template(row, draft_path=draft_path)
            service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                          phase="完成", message="模板草稿已生成并进入后续导出队列")
            _report_executor("completed")
        except subprocess.TimeoutExpired:
            if _is_retry_requested(job_id):
                _requeue_after_retry(job_id, row)
                return
            _fail(job_id, row, f"模板生成超过{timeout // 60}分钟仍未完成，任务已标记超时", status="timeout")
        except Exception as exc:  # noqa: BLE001
            if _is_retry_requested(job_id):
                _requeue_after_retry(job_id, row)
                return
            service.record_executor_trace(executor_id="template_generator", run_id=job_id, production_task_id=task_id,
                                          phase="失败", message=str(exc))
            _fail(job_id, row, f"模板生成失败：{exc}")
        finally:
            heartbeat_stop.set()
            with PROCESS_LOCK:
                RUNNING_PROCESSES.pop(job_id, None)


def _fail(job_id: str, row: object, message: str, *, status: str = "error") -> None:
    try:
        _restore_reserved(str(row["reserved_videos_json"]))  # type: ignore[index]
        # 失败尝试的缓存和未完成草稿不属于可复用结果；保留日志和错误记录。
        attempt_root = Path(str(row["template_path"])) / f"R{int(row['version_no']):02d}"  # type: ignore[index]
        for child_name in ("模板剧照缓存", "照片缓存"):
            shutil.rmtree(attempt_root / child_name, ignore_errors=True)
        draft_path = Path(str(row["draft_path"] or ""))  # type: ignore[index]
        if draft_path and draft_path.name and draft_path.exists():
            shutil.rmtree(draft_path, ignore_errors=True)
    finally:
        _set_job(job_id, status=status, error_message=message, finished_at=service.now_text())
        _report_executor("timed_out" if status == "timeout" else "failed", message)


def _is_retry_requested(job_id: str) -> bool:
    conn = service.connection()
    try:
        row = conn.execute("SELECT status FROM template_jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and str(row["status"]) == "retry_requested")
    finally:
        conn.close()


def _requeue_after_retry(job_id: str, row: object) -> None:
    """Clean the interrupted attempt, then reuse its version for a fresh run."""
    _fail(job_id, row, "人工重试：已停止当前执行并重新排队", status="error")
    service.queue_template_job(str(row["task_id"]), retry=True)  # type: ignore[index]


def _report_executor(outcome: str, message: str = "") -> None:
    """Release this executor and apply the shared failure policy."""
    conn = service.connection()
    try:
        from server.executor_management import ExecutorManager
        manager = ExecutorManager(conn)
        manager.report_result("template_generator", outcome=outcome)
        if message:
            conn.execute("UPDATE executor_controls SET last_error_message=? WHERE executor_id=?", (message, "template_generator"))
            conn.commit()
    finally:
        conn.close()


def request_retry(job_id: str) -> dict[str, object]:
    """Stop or reset one V2 template job and queue it again."""
    conn = service.connection()
    try:
        row = conn.execute("SELECT * FROM template_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("模板任务不存在")
    status = str(row["status"])
    if status in {"queued", "dispatching"}:
        _fail(job_id, row, "人工重试：原任务已取消并重新排队", status="error")
        return service.queue_template_job(str(row["task_id"]), retry=True)
    if status not in {"running", "error", "timeout", "retry_requested"}:
        raise ValueError("当前任务状态不支持重试")
    with PROCESS_LOCK:
        process = RUNNING_PROCESSES.get(job_id)
    if process and process.poll() is None:
        conn = service.connection()
        try:
            conn.execute("UPDATE template_jobs SET status='retry_requested', error_message=?, updated_at=? WHERE id=?",
                         ("人工重试：正在停止当前执行", service.now_text(), job_id))
            conn.commit()
        finally:
            conn.close()
        process.terminate()
        return {"id": job_id, "task_id": str(row["task_id"]), "status": "retry_requested"}
    _fail(job_id, row, "人工重试：原任务已清理并重新排队", status="error")
    return service.queue_template_job(str(row["task_id"]), retry=True)
