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

    def report_result(self, executor_id: str, *, outcome: str) -> dict[str, object]:
        if executor_id not in EXECUTOR_IDS:
            raise ValueError("未知执行器")
        if outcome not in {"completed", "failed", "timed_out"}:
            raise ValueError("执行结果只能是 completed、failed 或 timed_out")
        old = self.state(executor_id)
        failures = 0 if outcome == "completed" else int(old["consecutive_failures"]) + 1
        paused = failures >= FAILURE_PAUSE_THRESHOLD
        self.connection.execute(
            "INSERT INTO executor_controls(executor_id,consecutive_failures,is_paused,updated_at) VALUES (?,?,?,?) ON CONFLICT(executor_id) DO UPDATE SET consecutive_failures=excluded.consecutive_failures,is_paused=excluded.is_paused,updated_at=excluded.updated_at",
            (executor_id, failures, int(paused), self._now()),
        )
        self.connection.commit()
        return self.state(executor_id)

    def restart(self, executor_id: str) -> dict[str, object]:
        """Manual task-center action: clear only this executor's failure history."""
        if executor_id not in EXECUTOR_IDS:
            raise ValueError("未知执行器")
        self.connection.execute(
            "INSERT INTO executor_controls(executor_id,consecutive_failures,is_paused,updated_at) VALUES (?,0,0,?) ON CONFLICT(executor_id) DO UPDATE SET consecutive_failures=0,is_paused=0,updated_at=excluded.updated_at",
            (executor_id, self._now()),
        )
        self.connection.commit()
        return self.state(executor_id)

    def state(self, executor_id: str) -> dict[str, object]:
        row = self.connection.execute("SELECT * FROM executor_controls WHERE executor_id=?", (executor_id,)).fetchone()
        return dict(row) if row else {"executor_id": executor_id, "consecutive_failures": 0, "is_paused": 0}
