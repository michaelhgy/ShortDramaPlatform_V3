import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import task_center_service
from server import v2_file_service
from server.task_center_service import _diagnostic_log_excerpt, _executor_snapshot, _executor_stage_items, _export_task_item, _user_facing_error_detail


class V2TaskCenterErrorPresentationTests(unittest.TestCase):
    def test_ollama_port_collision_has_short_operator_message(self) -> None:
        raw_error = '{"results":[{"error":"LocalOllamaError: OLLAMA_CHAT_FAILED: [WinError 10048] port conflict"}]}'
        detail = _user_facing_error_detail(raw_error)
        self.assertIn("端口正被其他程序占用", str(detail))
        self.assertLessEqual(len(str(detail)), 280)

    def test_long_error_is_not_sent_as_unbounded_task_detail_log(self) -> None:
        raw_error = "x" * 2000
        self.assertLess(len(str(_diagnostic_log_excerpt(raw_error))), len(raw_error))
        self.assertLessEqual(len(str(_user_facing_error_detail(raw_error))), 281)


class V2TaskCenterExecutorOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self._originals = (
            v2_file_service.WORKSPACE,
            v2_file_service.DATA_ROOT,
            v2_file_service.DATABASE_INITIALIZED_PATH,
        )
        v2_file_service.WORKSPACE = root / "workspace"
        v2_file_service.DATA_ROOT = root / "system-data"
        v2_file_service.DATABASE_INITIALIZED_PATH = None

    def tearDown(self) -> None:
        (
            v2_file_service.WORKSPACE,
            v2_file_service.DATA_ROOT,
            v2_file_service.DATABASE_INITIALIZED_PATH,
        ) = self._originals
        self.temp.cleanup()

    def test_observing_output_is_presented_as_an_active_export(self) -> None:
        task = _export_task_item({
            "id": "attempt-1", "status": "observing_output", "error_code": "", "error_message": "",
            "subject_type": "template", "production_task_id": "production-1", "account_name": "账号A",
            "drama_name": "剧集A", "planned_publish_at": "", "started_at": "2026-09-02T10:00:00",
            "finished_at": "", "created_at": "2026-09-02T10:00:00", "draft_path": "D:/draft",
            "target_path": "D:/output.mp4",
        })
        self.assertEqual("running", task["status"])
        self.assertEqual("observing_output", task["videoStage"]["rawStatus"])
        self.assertEqual("剪映已提交，等待输出文件", task["stageInfo"]["currentStage"])

    def test_template_export_timeout_belongs_only_to_video_exporter(self) -> None:
        template_card = {
            "executorId": "template_generator",
            "draftStage": {"status": "done"},
            "videoStage": {"status": "timeout", "rawStatus": "failed"},
        }
        self.assertEqual(["done"], [item["status"] for item in _executor_stage_items("template_generator", [template_card])])
        self.assertEqual(["timeout"], [item["status"] for item in _executor_stage_items("video_exporter", [template_card])])

    def test_idle_video_placeholder_is_not_an_exporter_task(self) -> None:
        card = {
            "executorId": "template_generator",
            "draftStage": {"status": "waiting"},
            "videoStage": {"status": "idle"},
        }
        self.assertEqual([], _executor_stage_items("video_exporter", [card]))

    def test_snapshot_keeps_a_complete_executor_payload(self) -> None:
        class Manager:
            def state(self, _executor_id):
                return {"control_state": "idle", "pause_requested": False, "consecutive_failures": 0, "current_task_id": ""}

        result = _executor_snapshot(Manager(), "template_generator", [{
            "executorId": "template_generator", "draftStage": {"status": "done"}, "videoStage": {"status": "idle"},
        }])
        self.assertEqual("模板生成器", result["name"])
        self.assertEqual(1, result["queueStats"]["completed"])


