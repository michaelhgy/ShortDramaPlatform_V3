import sqlite3
import unittest

from server import v2_file_service as service
from server.executor_management import ExecutorManager
from server.v2_exporter import AttemptCoordinator, AttemptStatus, ExportRepository, MemoryInputLease


class V2ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE production_tasks (id TEXT PRIMARY KEY);
            INSERT INTO production_tasks VALUES ('task-1');
            CREATE TABLE export_jobs (id TEXT PRIMARY KEY, production_task_id TEXT NOT NULL, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, draft_name TEXT NOT NULL, draft_path TEXT NOT NULL, target_path TEXT NOT NULL, manual_check_required INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE export_attempts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, attempt_no INTEGER NOT NULL, status TEXT NOT NULL, deadline_at TEXT NOT NULL, source_output_path TEXT NOT NULL, source_baseline_json TEXT NOT NULL, error_code TEXT NOT NULL, error_message TEXT NOT NULL, debug_enabled INTEGER NOT NULL, created_at TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(job_id, attempt_no));
            CREATE TABLE export_events (id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, sequence_no INTEGER NOT NULL, event_type TEXT NOT NULL, phase TEXT NOT NULL, message TEXT NOT NULL, detail_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(attempt_id, sequence_no));
            CREATE TABLE executor_controls (executor_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL, is_paused INTEGER NOT NULL, updated_at TEXT NOT NULL);
        """)
        self.repo = ExportRepository(self.connection, now=lambda: "2026-08-27T10:00:00")
        self.lease = MemoryInputLease()
        self.coordinator = AttemptCoordinator(self.repo, self.lease)
        self.job = self.repo.create_job(production_task_id="task-1", subject_type="final", subject_id="video-1", draft_name="草稿", draft_path="D:/draft", target_path="D:/target.mp4", manual_check_required=True)

    def test_human_check_returns_to_submission_without_reopening_draft(self) -> None:
        attempt = self.repo.queue_new_attempt(self.job["id"], deadline_minutes=20, debug_enabled=False)
        self.coordinator.begin(attempt["id"])
        waiting = self.coordinator.await_human_check(attempt["id"])
        self.assertEqual(AttemptStatus.AWAITING_HUMAN_CHECK, waiting["status"])
        self.assertIsNone(self.lease.active_attempt_id)
        submitting = self.coordinator.confirm_human_check(attempt["id"])
        self.assertEqual(AttemptStatus.SUBMITTING, submitting["status"])
        self.assertEqual(attempt["id"], self.lease.active_attempt_id)

    def test_double_esc_is_terminal_failure_without_exporter_pause_policy(self) -> None:
        attempt = self.repo.queue_new_attempt(self.job["id"], deadline_minutes=20, debug_enabled=False)
        self.coordinator.begin(attempt["id"])
        stopped = self.coordinator.double_esc_abort(attempt["id"])
        self.assertEqual(AttemptStatus.FAILED, stopped["status"])
        self.assertEqual("USER_DOUBLE_ESC_ABORT", stopped["error_code"])
        self.assertIsNone(self.connection.execute("SELECT 1 FROM executor_controls").fetchone())
        self.assertIsNone(self.lease.active_attempt_id)

    def test_global_executor_manager_pauses_only_the_reported_executor_after_three_results(self) -> None:
        manager = ExecutorManager(self.connection, now=lambda: "2026-08-27T10:00:00")
        for _ in range(3):
            state = manager.report_result("video_exporter", outcome="failed")
        self.assertEqual(1, state["is_paused"])
        self.assertEqual(0, manager.state("template_generator")["consecutive_failures"])
        self.assertEqual(0, manager.restart("video_exporter")["consecutive_failures"])

    def test_submission_records_baseline_before_passive_observation(self) -> None:
        attempt = self.repo.queue_new_attempt(self.job["id"], deadline_minutes=20, debug_enabled=True)
        self.coordinator.begin(attempt["id"])
        self.coordinator.begin_submission(attempt["id"])
        observing = self.coordinator.submission_confirmed(attempt["id"], source_output_path="D:/剪映/源.mp4", baseline={"exists": True, "size": 4, "mtime_ns": 9})
        self.assertEqual(AttemptStatus.OBSERVING_OUTPUT, observing["status"])
        self.assertIsNone(self.lease.active_attempt_id)
        self.assertEqual({"exists": True, "mtime_ns": 9, "size": 4}, __import__("json").loads(observing["source_baseline_json"]))

    def test_human_check_is_not_available_to_template_exports(self) -> None:
        template = self.repo.create_job(production_task_id="task-1", subject_type="template", subject_id="template-1", draft_name="模板草稿", draft_path="D:/template", target_path="D:/template.mp4", manual_check_required=True)
        attempt = self.repo.queue_new_attempt(template["id"], deadline_minutes=20, debug_enabled=False)
        self.coordinator.begin(attempt["id"])
        with self.assertRaisesRegex(ValueError, "只有启用人工检查模式的成片导出"):
            self.coordinator.await_human_check(attempt["id"])


if __name__ == "__main__":
    unittest.main()
