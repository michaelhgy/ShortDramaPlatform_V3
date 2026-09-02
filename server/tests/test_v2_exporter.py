import sqlite3
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from server.executor_management import ExecutorManager
from server.v2_exporter import AttemptCoordinator, AttemptStatus, ExportRepository, MemoryInputLease
from server.v2_exporter.runtime import MediaInfo, Submission, file_baseline


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

    def test_live_human_check_can_pause_a_job_queued_before_the_toggle(self) -> None:
        queued_before_toggle = self.repo.create_job(
            production_task_id="task-1", subject_type="final", subject_id="video-older",
            draft_name="旧草稿", draft_path="D:/draft", target_path="D:/target.mp4", manual_check_required=False,
        )
        attempt = self.repo.queue_new_attempt(queued_before_toggle["id"], deadline_minutes=20, debug_enabled=False)
        self.coordinator.begin(attempt["id"])

        waiting = self.coordinator.await_human_check(attempt["id"])

        self.assertEqual(AttemptStatus.AWAITING_HUMAN_CHECK, waiting["status"])
        self.assertIsNone(self.lease.active_attempt_id)

    def test_double_esc_is_terminal_failure_without_exporter_pause_policy(self) -> None:
        attempt = self.repo.queue_new_attempt(self.job["id"], deadline_minutes=20, debug_enabled=False)
        self.coordinator.begin(attempt["id"])
        stopped = self.coordinator.double_esc_abort(attempt["id"])
        self.assertEqual(AttemptStatus.FAILED, stopped["status"])
        self.assertEqual("USER_DOUBLE_ESC_ABORT", stopped["error_code"])
        self.assertIsNone(self.connection.execute("SELECT 1 FROM executor_controls").fetchone())
        self.assertIsNone(self.lease.active_attempt_id)

    def test_export_timeout_starts_when_the_serial_worker_claims_the_attempt(self) -> None:
        clock = ["2026-08-27T10:00:00"]
        repository = ExportRepository(self.connection, now=lambda: clock[0])
        job = repository.create_job(production_task_id="task-1", subject_type="template", subject_id="template-1", draft_name="草稿", draft_path="D:/draft", target_path="D:/target.mp4", manual_check_required=False)
        attempt = repository.queue_new_attempt(job["id"], deadline_minutes=20, debug_enabled=False)
        self.assertEqual("2026-08-27T10:20:00", attempt["deadline_at"])

        # It waited half an hour behind earlier serial exports.  Its own
        # twenty-minute allowance must begin only now.
        clock[0] = "2026-08-27T10:30:00"
        active = repository.activate_attempt_deadline(attempt["id"])
        self.assertEqual("2026-08-27T10:50:00", active["deadline_at"])
        events = repository.events(attempt["id"])
        self.assertEqual("ATTEMPT_STARTED_TIMEOUT_WINDOW", events[-1]["event_type"])

    def test_global_executor_manager_pauses_only_the_reported_executor_after_three_results(self) -> None:
        manager = ExecutorManager(self.connection, now=lambda: "2026-08-27T10:00:00")
        for _ in range(3):
            state = manager.report_result("video_exporter", outcome="failed")
        self.assertEqual(1, state["is_paused"])
        self.assertEqual(0, manager.state("template_generator")["consecutive_failures"])
        self.assertEqual(0, manager.restart("video_exporter")["consecutive_failures"])

    def test_executor_manual_pause_drains_current_task_before_pausing(self) -> None:
        manager = ExecutorManager(self.connection, now=lambda: "2026-08-27T10:00:00")
        manager.set_current_task("video_exporter", "export-1")
        pausing = manager.request_pause("video_exporter")
        self.assertEqual("pausing", pausing["control_state"])
        self.assertEqual(1, pausing["pause_requested"])
        paused = manager.report_result("video_exporter", outcome="completed")
        self.assertEqual("manual_paused", paused["control_state"])
        self.assertEqual(1, paused["is_paused"])
        self.assertEqual(0, paused["consecutive_failures"])

    def test_executor_error_pause_is_independent_and_success_clears_failures(self) -> None:
        manager = ExecutorManager(self.connection, now=lambda: "2026-08-27T10:00:00")
        for _ in range(2):
            state = manager.report_result("template_generator", outcome="failed")
        self.assertEqual("idle", state["control_state"])
        state = manager.report_result("template_generator", outcome="timed_out")
        self.assertEqual("error_paused", state["control_state"])
        self.assertEqual(3, state["consecutive_failures"])
        self.assertEqual(0, manager.state("video_exporter")["consecutive_failures"])
        restarted = manager.restart("template_generator")
        self.assertEqual(0, restarted["consecutive_failures"])
        self.assertEqual("idle", restarted["control_state"])

    def test_double_esc_pauses_safely_without_counting_as_a_program_failure(self) -> None:
        manager = ExecutorManager(self.connection, now=lambda: "2026-08-27T10:00:00")
        manager.report_result("video_exporter", outcome="failed")
        state = manager.report_result("video_exporter", outcome="aborted")
        self.assertEqual(1, state["consecutive_failures"])
        self.assertEqual("manual_paused", state["control_state"])
        self.assertEqual("用户双 ESC 紧急终止", state["pause_reason"])

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
        with self.assertRaisesRegex(ValueError, "只有成片导出"):
            self.coordinator.await_human_check(attempt["id"])

    def test_runner_reports_success_to_global_executor_manager(self) -> None:
        from server.v2_exporter.runner import V2ExportRunner
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); draft = root / "draft"; draft.mkdir()
            (draft / "draft_content.json").write_text('{"duration":10000000,"canvas_config":{"width":1080,"height":2400}}', encoding="utf-8")
            source = root / "jianying.mp4"; source.write_bytes(b"new")
            target = root / "formal.mp4"
            job = self.repo.create_job(production_task_id="task-1", subject_type="template", subject_id="t", draft_name="草稿", draft_path=str(draft), target_path=str(target), manual_check_required=False)
            attempt = self.repo.queue_new_attempt(job["id"], deadline_minutes=20, debug_enabled=False)
            class Lease:
                def __init__(self, **_kwargs): pass
                def acquire(self, _id): pass
                def release(self, _id): pass
                def require_active(self, _id): pass
            class Bridge:
                def __init__(self, *_args, **_kwargs): pass
                def ensure_started(self): pass
                def recover_and_open(self, _name): pass
                def submit(self, **kwargs):
                    kwargs["on_baseline"](source, {"exists": False, "size": 0, "mtime_ns": 0})
                    return Submission(source, {"exists": False, "size": 0, "mtime_ns": 0})
            media = MediaInfo(str(source), 3, 10, 1080, 2400, 30, "h264")
            with patch("server.jianying_preflight.require_jianying_ready"), patch("server.v2_exporter.runner.WindowsInputLease", Lease), patch("server.v2_exporter.runner.Jianying59Bridge", Bridge), patch("server.v2_exporter.runner.wait_for_stable_new_file"), patch("server.v2_exporter.runner.verify_media", return_value=media):
                result = V2ExportRunner(self.connection, settings={}).run(attempt["id"])
            self.assertEqual(AttemptStatus.COMPLETED, result["status"])
            self.assertEqual(0, ExecutorManager(self.connection).state("video_exporter")["consecutive_failures"])
            self.assertTrue(target.is_file())

    def test_runner_reports_failure_to_global_executor_manager(self) -> None:
        from server.v2_exporter.runner import V2ExportRunner
        from server.v2_exporter.runtime import V2ExportFailure
        job = self.repo.create_job(production_task_id="task-1", subject_type="template", subject_id="t", draft_name="草稿", draft_path="D:/draft", target_path="D:/target.mp4", manual_check_required=False)
        attempt = self.repo.queue_new_attempt(job["id"], deadline_minutes=20, debug_enabled=False)
        class Lease:
            def __init__(self, **_kwargs): pass
            def acquire(self, _id): pass
            def release(self, _id): pass
            def require_active(self, _id): pass
        class Bridge:
            def __init__(self, *_args, **_kwargs): pass
            def ensure_started(self): raise V2ExportFailure("JIANYING_START_FAILED", "测试启动失败")
        with patch("server.jianying_preflight.require_jianying_ready"), patch("server.v2_exporter.runner.WindowsInputLease", Lease), patch("server.v2_exporter.runner.Jianying59Bridge", Bridge):
            result = V2ExportRunner(self.connection, settings={}).run(attempt["id"])
        self.assertEqual(AttemptStatus.FAILED, result["status"])
        self.assertEqual("JIANYING_START_FAILED", result["error_code"])
        self.assertEqual(1, ExecutorManager(self.connection).state("video_exporter")["consecutive_failures"])

    def test_restart_recovery_finishes_persisted_passive_observation(self) -> None:
        from server.v2_exporter.runner import V2ExportRunner
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); draft = root / "draft"; draft.mkdir()
            (draft / "draft_content.json").write_text('{"duration":10000000,"canvas_config":{"width":1080,"height":2400}}', encoding="utf-8")
            source, target = root / "jianying.mp4", root / "formal.mp4"
            source.write_bytes(b"accepted-by-jianying")
            job = self.repo.create_job(production_task_id="task-1", subject_type="template", subject_id="template-1", draft_name="草稿", draft_path=str(draft), target_path=str(target), manual_check_required=False)
            attempt = self.repo.queue_new_attempt(job["id"], deadline_minutes=20, debug_enabled=False)
            self.coordinator.begin(attempt["id"]); self.coordinator.begin_submission(attempt["id"])
            self.coordinator.submission_confirmed(attempt["id"], source_output_path=str(source), baseline={"exists": False, "size": 0, "mtime_ns": 0})
            media = MediaInfo(str(source), source.stat().st_size, 10, 1080, 2400, 30, "h264")
            with patch("server.v2_exporter.runner.wait_for_stable_new_file"), patch("server.v2_exporter.runner.verify_media", return_value=media):
                result = V2ExportRunner(self.connection, settings={}).recover_passive_observation(attempt["id"])
            self.assertEqual(AttemptStatus.COMPLETED, result["status"])
            self.assertTrue(target.is_file())
            self.assertFalse(source.exists())

    def test_restart_recovery_recalculates_legacy_final_video_name(self) -> None:
        from server.v2_exporter.runner import V2ExportRunner
        self.connection.executescript(
            """
            ALTER TABLE production_tasks ADD COLUMN final_path TEXT NOT NULL DEFAULT '';
            ALTER TABLE production_tasks ADD COLUMN drama_name TEXT NOT NULL DEFAULT '';
            ALTER TABLE production_tasks ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
            CREATE TABLE production_files (id TEXT PRIMARY KEY, sequence_no INTEGER NOT NULL);
            CREATE TABLE production_video_tasks (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, source_material_id TEXT NOT NULL, output_path TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '');
            """
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); draft = root / "draft"; draft.mkdir(); finals = root / "finals"; finals.mkdir()
            (draft / "draft_content.json").write_text('{"duration":10000000,"canvas_config":{"width":1080,"height":2400}}', encoding="utf-8")
            self.connection.execute("UPDATE production_tasks SET final_path=?,drama_name=? WHERE id='task-1'", (str(finals), "剧集A"))
            self.connection.execute("INSERT INTO production_files VALUES ('material-2', 2)")
            self.connection.execute("INSERT INTO production_video_tasks(id,task_id,source_material_id) VALUES ('video-2','task-1','material-2')")
            self.connection.commit()
            source = root / "jianying.mp4"; source.write_bytes(b"accepted-by-jianying")
            legacy_target = finals / "旧格式.mp4"
            job = self.repo.create_job(production_task_id="task-1", subject_type="final", subject_id="video-2", draft_name="草稿", draft_path=str(draft), target_path=str(legacy_target), manual_check_required=False)
            attempt = self.repo.queue_new_attempt(job["id"], deadline_minutes=20, debug_enabled=False)
            self.coordinator.begin(attempt["id"]); self.coordinator.begin_submission(attempt["id"])
            self.coordinator.submission_confirmed(attempt["id"], source_output_path=str(source), baseline={"exists": False, "size": 0, "mtime_ns": 0})
            media = MediaInfo(str(source), source.stat().st_size, 10, 1080, 2400, 30, "h264")
            with patch("server.v2_exporter.runner.wait_for_stable_new_file"), patch("server.v2_exporter.runner.verify_media", return_value=media):
                result = V2ExportRunner(self.connection, settings={}).recover_passive_observation(attempt["id"])
            self.assertEqual(AttemptStatus.COMPLETED, result["status"], result)
            correct_target = finals / "剧集A-2.mp4"
            self.assertTrue(correct_target.is_file())
            self.assertFalse(legacy_target.exists())
            self.assertEqual(str(correct_target), self.repo.job(job["id"])["target_path"])


if __name__ == "__main__":
    unittest.main()