class V2TaskCenterSequenceSchedulingTests(unittest.TestCase):
    def _temporary_database(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        return directory, Path(directory.name) / "task-center.db"

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_final_generator_claims_lower_material_sequence_first(self) -> None:
        temporary, database_path = self._temporary_database()
        self.addCleanup(temporary.cleanup)
        conn = self._connect(database_path)
        try:
            conn.executescript(
                """
                CREATE TABLE executor_controls (
                    executor_id TEXT PRIMARY KEY,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    is_paused INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE production_tasks (id TEXT PRIMARY KEY, planned_publish_at TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE template_jobs (task_id TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE production_files (id TEXT PRIMARY KEY, sequence_no INTEGER, file_name TEXT NOT NULL);
                CREATE TABLE production_video_tasks (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, source_material_id TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute("INSERT INTO production_tasks VALUES ('task-a', '2026-08-29 21:00:00', '2026-08-28 09:00:00')")
            conn.execute("INSERT INTO template_jobs VALUES ('task-a', 'draft_ready')")
            conn.execute("INSERT INTO production_files VALUES ('material-2', 2, '剧集A-2.mp4')")
            conn.execute("INSERT INTO production_files VALUES ('material-3', 3, '剧集A-3.mp4')")
            # 故意让 -3 更早建任务，验证不能再按创建时间抢在 -2 前面。
            conn.execute("INSERT INTO production_video_tasks VALUES ('video-2', 'task-a', 'material-2', 'pending_generation', '2026-08-28 10:05:00', '')")
            conn.execute("INSERT INTO production_video_tasks VALUES ('video-3', 'task-a', 'material-3', 'pending_generation', '2026-08-28 10:00:00', '')")
            conn.commit()
        finally:
            conn.close()

        with patch.object(task_center_service, "_executor_available", return_value=True), patch.object(
            task_center_service.service, "connection", side_effect=lambda: self._connect(database_path)
        ), patch.object(task_center_service.service, "now_text", return_value="2026-08-28 10:10:00"):
            self.assertEqual("video-2", task_center_service._claim_next_final_video())

    def test_final_reexport_does_not_jump_ahead_of_lower_material_sequence(self) -> None:
        temporary, database_path = self._temporary_database()
        self.addCleanup(temporary.cleanup)
        conn = self._connect(database_path)
        try:
            conn.executescript(
                """
                CREATE TABLE executor_controls (
                    executor_id TEXT PRIMARY KEY,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    is_paused INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE production_tasks (id TEXT PRIMARY KEY, planned_publish_at TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE production_files (id TEXT PRIMARY KEY, sequence_no INTEGER, file_name TEXT NOT NULL);
                CREATE TABLE production_video_tasks (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, source_material_id TEXT NOT NULL);
                CREATE TABLE export_jobs (
                    id TEXT PRIMARY KEY, production_task_id TEXT NOT NULL, subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL, draft_name TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE export_attempts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, status TEXT NOT NULL, attempt_no INTEGER NOT NULL);
                """
            )
            conn.execute("INSERT INTO production_tasks VALUES ('task-a', '2026-08-29 21:00:00', '2026-08-28 09:00:00')")
            conn.execute("INSERT INTO production_files VALUES ('material-2', 2, '剧集A-2.mp4')")
            conn.execute("INSERT INTO production_files VALUES ('material-3', 3, '剧集A-3.mp4')")
            conn.execute("INSERT INTO production_video_tasks VALUES ('video-2', 'task-a', 'material-2')")
            conn.execute("INSERT INTO production_video_tasks VALUES ('video-3', 'task-a', 'material-3')")
            conn.execute("INSERT INTO export_jobs VALUES ('job-2', 'task-a', 'final', 'video-2', '剧集A-2', 'queued', '2026-08-28 10:05:00', '')")
            # 模拟 -3 的重新导出更早进队；它也不能抢在 -2 前面。
            conn.execute("INSERT INTO export_jobs VALUES ('job-3-reexport', 'task-a', 'final', 'video-3', '剧集A-3', 'queued', '2026-08-28 10:00:00', '')")
            conn.execute("INSERT INTO export_attempts VALUES ('attempt-2', 'job-2', 'queued', 1)")
            conn.execute("INSERT INTO export_attempts VALUES ('attempt-3-reexport', 'job-3-reexport', 'queued', 2)")
            conn.commit()
        finally:
            conn.close()

        with patch.object(task_center_service, "_executor_available", return_value=True), patch.object(
            task_center_service.service, "connection", side_effect=lambda: self._connect(database_path)
        ), patch.object(task_center_service.service, "now_text", return_value="2026-08-28 10:10:00"):
            self.assertEqual("attempt-2", task_center_service._claim_next_export_attempt())


class V2TaskCenterDramaPriorityTests(unittest.TestCase):
    def test_banner_uses_real_production_order_and_draft_progress(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(
                """
                CREATE TABLE production_tasks (id TEXT PRIMARY KEY, account_name TEXT NOT NULL, drama_name TEXT NOT NULL, planned_publish_at TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE template_jobs (task_id TEXT NOT NULL, version_no INTEGER NOT NULL, status TEXT NOT NULL);
                CREATE TABLE production_video_tasks (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, status TEXT NOT NULL);
                """
            )
            conn.execute("INSERT INTO production_tasks VALUES ('later', '账号乙', '剧集后', '2026-08-29T20:00:00', '2026-08-28T09:00:00')")
            conn.execute("INSERT INTO production_tasks VALUES ('first', '账号甲', '剧集先', '2026-08-29T18:00:00', '2026-08-28T10:00:00')")
            conn.execute("INSERT INTO template_jobs VALUES ('first', 1, 'draft_ready')")
            conn.execute("INSERT INTO production_video_tasks VALUES ('video-1', 'first', 'draft_ready')")
            conn.execute("INSERT INTO production_video_tasks VALUES ('video-2', 'first', 'pending_generation')")
            # 最新版本才代表当前模板阶段；旧版本成功不能把新版本算作完成。
            conn.execute("INSERT INTO template_jobs VALUES ('later', 1, 'draft_ready')")
            conn.execute("INSERT INTO template_jobs VALUES ('later', 2, 'queued')")
            conn.commit()

            priorities = task_center_service._drama_priorities(conn)
        finally:
            conn.close()

        self.assertEqual(["剧集先", "剧集后"], [item["dramaName"] for item in priorities])
        self.assertEqual(["账号甲", "账号乙"], [item["accountName"] for item in priorities])
        self.assertEqual([1, 2], [item["priorityRank"] for item in priorities])
        self.assertEqual("18:00", priorities[0]["scheduledPublishTime"])
        self.assertEqual({"totalTasks": 3, "completedTasks": 2}, {
            key: priorities[0][key] for key in ("totalTasks", "completedTasks")
        })
        self.assertEqual({"totalTasks": 1, "completedTasks": 0}, {
            key: priorities[1][key] for key in ("totalTasks", "completedTasks")
        })

    def test_same_drama_for_two_accounts_stays_as_two_production_units(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript("""
                CREATE TABLE production_tasks (id TEXT PRIMARY KEY, account_name TEXT NOT NULL, drama_name TEXT NOT NULL, planned_publish_at TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE template_jobs (task_id TEXT NOT NULL, version_no INTEGER NOT NULL, status TEXT NOT NULL);
                CREATE TABLE production_video_tasks (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, status TEXT NOT NULL);
            """)
            conn.execute("INSERT INTO production_tasks VALUES ('account-a', '账号甲', '同一剧集', '2026-08-29T10:00:00', '2026-08-28T09:00:00')")
            conn.execute("INSERT INTO production_tasks VALUES ('account-b', '账号乙', '同一剧集', '2026-08-29T10:00:00', '2026-08-28T09:01:00')")
            conn.execute("INSERT INTO template_jobs VALUES ('account-a', 1, 'draft_ready')")
            conn.execute("INSERT INTO template_jobs VALUES ('account-b', 1, 'queued')")
            conn.commit()
            priorities = task_center_service._drama_priorities(conn)
        finally:
            conn.close()

        self.assertEqual(2, len(priorities))
        self.assertEqual(['账号甲', '账号乙'], [item['accountName'] for item in priorities])
        self.assertEqual(['同一剧集', '同一剧集'], [item['dramaName'] for item in priorities])
        self.assertEqual(['account-a', 'account-b'], [item['productionTaskId'] for item in priorities])


if __name__ == "__main__":
    unittest.main()
