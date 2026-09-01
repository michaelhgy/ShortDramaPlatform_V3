"""V2 Exporter first-phase domain.

No Jianying action, queue dispatch, or media mutation belongs here yet.  This
module establishes one attempt history and one event stream before UIA and
file-observation adapters are connected.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol


class AttemptStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    AWAITING_HUMAN_CHECK = "awaiting_human_check"
    SUBMITTING = "submitting"
    OBSERVING_OUTPUT = "observing_output"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class JianyingScene(StrEnum):
    HOME = "home"
    EDITOR = "editor"
    PARAMETER_DIALOG = "parameter_dialog"
    SUCCESS_PAGE = "success_page"
    LOADING = "loading"
    UNKNOWN = "unknown"


TERMINAL = {AttemptStatus.COMPLETED, AttemptStatus.FAILED}
_ALLOWED: dict[AttemptStatus, set[AttemptStatus]] = {
    AttemptStatus.QUEUED: {AttemptStatus.PREPARING, AttemptStatus.FAILED},
    AttemptStatus.PREPARING: {AttemptStatus.AWAITING_HUMAN_CHECK, AttemptStatus.SUBMITTING, AttemptStatus.FAILED},
    AttemptStatus.AWAITING_HUMAN_CHECK: {AttemptStatus.SUBMITTING, AttemptStatus.FAILED},
    AttemptStatus.SUBMITTING: {AttemptStatus.OBSERVING_OUTPUT, AttemptStatus.FAILED},
    AttemptStatus.OBSERVING_OUTPUT: {AttemptStatus.FINALIZING, AttemptStatus.FAILED},
    AttemptStatus.FINALIZING: {AttemptStatus.COMPLETED, AttemptStatus.FAILED},
    AttemptStatus.COMPLETED: set(),
    AttemptStatus.FAILED: set(),
}


class ExportStateError(ValueError):
    pass


class InputLease(Protocol):
    """The real Windows implementation will block physical input behind this interface."""

    def acquire(self, attempt_id: str) -> None: ...
    def release(self, attempt_id: str) -> None: ...


class SceneGateway(Protocol):
    """Future UIA adapter contract.  It must never guess the current draft identity."""

    def inspect(self) -> JianyingScene: ...
    def recover_to_home(self, scene: JianyingScene) -> None: ...


def recovery_is_supported(scene: JianyingScene) -> bool:
    """Only verified, bounded routes may be automated in a later UIA adapter."""
    return scene in {JianyingScene.HOME, JianyingScene.EDITOR, JianyingScene.PARAMETER_DIALOG, JianyingScene.SUCCESS_PAGE, JianyingScene.LOADING}


@dataclass
class MemoryInputLease:
    """Deterministic first-phase lease used by tests; it never touches Windows input."""

    active_attempt_id: str | None = None

    def acquire(self, attempt_id: str) -> None:
        if self.active_attempt_id not in {None, attempt_id}:
            raise ExportStateError("视频导出器键鼠控制已被其他尝试占用")
        self.active_attempt_id = attempt_id

    def release(self, attempt_id: str) -> None:
        if self.active_attempt_id == attempt_id:
            self.active_attempt_id = None


class ExportRepository:
    """SQLite persistence for jobs, immutable attempts and their event stream."""

    def __init__(self, connection: sqlite3.Connection, *, now: callable | None = None) -> None:
        self.connection = connection
        self._now = now or (lambda: datetime.now().isoformat(timespec="seconds"))

    def create_job(self, *, production_task_id: str, subject_type: str, subject_id: str,
                   draft_name: str, draft_path: str, target_path: str,
                   manual_check_required: bool) -> dict[str, Any]:
        if subject_type not in {"template", "final"}:
            raise ValueError("导出对象类型只能是 template 或 final")
        if not all(str(value).strip() for value in (production_task_id, subject_id, draft_name, draft_path, target_path)):
            raise ValueError("导出任务缺少生产任务、草稿或正式输出路径")
        job_id, stamp = uuid.uuid4().hex, self._now()
        self.connection.execute(
            "INSERT INTO export_jobs(id,production_task_id,subject_type,subject_id,draft_name,draft_path,target_path,manual_check_required,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, production_task_id, subject_type, subject_id, draft_name, draft_path, target_path, int(manual_check_required), "ready", stamp, stamp),
        )
        self.connection.commit()
        return self.job(job_id)

    def job(self, job_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM export_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("V2 导出任务不存在")
        return dict(row)

    def queue_new_attempt(self, job_id: str, *, deadline_minutes: int, debug_enabled: bool) -> dict[str, Any]:
        if not 1 <= deadline_minutes <= 120:
            raise ValueError("视频导出超时时间必须为 1-120 分钟")
        job = self.job(job_id)
        active = self.connection.execute(
            "SELECT id FROM export_attempts WHERE job_id=? AND status NOT IN ('completed','failed')", (job_id,)
        ).fetchone()
        if active:
            raise ExportStateError("该导出任务已有进行中的尝试")
        attempt_no = int(self.connection.execute("SELECT COALESCE(MAX(attempt_no), 0) FROM export_attempts WHERE job_id=?", (job_id,)).fetchone()[0]) + 1
        stamp = self._now()
        deadline = (datetime.fromisoformat(stamp) + timedelta(minutes=deadline_minutes)).isoformat(timespec="seconds")
        attempt_id = uuid.uuid4().hex
        self.connection.execute(
            "INSERT INTO export_attempts(id,job_id,attempt_no,status,deadline_at,source_output_path,source_baseline_json,error_code,error_message,debug_enabled,created_at,started_at,finished_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (attempt_id, job_id, attempt_no, AttemptStatus.QUEUED, deadline, "", "{}", "", "", int(debug_enabled), stamp, "", "", stamp),
        )
        self.connection.execute("UPDATE export_jobs SET status='queued',updated_at=? WHERE id=?", (stamp, job_id))
        self._event(attempt_id, "ATTEMPT_QUEUED", AttemptStatus.QUEUED, "已创建新的导出尝试", {"attempt_no": attempt_no, "deadline_at": deadline})
        self.connection.commit()
        return self.attempt(attempt_id)

    def activate_attempt_deadline(self, attempt_id: str) -> dict[str, Any]:
        """Start the export timeout when this serial attempt actually starts.

        A queued attempt can legitimately wait behind earlier renders.  Its
        configured export allowance must therefore not be consumed by queue
        waiting time.  Keep the allowance encoded by the original
        ``created_at -> deadline_at`` interval, but move the deadline to the
        moment this worker begins.
        """
        attempt = self.attempt(attempt_id)
        if AttemptStatus(str(attempt["status"])) != AttemptStatus.QUEUED:
            return attempt
        try:
            original_budget = datetime.fromisoformat(str(attempt["deadline_at"])) - datetime.fromisoformat(str(attempt["created_at"]))
        except ValueError as exc:
            raise ExportStateError("导出尝试期限无效") from exc
        if original_budget.total_seconds() <= 0:
            raise ExportStateError("导出尝试期限必须大于零")
        stamp = self._now()
        deadline = (datetime.fromisoformat(stamp) + original_budget).isoformat(timespec="seconds")
        self.connection.execute(
            "UPDATE export_attempts SET deadline_at=?,updated_at=? WHERE id=? AND status='queued'",
            (deadline, stamp, attempt_id),
        )
        self._event(
            attempt_id,
            "ATTEMPT_STARTED_TIMEOUT_WINDOW",
            AttemptStatus.QUEUED,
            "已开始本次导出计时；排队等待时间不计入超时",
            {"deadline_at": deadline, "timeout_started_at": stamp},
        )
        self.connection.commit()
        return self.attempt(attempt_id)

    def attempt(self, attempt_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM export_attempts WHERE id=?", (attempt_id,)).fetchone()
        if not row:
            raise ValueError("V2 导出尝试不存在")
        return dict(row)

    def job_for_attempt(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.attempt(attempt_id)
        return self.job(str(attempt["job_id"]))

    def events(self, attempt_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.connection.execute("SELECT * FROM export_events WHERE attempt_id=? ORDER BY sequence_no", (attempt_id,))]

    def transition(self, attempt_id: str, target: AttemptStatus, *, event_type: str,
                   message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        current = self.attempt(attempt_id)
        source = AttemptStatus(str(current["status"]))
        if target not in _ALLOWED[source]:
            raise ExportStateError(f"不允许导出尝试从 {source} 转为 {target}")
        stamp = self._now()
        finished = stamp if target in TERMINAL else ""
        self.connection.execute(
            "UPDATE export_attempts SET status=?,started_at=CASE WHEN ?='preparing' AND started_at='' THEN ? ELSE started_at END,finished_at=CASE WHEN ?<>'' THEN ? ELSE finished_at END,updated_at=? WHERE id=?",
            (target, target, stamp, finished, finished, stamp, attempt_id),
        )
        if target == AttemptStatus.COMPLETED:
            job_status = "completed"
        elif target == AttemptStatus.FAILED:
            job_status = "failed"
        else:
            job_status = "active"
        self.connection.execute("UPDATE export_jobs SET status=?,updated_at=? WHERE id=(SELECT job_id FROM export_attempts WHERE id=?)", (job_status, stamp, attempt_id))
        self._event(attempt_id, event_type, target, message, detail or {})
        self.connection.commit()
        return self.attempt(attempt_id)

    def fail(self, attempt_id: str, *, code: str, message: str) -> dict[str, Any]:
        current = self.attempt(attempt_id)
        if AttemptStatus(str(current["status"])) in TERMINAL:
            return current
        stamp = self._now()
        self.connection.execute("UPDATE export_attempts SET error_code=?,error_message=?,updated_at=? WHERE id=?", (code, message, stamp, attempt_id))
        result = self.transition(attempt_id, AttemptStatus.FAILED, event_type="ATTEMPT_FAILED", message=message, detail={"code": code})
        return result

    def record_source_baseline(self, attempt_id: str, *, source_output_path: str, baseline: dict[str, Any]) -> None:
        """Persist the observed Jianying path before the irreversible final click."""
        if not source_output_path:
            raise ValueError("剪映原始输出路径不能为空")
        self.connection.execute(
            "UPDATE export_attempts SET source_output_path=?,source_baseline_json=?,updated_at=? WHERE id=?",
            (source_output_path, json.dumps(baseline, ensure_ascii=False, sort_keys=True), self._now(), attempt_id),
        )
        self._event(attempt_id, "SOURCE_BASELINE_RECORDED", AttemptStatus.SUBMITTING, "已记录剪映原始输出路径及提交前基线", {"source_output_path": source_output_path, "baseline": baseline})
        self.connection.commit()

    def _event(self, attempt_id: str, event_type: str, phase: AttemptStatus, message: str, detail: dict[str, Any]) -> None:
        sequence = int(self.connection.execute("SELECT COALESCE(MAX(sequence_no), 0) FROM export_events WHERE attempt_id=?", (attempt_id,)).fetchone()[0]) + 1
        self.connection.execute(
            "INSERT INTO export_events(id,attempt_id,sequence_no,event_type,phase,message,detail_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, attempt_id, sequence, event_type, str(phase), message, json.dumps(detail, ensure_ascii=False, sort_keys=True), self._now()),
        )


class AttemptCoordinator:
    """Business transitions around UI adapters; no resume path exists after double Esc."""

    def __init__(self, repository: ExportRepository, input_lease: InputLease) -> None:
        self.repository, self.input_lease = repository, input_lease

    def begin(self, attempt_id: str) -> dict[str, Any]:
        self.input_lease.acquire(attempt_id)
        return self.repository.transition(attempt_id, AttemptStatus.PREPARING, event_type="AUTOMATION_STARTED", message="已取得键鼠控制，开始识别剪映场景")

    def await_human_check(self, attempt_id: str) -> dict[str, Any]:
        job = self.repository.job_for_attempt(attempt_id)
        # The runner re-reads the live drama-level policy immediately after
        # opening the draft.  ``manual_check_required`` is only the value that
        # happened to be stored when this export job was queued, so rejecting
        # it here would make a later user toggle fail a queued export.
        if str(job["subject_type"]) != "final":
            raise ExportStateError("只有成片导出才能等待人工检查")
        self.input_lease.release(attempt_id)
        return self.repository.transition(attempt_id, AttemptStatus.AWAITING_HUMAN_CHECK, event_type="HUMAN_CHECK_REQUIRED", message="成片人工检查中；按 Enter 后继续，双 ESC 终止本次尝试")

    def confirm_human_check(self, attempt_id: str) -> dict[str, Any]:
        self.input_lease.acquire(attempt_id)
        return self.repository.transition(attempt_id, AttemptStatus.SUBMITTING, event_type="HUMAN_CHECK_CONFIRMED", message="用户已确认当前草稿，直接继续导出提交")

    def begin_submission(self, attempt_id: str) -> dict[str, Any]:
        return self.repository.transition(attempt_id, AttemptStatus.SUBMITTING, event_type="SUBMISSION_STARTED", message="开始导出参数与最终提交")

    def submission_confirmed(self, attempt_id: str, *, source_output_path: str, baseline: dict[str, Any]) -> dict[str, Any]:
        if not source_output_path:
            raise ValueError("最终提交前必须记录剪映原始输出路径")
        recorded = self.repository.attempt(attempt_id)
        if not str(recorded["source_output_path"]):
            self.repository.record_source_baseline(attempt_id, source_output_path=source_output_path, baseline=baseline)
        elif str(recorded["source_output_path"]) != source_output_path:
            raise ExportStateError("最终提交回执的原始输出路径与提交前记录不一致")
        self.input_lease.release(attempt_id)
        return self.repository.transition(attempt_id, AttemptStatus.OBSERVING_OUTPUT, event_type="SUBMISSION_CONFIRMED", message="剪映已接受导出；已释放键鼠并开始被动观察输出", detail={"source_output_path": source_output_path})

    def begin_finalization(self, attempt_id: str) -> dict[str, Any]:
        return self.repository.transition(attempt_id, AttemptStatus.FINALIZING, event_type="MEDIA_VERIFIED", message="新视频已通过媒体验证，准备原子替换或移动")

    def complete(self, attempt_id: str) -> dict[str, Any]:
        return self.repository.transition(attempt_id, AttemptStatus.COMPLETED, event_type="ATTEMPT_COMPLETED", message="文件收口和数据库写入完成")

    def double_esc_abort(self, attempt_id: str) -> dict[str, Any]:
        self.input_lease.release(attempt_id)
        return self.repository.fail(attempt_id, code="USER_DOUBLE_ESC_ABORT", message="用户双 ESC 紧急终止")

    def fail(self, attempt_id: str, *, code: str, message: str, timeout: bool = False) -> dict[str, Any]:
        self.input_lease.release(attempt_id)
        return self.repository.fail(attempt_id, code=code, message=message)
