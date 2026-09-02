"""One real V2 export attempt.  No V1 worker/session/queue is used here."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from server.executor_management import ExecutorManager
from server.runtime_process import com_initialized
from server.v2_exporter.core import AttemptCoordinator, AttemptStatus, ExportRepository, MemoryInputLease
from server.v2_exporter.runtime import (Jianying59Bridge, V2ExportFailure, WindowsInputLease, draft_duration_seconds,
                                        safe_move_verified_output, verify_media, wait_for_stable_new_file)


_MANUAL_DRAFT_OPEN_LOCK = threading.Lock()


def start_manual_draft_open_in_background(connection_factory, *, video_id: str, draft_name: str, draft_path: Path,
                                          settings: dict[str, object]) -> threading.Thread:
    """Open one final draft for editing without entering the export workflow."""
    from server.jianying_preflight import require_jianying_ready
    require_jianying_ready(settings)
    if not _MANUAL_DRAFT_OPEN_LOCK.acquire(blocking=False):
        raise ValueError("已有草稿正在打开，请等待当前操作完成")

    def target() -> None:
        operation_id = f"manual-open-{video_id}"
        with com_initialized():
            lease = WindowsInputLease(maximum_seconds=90)
            try:
                lease.acquire(operation_id)
                bridge = Jianying59Bridge(lease, operation_id, executable=str(settings.get("jianying_executable") or ""))
                bridge.ensure_started()
                bridge.recover_and_open(draft_name)
            finally:
                try:
                    lease.release(operation_id)
                finally:
                    _MANUAL_DRAFT_OPEN_LOCK.release()

    thread = threading.Thread(target=target, name=f"v2-manual-draft-open-{video_id[:8]}", daemon=True)
    thread.start()
    return thread

def start_manual_template_draft_open_in_background(*, draft_name: str, settings: dict[str, object]) -> threading.Thread:
    from server.jianying_preflight import require_jianying_ready
    require_jianying_ready(settings)
    if not _MANUAL_DRAFT_OPEN_LOCK.acquire(blocking=False):
        raise ValueError("已有草稿正在打开，请等待当前操作完成")
    def target() -> None:
        operation_id = f"manual-open-template-{int(time.time() * 1000)}"
        with com_initialized():
            lease = WindowsInputLease(maximum_seconds=90)
            try:
                lease.acquire(operation_id)
                bridge = Jianying59Bridge(lease, operation_id, executable=str(settings.get("jianying_executable") or ""))
                bridge.ensure_started()
                bridge.recover_and_open(draft_name)
            finally:
                try: lease.release(operation_id)
                finally: _MANUAL_DRAFT_OPEN_LOCK.release()
    thread = threading.Thread(target=target, name="v2-manual-template-draft-open", daemon=True)
    thread.start()
    return thread


class V2ExportRunner:
    def __init__(self, connection, *, settings: dict[str, object]) -> None:
        self.connection, self.settings = connection, settings
        self.repository = ExportRepository(connection)

    def run(self, attempt_id: str, *, wait_for_enter: callable | None = None) -> dict[str, Any]:
        # The serial queue may keep a task waiting behind earlier exports.
        # Start its configured timeout only when this worker really receives
        # the task, not when the user placed it in the queue.
        from server.jianying_preflight import require_jianying_ready
        require_jianying_ready(self.settings)
        attempt = self.repository.activate_attempt_deadline(attempt_id)
        job = self.repository.job_for_attempt(attempt_id)
        deadline = _deadline_timestamp(str(attempt["deadline_at"]))
        lease = WindowsInputLease(maximum_seconds=max(1.0, deadline - time.time()))
        coordinator = AttemptCoordinator(self.repository, lease)
        bridge = Jianying59Bridge(lease, attempt_id, executable=str(self.settings.get("jianying_executable") or ""), debug_sink=self._debug_sink(attempt_id) if bool(attempt["debug_enabled"]) else None)
        try:
            coordinator.begin(attempt_id)
            bridge.ensure_started()
            # Match V1's fast handoff: finish local draft reading before the
            # editor button becomes actionable, then open the draft and click
            # its already-confirmed Export button without a V2-only gap.
            expected_duration = draft_duration_seconds(Path(str(job["draft_path"])))
            bridge.recover_and_open(str(job["draft_name"]))
            manual_check_required = bool(job["manual_check_required"])
            if str(job["subject_type"]) == "final":
                task_row = self.connection.execute(
                    "SELECT final_video_manual_check FROM production_tasks WHERE id=?",
                    (str(job["production_task_id"]),),
                ).fetchone()
                if task_row is not None:
                    manual_check_required = bool(task_row["final_video_manual_check"])
            if str(job["subject_type"]) == "final" and manual_check_required:
                coordinator.await_human_check(attempt_id)
                self._wait_for_human_enter(attempt_id, lease, deadline, wait_for_enter)
                coordinator.confirm_human_check(attempt_id)
                # A user may have edited the final draft during their manual
                # check, so only that branch must read it again here.
                expected_duration = draft_duration_seconds(Path(str(job["draft_path"])))
            else:
                coordinator.begin_submission(attempt_id)
            lease.require_active(attempt_id)
            receipt = bridge.submit(
                draft_name=str(job["draft_name"]), target_path=Path(str(job["target_path"])), expected_duration=expected_duration,
                subject_type=str(job["subject_type"]),
                on_baseline=lambda source, baseline: self.repository.record_source_baseline(attempt_id, source_output_path=str(source), baseline=baseline),
            )
            coordinator.submission_confirmed(attempt_id, source_output_path=str(receipt.source_path), baseline=receipt.baseline)
            # No more Jianying calls below this point.  Users may manually
            # cancel/edit/re-submit while V2 passively watches this same path.
            wait_for_stable_new_file(receipt.source_path, baseline=receipt.baseline, deadline=_deadline_monotonic(deadline))
            verification = verify_media(receipt.source_path, expected_duration=expected_duration)
            coordinator.begin_finalization(attempt_id)
            output_path = self._recovery_output_path(job, attempt_id=attempt_id)
            safe_move_verified_output(receipt.source_path, output_path)
            self._persist_output_path(job, output_path)
            self._record_finalization(attempt_id, verification)
            result = coordinator.complete(attempt_id)
            ExecutorManager(self.connection).report_result("video_exporter", outcome="completed")
            return result
        except V2ExportFailure as exc:
            if exc.code == "USER_DOUBLE_ESC_ABORT":
                result = coordinator.double_esc_abort(attempt_id)
                ExecutorManager(self.connection).report_result("video_exporter", outcome="aborted")
            else:
                result = coordinator.fail(attempt_id, code=exc.code, message=exc.detail, timeout=exc.code.endswith("TIMEOUT"))
                ExecutorManager(self.connection).report_result("video_exporter", outcome="timed_out" if exc.code.endswith("TIMEOUT") else "failed")
            return result
        except Exception as exc:
            result = coordinator.fail(attempt_id, code="UNEXPECTED_FAILURE", message=str(exc))
            ExecutorManager(self.connection).report_result("video_exporter", outcome="failed")
            return result
        finally:
            lease.release(attempt_id)

    def recover_passive_observation(self, attempt_id: str) -> dict[str, Any]:
        """Finish an export already accepted by Jianying before a V2 restart.

        This never opens Jianying or sends input.  It only resumes the
        persisted file observation, validates the MP4, and publishes it.
        """
        attempt = self.repository.attempt(attempt_id)
        if AttemptStatus(str(attempt["status"])) != AttemptStatus.OBSERVING_OUTPUT:
            return attempt
        job = self.repository.job_for_attempt(attempt_id)
        try:
            source_text = str(attempt["source_output_path"] or "").strip()
            source = Path(source_text)
            if not source_text or not source.is_absolute():
                raise V2ExportFailure("RECOVERY_SOURCE_UNREADABLE", "服务重启后缺少剪映原始输出路径，无法安全接回导出")
            try:
                baseline = json.loads(str(attempt["source_baseline_json"] or "{}"))
            except json.JSONDecodeError as exc:
                raise V2ExportFailure("RECOVERY_BASELINE_INVALID", "服务重启后导出基线记录无效") from exc
            if not isinstance(baseline, dict):
                raise V2ExportFailure("RECOVERY_BASELINE_INVALID", "服务重启后导出基线记录无效")
            deadline = _deadline_timestamp(str(attempt["deadline_at"]))
            wait_for_stable_new_file(source, baseline=baseline, deadline=_deadline_monotonic(deadline))
            verification = verify_media(source, expected_duration=draft_duration_seconds(Path(str(job["draft_path"]))))
            coordinator = AttemptCoordinator(self.repository, MemoryInputLease())
            coordinator.begin_finalization(attempt_id)
            output_path = self._recovery_output_path(job, attempt_id=attempt_id)
            safe_move_verified_output(source, output_path)
            self._persist_output_path(job, output_path)
            self._record_finalization(attempt_id, verification)
            result = coordinator.complete(attempt_id)
            ExecutorManager(self.connection).report_result("video_exporter", outcome="completed")
            return result
        except V2ExportFailure as exc:
            result = self.repository.fail(attempt_id, code=exc.code, message=exc.detail)
            ExecutorManager(self.connection).report_result("video_exporter", outcome="timed_out" if exc.code.endswith("TIMEOUT") else "failed")
            return result
        except Exception as exc:
            result = self.repository.fail(attempt_id, code="RECOVERY_UNEXPECTED_FAILURE", message=str(exc))
            ExecutorManager(self.connection).report_result("video_exporter", outcome="failed")
            return result

    def _recovery_output_path(self, job: dict[str, Any], *, attempt_id: str) -> Path:
        """Use the current V2 formal-name rule even for a pre-fix job row."""
        target = Path(str(job["target_path"]))
        if str(job["subject_type"]) != "final":
            return target
        row = self.connection.execute(
            "SELECT t.final_path, t.drama_name, f.sequence_no FROM production_video_tasks v "
            "JOIN production_tasks t ON t.id=v.task_id "
            "JOIN production_files f ON f.id=v.source_material_id WHERE v.id=?",
            (str(job["subject_id"]),),
        ).fetchone()
        if not row or row["sequence_no"] is None:
            raise V2ExportFailure("RECOVERY_FORMAL_NAME_UNAVAILABLE", "无法按剧名和素材序号确定成片正式文件名")
        from server.v2_file_service import safe_component
        output_stem = safe_component(f"{row['drama_name']}-{int(row['sequence_no'])}", "成片视频名称")
        output = Path(str(row["final_path"])) / f"{output_stem}.mp4"
        if output != target:
            self.connection.execute("UPDATE export_jobs SET target_path=?,updated_at=? WHERE id=?", (str(output), datetime.now().isoformat(timespec="seconds"), str(job["id"])))
            self.repository._event(attempt_id, "FORMAL_TARGET_RECALCULATED", AttemptStatus.OBSERVING_OUTPUT, "按当前规则更新成片正式文件名", {"target_path": str(output)})
            self.connection.commit()
            job["target_path"] = str(output)
        return output

    def _wait_for_human_enter(self, attempt_id: str, lease: WindowsInputLease, deadline: float, wait_for_enter: callable | None) -> None:
        if wait_for_enter is not None:
            if not wait_for_enter(deadline):
                raise V2ExportFailure("HUMAN_CHECK_TIMEOUT", "人工检查未在导出期限内按 Enter 确认")
            return
        # Esc is intentionally left available by the V1-tested lease.  The
        # polling loop never reopens a draft and has no Resume branch.
        import ctypes
        was_down = False
        esc_was_down = False
        first_esc_at: float | None = None
        while time.time() < deadline:
            # Input was released for human check, so observe only Enter/Esc.
            enter_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x0D) & 0x8000)
            esc_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
            if esc_down and not esc_was_down:
                current = time.monotonic()
                if first_esc_at is not None and current - first_esc_at <= .75:
                    raise V2ExportFailure("USER_DOUBLE_ESC_ABORT", "用户双 ESC 紧急终止")
                first_esc_at = current
            esc_was_down = esc_down
            if enter_down and not was_down:
                return
            was_down = enter_down
            time.sleep(.05)
        raise V2ExportFailure("HUMAN_CHECK_TIMEOUT", "人工检查未在导出期限内按 Enter 确认")

    def _debug_sink(self, attempt_id: str):
        started = time.monotonic()
        def emit(payload: dict[str, Any]) -> None:
            detail = dict(payload)
            detail["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
            try:
                self.repository._event(attempt_id, "DEBUG_UIA", AttemptStatus.PREPARING, "调试 UIA 事件", detail)
                self.connection.commit()
            except Exception:
                pass
        return emit

    def _record_finalization(self, attempt_id: str, verification: Any) -> None:
        self.repository._event(attempt_id, "OUTPUT_FINALIZED", AttemptStatus.FINALIZING, "MP4 已验证、改名并移动到正式目录", {
            "path": verification.path, "size_bytes": verification.size_bytes, "duration_seconds": verification.duration_seconds,
            "width": verification.width, "height": verification.height, "fps": verification.fps, "codec": verification.codec,
        })
        self.connection.commit()

    def _persist_output_path(self, job: dict[str, Any], output_path: Path) -> None:
        """Publish the verified MP4 path back to the owning production record."""
        stamp = datetime.now().isoformat(timespec="seconds")
        if str(job["subject_type"]) == "template":
            table = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='template_jobs'").fetchone()
            if table:
                self.connection.execute("UPDATE template_jobs SET video_path=?, updated_at=? WHERE id=?", (str(output_path), stamp, str(job["subject_id"])))
        elif str(job["subject_type"]) == "final":
            table = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_video_tasks'").fetchone()
            if table:
                self.connection.execute("UPDATE production_video_tasks SET output_path=?, updated_at=? WHERE id=?", (str(output_path), stamp, str(job["subject_id"])))
        self.connection.commit()


def _deadline_timestamp(value: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError as exc:
        raise V2ExportFailure("ATTEMPT_DEADLINE_INVALID", "导出尝试期限无效") from exc


def _deadline_monotonic(deadline_timestamp: float) -> float:
    """Convert the persisted wall-clock deadline for monotonic file polling."""
    return time.monotonic() + max(0.0, deadline_timestamp - time.time())


def start_attempt_in_background(connection_factory, *, attempt_id: str, settings: dict[str, object]) -> threading.Thread:
    def target() -> None:
        with com_initialized():
            connection = connection_factory()
            try:
                V2ExportRunner(connection, settings=settings).run(attempt_id)
            finally:
                connection.close()
    thread = threading.Thread(target=target, name=f"v2-video-export-{attempt_id[:8]}", daemon=True)
    thread.start()
    return thread


def resume_passive_observation_in_background(connection_factory, *, attempt_id: str, settings: dict[str, object]) -> threading.Thread:
    def target() -> None:
        with com_initialized():
            connection = connection_factory()
            try:
                V2ExportRunner(connection, settings=settings).recover_passive_observation(attempt_id)
            finally:
                connection.close()
    thread = threading.Thread(target=target, name=f"v2-export-recovery-{attempt_id[:8]}", daemon=True)
    thread.start()
    return thread
