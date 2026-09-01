"""Global executor-health policy, shared by template, final and video workers.

This is deliberately outside ``v2_exporter``.  Workers report one completed,
failed or timed-out attempt; the task-center execution manager decides whether
the corresponding executor may receive another task.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


EXECUTOR_IDS = frozenset({"video_exporter", "final_generator", "template_generator"})
FAILURE_PAUSE_THRESHOLD = 3


class ExecutorManager:
    def __init__(self, connection: sqlite3.Connection, *, now: callable | None = None) -> None:
        self.connection = connection
        self._now = now or (lambda: datetime.now().isoformat(timespec="seconds"))
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """Keep the V2 control table forward-compatible for existing databases."""
        columns = {str(row[1]) for row in self.connection.execute("PRAGMA table_info(executor_controls)").fetchall()}
        definitions = {
            "control_state": "TEXT NOT NULL DEFAULT 'idle'",
            "pause_requested": "INTEGER NOT NULL DEFAULT 0 CHECK(pause_requested IN (0, 1))",
            "pause_reason": "TEXT NOT NULL DEFAULT ''",
            "current_task_id": "TEXT NOT NULL DEFAULT ''",
            "last_error_message": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in definitions.items():
            if name not in columns:
                self.connection.execute(f"ALTER TABLE executor_controls ADD COLUMN {name} {definition}")
        self.connection.commit()

    def report_result(self, executor_id: str, *, outcome: str) -> dict[str, object]:
        if executor_id not in EXECUTOR_IDS:
            raise ValueError("未知执行器")
        if outcome not in {"completed", "failed", "timed_out", "aborted"}:
            raise ValueError("执行结果只能是 completed、failed、timed_out 或 aborted")
        old = self.state(executor_id)
        failures = 0 if outcome == "completed" else int(old["consecutive_failures"]) if outcome == "aborted" else int(old["consecutive_failures"]) + 1
        paused = failures >= FAILURE_PAUSE_THRESHOLD
        requested_pause = bool(old.get("pause_requested")) or outcome == "aborted"
        state = "error_paused" if paused else ("manual_paused" if requested_pause else "idle")
        is_paused = paused or requested_pause
        reason = "连续失败3次" if paused else ("用户双 ESC 紧急终止" if outcome == "aborted" else ("人工暂停" if requested_pause else ""))
        self.connection.execute(
            "INSERT INTO executor_controls(executor_id,consecutive_failures,is_paused,control_state,pause_requested,pause_reason,current_task_id,last_error_message,updated_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(executor_id) DO UPDATE SET consecutive_failures=excluded.consecutive_failures,is_paused=excluded.is_paused,control_state=excluded.control_state,pause_requested=excluded.pause_requested,pause_reason=excluded.pause_reason,current_task_id=excluded.current_task_id,last_error_message=excluded.last_error_message,updated_at=excluded.updated_at",
            (executor_id, failures, int(is_paused), state, int(requested_pause), reason, "", "" if outcome in {"completed", "aborted"} else str(old.get("last_error_message", "")), self._now()),
        )
        self.connection.commit()
        return self.state(executor_id)

    def restart(self, executor_id: str) -> dict[str, object]:
        """Manual task-center action: clear only this executor's failure history."""
        if executor_id not in EXECUTOR_IDS:
            raise ValueError("未知执行器")
        self.connection.execute(
            "INSERT INTO executor_controls(executor_id,consecutive_failures,is_paused,control_state,pause_requested,pause_reason,current_task_id,last_error_message,updated_at) VALUES (?,0,0,'idle',0,'','','',?) ON CONFLICT(executor_id) DO UPDATE SET consecutive_failures=0,is_paused=0,control_state='idle',pause_requested=0,pause_reason='',last_error_message='',updated_at=excluded.updated_at",
            (executor_id, self._now()),
        )
        self.connection.commit()
        return self.state(executor_id)

    def resume(self, executor_id: str) -> dict[str, object]:
        """Resume a manually paused executor without changing failure history."""
        if executor_id not in EXECUTOR_IDS:
            raise ValueError("未知执行器")
        current = self.state(executor_id)
        if str(current.get("control_state")) == "error_paused":
            return self.restart(executor_id)
        self.connection.execute(
            "UPDATE executor_controls SET is_paused=0,control_state='idle',pause_requested=0,pause_reason='',updated_at=? WHERE executor_id=?",
            (self._now(), executor_id),
        )
        self.connection.commit()
        return self.state(executor_id)

    def state(self, executor_id: str) -> dict[str, object]:
        row = self.connection.execute("SELECT * FROM executor_controls WHERE executor_id=?", (executor_id,)).fetchone()
        return dict(row) if row else {"executor_id": executor_id, "consecutive_failures": 0, "is_paused": 0, "control_state": "idle", "pause_requested": 0, "pause_reason": "", "current_task_id": "", "last_error_message": ""}

    def request_pause(self, executor_id: str, *, reason: str = "人工暂停") -> dict[str, object]:
        """Request a graceful pause; an active task is allowed to finish."""
        if executor_id not in EXECUTOR_IDS:
            raise ValueError("未知执行器")
        current = self.state(executor_id)
        state = "pausing" if current.get("current_task_id") else "manual_paused"
        stamp = self._now()
        if current.get("executor_id") and self.connection.execute("SELECT 1 FROM executor_controls WHERE executor_id=?", (executor_id,)).fetchone():
            self.connection.execute("UPDATE executor_controls SET is_paused=?,control_state=?,pause_requested=1,pause_reason=?,updated_at=? WHERE executor_id=?", (int(state == "manual_paused"), state, reason, stamp, executor_id))
        else:
            self.connection.execute("INSERT INTO executor_controls(executor_id,consecutive_failures,is_paused,control_state,pause_requested,pause_reason,current_task_id,last_error_message,updated_at) VALUES (?,0,?,?,1,?,'','',?)", (executor_id, int(state == "manual_paused"), state, reason, stamp))
        self.connection.commit()
        return self.state(executor_id)

    def mark_idle_if_pause_requested(self, executor_id: str) -> dict[str, object]:
        current = self.state(executor_id)
        if current.get("pause_requested") and not current.get("current_task_id"):
            self.connection.execute("UPDATE executor_controls SET is_paused=1,control_state='manual_paused',updated_at=? WHERE executor_id=?", (self._now(), executor_id))
            self.connection.commit()
        return self.state(executor_id)

    def resume_global_pause(self, executor_id: str) -> dict[str, object]:
        current = self.state(executor_id)
        if str(current.get("pause_reason") or "") != "全局暂停":
            return current
        return self.resume(executor_id)

    def set_current_task(self, executor_id: str, task_id: str | None) -> dict[str, object]:
        current = self.state(executor_id)
        task = task_id or ""
        state = "running" if task else ("manual_paused" if current.get("pause_requested") else ("error_paused" if current.get("is_paused") and current.get("control_state") == "error_paused" else "idle"))
        stamp = self._now()
        if self.connection.execute("SELECT 1 FROM executor_controls WHERE executor_id=?", (executor_id,)).fetchone():
            self.connection.execute("UPDATE executor_controls SET control_state=?,current_task_id=?,updated_at=? WHERE executor_id=?", (state, task, stamp, executor_id))
        else:
            self.connection.execute("INSERT INTO executor_controls(executor_id,consecutive_failures,is_paused,control_state,pause_requested,pause_reason,current_task_id,last_error_message,updated_at) VALUES (?,0,0,?,0,'',?,?,?)", (executor_id, state, task, "", stamp))
        self.connection.commit()
        return self.state(executor_id)
