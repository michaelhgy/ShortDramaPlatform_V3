import tempfile
import unittest
import base64
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service


class V2FileServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        service.WORKSPACE = root / "workspace"
        service.DATA_ROOT = root / "system-data"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_resource_index_reuses_metadata_until_file_changes(self) -> None:
        root = service.WORKSPACE / "生成资源" / "引流视频"
        root.mkdir(parents=True, exist_ok=True)
        source = root / "lead.mp4"
        source.write_bytes(b"video")
        calls = []

        def fake_probe(path, key):
            calls.append(str(path))
            thumbnail = service.DATA_ROOT / "cache" / "material-thumbnails" / f"{key}.jpg"
            thumbnail.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.write_bytes(b"jpg")
            return 12.5, "1080x1920", str(thumbnail)

        with patch.object(service, "probe_resource_metadata", side_effect=fake_probe):
            first = service.list_production_resources()
            second = service.list_production_resources()
            self.assertEqual(1, len(calls))
            self.assertEqual(first["items"][0]["durationSeconds"], second["items"][0]["durationSeconds"])
            source.write_bytes(b"changed-video")
            service.list_production_resources()
            self.assertEqual(2, len(calls))

    def test_missing_short_term_cache_is_removed_but_lead_video_cache_is_retained(self) -> None:
        root = service.WORKSPACE / "生成资源"
        lead = root / "引流视频" / "lead.mp4"
        real = root / "真人视频" / "real.mp4"
        lead.parent.mkdir(parents=True, exist_ok=True)
        real.parent.mkdir(parents=True, exist_ok=True)
        lead.write_bytes(b"lead")
        real.write_bytes(b"real")
        with patch.object(service, "probe_resource_metadata", return_value=(1.0, "1080x1920", str(service.DATA_ROOT / "cache" / "placeholder.jpg"))):
            # Use distinct cache files for the two rows.
            service.list_production_resources()
        conn = service.connection()
        try:
            rows = conn.execute("SELECT resource_id, category FROM resource_index").fetchall()
            self.assertEqual(2, len(rows))
            cache_paths = {}
            for row in rows:
                target = service.DATA_ROOT / "cache" / f"{row['resource_id']}.jpg"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"x")
                conn.execute("UPDATE resource_index SET thumbnail_path=? WHERE resource_id=?", (str(target), row["resource_id"]))
            conn.commit()
        finally:
            conn.close()
        lead.unlink()
        real.unlink()
        service.list_production_resources()
        conn = service.connection()
        try:
            categories = {row["category"]: row for row in conn.execute("SELECT category, thumbnail_path FROM resource_index")}
            self.assertIn("lead_video", categories)
            self.assertNotIn("real_video", categories)
            self.assertTrue(Path(categories["lead_video"]["thumbnail_path"]).is_file())
        finally:
            conn.close()

    def test_scan_creates_v2_layout_and_keeps_task_identity(self) -> None:
        task = service.create_task({
            "source_id": "v1-plan-drama-39",
            "account_name": "accountA", "drama_name": "testDrama", "planned_publish_at": "2026-08-27T08:00",
        })
        repeated = service.create_task({
            "source_id": "v1-plan-drama-39",
            "account_name": "accountA", "drama_name": "testDrama", "planned_publish_at": "2026-08-27T08:00",
        })
        self.assertEqual(task["id"], repeated["id"])
        self.assertEqual(date.today().isoformat(), task["created_date"])
        self.assertEqual("2026-08-27T08:00", task["planned_publish_at"])
        materials = Path(task["paths"]["materials"])
        self.assertTrue(materials.is_dir())
        self.assertTrue(all((service.WORKSPACE / name).is_dir() for name in service.ROOT_DIRECTORIES))
        (materials / "download10.mp4").write_bytes(b"first")
        (materials / "download2.mp4").write_bytes(b"second")
        self.assertEqual(2, service.list_tasks()["items"][0]["pending_material_count"])

        result = service.scan_task(str(task["id"]))

        self.assertEqual(2, result["discovered"])
        self.assertEqual(["testDrama-1.mp4", "testDrama-2.mp4"], sorted(item["name"] for item in result["items"]))
        self.assertTrue(all(item["md5"] for item in result["items"]))
        self.assertTrue((service.DATA_ROOT / "database" / "v2_system.db").is_file())
        listed = service.list_tasks()["items"]
        self.assertEqual(1, len(listed))
        self.assertEqual(["testDrama-1.mp4", "testDrama-2.mp4"], [item["name"] for item in listed[0]["materials"]])
        self.assertEqual([], listed[0]["videos"])
        self.assertEqual(0, listed[0]["pending_material_count"])
        (materials / "testDrama-1.mp4").unlink()
        missing_before_scan = service.list_tasks()["items"][0]
        self.assertEqual(["testDrama-2.mp4"], [item["name"] for item in missing_before_scan["materials"]])
        self.assertEqual([], missing_before_scan["videos"])
        service.scan_task(str(task["id"]))
        refreshed = service.list_tasks()["items"][0]
        self.assertEqual(["testDrama-2.mp4"], [item["name"] for item in refreshed["materials"]])
        self.assertEqual([], refreshed["videos"])
        conn = service.connection()
        try:
            self.assertEqual("source_missing", conn.execute("SELECT status FROM production_files WHERE file_name='testDrama-1.mp4'").fetchone()[0])
            self.assertIsNone(conn.execute("SELECT id FROM production_video_tasks WHERE source_material_id=(SELECT id FROM production_files WHERE file_name='testDrama-1.mp4')").fetchone())
        finally:
            conn.close()

    def test_change_feed_reports_only_the_changed_production_task(self) -> None:
        task = service.create_task({
            "source_id": "change-feed-task", "account_name": "accountA", "drama_name": "changeDrama",
            "planned_publish_at": "2026-08-27T08:00",
        })
        initial = service.list_change_events(None)
        self.assertGreaterEqual(int(initial["latest_id"]), 1)
        Path(task["paths"]["materials"]).joinpath("source.mp4").write_bytes(b"change")
        service.scan_task(str(task["id"]))
        events = service.list_change_events(int(initial["latest_id"]))["items"]
        self.assertTrue(events)
        self.assertTrue(all(str(event["production_task_id"]) == str(task["id"]) for event in events))
        self.assertTrue(any(event["change_type"] == "material_changed" for event in events))

    def test_finished_export_name_is_separate_from_its_draft_name(self) -> None:
        task = service.create_task({
            "source_id": "final-output-name", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-28T08:00",
        })
        material = Path(task["paths"]["materials"]) / "待处理.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        material_id = service.list_tasks()["items"][0]["materials"][0]["id"]
        video = service.create_finished_video_task(str(task["id"]), str(material_id))
        draft = Path(self.temp.name) / "草稿"
        draft.mkdir()

        queued = service.ensure_export_job_for_finished_video(
            {"id": video["id"], "task_id": task["id"]},
            draft_name="2026-08-27-账号-剧集-成片-1_成片草稿", draft_path=draft,
        )

        self.assertEqual(Path(task["paths"]["finals"]) / "剧集-1.mp4", Path(str(queued["target_path"])))

    def test_production_list_marks_only_existing_completed_final_export_as_video(self) -> None:
        task = service.create_task({
            "source_id": "completed-final-video", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-28T08:00",
        })
        material = Path(task["paths"]["materials"]) / "待处理.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        material_id = service.list_tasks()["items"][0]["materials"][0]["id"]
        video = service.create_finished_video_task(str(task["id"]), str(material_id))
        draft = Path(self.temp.name) / "草稿-导出完成"; draft.mkdir()
        queued = service.ensure_export_job_for_finished_video({"id": video["id"], "task_id": task["id"]}, draft_name="成片草稿", draft_path=draft)
        output = Path(str(queued["target_path"])); output.write_bytes(b"verified-mp4")
        conn = service.connection()
        try:
            job_id = str(queued["job"]["id"])
            conn.execute("UPDATE export_jobs SET status='completed' WHERE id=?", (job_id,))
            conn.execute("UPDATE export_attempts SET status='completed' WHERE job_id=?", (job_id,))
            conn.execute("UPDATE production_video_tasks SET output_path=? WHERE id=?", (str(output), str(video["id"])))
            conn.commit()
        finally:
            conn.close()

        listed_video = service.list_tasks()["items"][0]["videos"][0]
        self.assertEqual("completed", listed_video["export_status"])
        self.assertTrue(listed_video["output_exists"])
        self.assertEqual(output.stat().st_size, listed_video["output_size_bytes"])

        self.assertEqual(output.resolve(), service.finished_video_media(str(video["id"])))
        with patch.object(service, "probe_material", return_value=(3.0, str(Path(self.temp.name) / "final-thumbnail.jpg"))) as probe:
            thumbnail = Path(self.temp.name) / "final-thumbnail.jpg"
            thumbnail.write_bytes(b"jpg")
            self.assertEqual(thumbnail, service.finished_video_thumbnail(str(video["id"])))
            self.assertEqual(output.resolve(), probe.call_args.args[0])

    def test_open_completed_final_draft_requires_manual_idle_exporter(self) -> None:
        task = service.create_task({
            "source_id": "manual-open-final", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-28T08:00",
        })
        material = Path(task["paths"]["materials"]) / "待处理.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        material_id = service.list_tasks()["items"][0]["materials"][0]["id"]
        video = service.create_finished_video_task(str(task["id"]), str(material_id))
        draft = Path(self.temp.name) / "草稿-人工打开"; draft.mkdir()
        queued = service.ensure_export_job_for_finished_video({"id": video["id"], "task_id": task["id"]}, draft_name="成片草稿", draft_path=draft)
        output = Path(str(queued["target_path"])); output.write_bytes(b"verified-mp4")
        conn = service.connection()
        try:
            conn.execute("UPDATE export_jobs SET status='completed' WHERE id=?", (str(queued["job"]["id"]),))
            conn.execute("UPDATE export_attempts SET status='completed' WHERE job_id=?", (str(queued["job"]["id"]),))
            conn.execute("UPDATE production_video_tasks SET draft_path=?, output_path=? WHERE id=?", (str(draft), str(output), str(video["id"])))
            conn.execute("INSERT INTO executor_controls(executor_id, consecutive_failures, is_paused, control_state, pause_requested, pause_reason, current_task_id, last_error_message, updated_at) VALUES ('video_exporter', 0, 1, 'manual_paused', 1, '人工暂停', '', '', '2026-08-28T08:00:00')")
            conn.commit()
        finally:
            conn.close()

        with patch("server.v2_exporter.runner.start_manual_draft_open_in_background") as start_open:
            result = service.request_open_finished_video_draft(str(video["id"]))
        self.assertTrue(result["accepted"])
        self.assertTrue(start_open.called)

        conn = service.connection()
        try:
            conn.execute("UPDATE executor_controls SET control_state='running', current_task_id='exporting-task' WHERE executor_id='video_exporter'")
            conn.commit()
        finally:
            conn.close()
        with self.assertRaisesRegex(ValueError, "人工暂停"):
            service.request_open_finished_video_draft(str(video["id"]))

    def test_repair_moves_only_an_empty_task_to_the_correct_date(self) -> None:
        task = service.create_task({
            "source_id": "v1-plan-drama-40", "account_name": "accountA", "drama_name": "testDrama", "planned_publish_at": "2026-08-27T08:00",
        })
        old_root = Path(task["paths"]["root"])
        target_date = "2026-08-26" if task["created_date"] == "2026-08-25" else "2026-08-25"
        repaired = service.repair_empty_task_date(str(task["id"]), target_date)

        self.assertEqual(target_date, repaired["created_date"])
        self.assertFalse(old_root.exists())
        self.assertTrue(Path(repaired["paths"]["materials"]).is_dir())

    def test_catalog_starts_empty_then_creates_theater_and_account(self) -> None:
        self.assertEqual([], service.list_theaters()["items"])
        self.assertEqual([], service.list_accounts()["items"])
        theater = service.create_theater({
            "name": "测试剧场", "default_commission_rate": 70, "default_tax_rate": 6,
        })
        account = service.create_account({
            "nickname": "测试账号", "channel_id": "channel-001", "theater_id": theater["id"],
            "reporting_date": "2026-08-25", "status": "正常",
        })
        self.assertEqual("测试剧场", service.list_theaters()["items"][0]["name"])
        self.assertEqual("测试账号", service.list_accounts()["items"][0]["nickname"])
        self.assertEqual("测试剧场", service.list_accounts()["items"][0]["theater_name"])
        self.assertEqual("正常", account["status"])

    def test_publish_date_offset_is_a_persisted_setting(self) -> None:
        settings = service.update_v2_settings({
            "publish_presets": ["08:00", "20:00"],
            "publish_date_offset_days": 1,
        })
        self.assertEqual(["08:00", "20:00"], settings["publish_presets"])
        self.assertEqual(1, settings["publish_date_offset_days"])

    def test_local_vision_ai_mode_is_persisted_and_validated(self) -> None:
        settings = service.update_v2_settings({"local_vision_ai_mode": "disabled"})
        self.assertEqual("disabled", settings["local_vision_ai_mode"])
        with self.assertRaisesRegex(ValueError, "本地视觉 AI 模式"):
            service.update_v2_settings({"local_vision_ai_mode": "unknown"})

    def test_immediate_cleanup_removes_every_owned_process_file_but_keeps_raw_material(self) -> None:
        task = service.create_task({
            "source_id": "immediate-cleanup-scope", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-28T08:00",
        })
        material = Path(task["paths"]["materials"]) / "源素材.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        scanned_material = service.list_tasks()["items"][0]["materials"][0]
        material_id = scanned_material["id"]
        material = Path(task["paths"]["materials"]) / str(scanned_material["name"])

        draft_root = Path(self.temp.name) / "jianying-drafts"; draft_root.mkdir()
        service.update_v2_settings({"jianying_draft_root": str(draft_root)})
        template_draft = draft_root / "模板草稿"; template_draft.mkdir()
        final_draft = draft_root / "成片草稿"; final_draft.mkdir()
        source_output = Path(self.temp.name) / "jianying-default-output.mp4"; source_output.write_bytes(b"leftover")
        thumbnail = service.DATA_ROOT / "cache" / "material-thumbnails" / "source-thumb.jpg"
        thumbnail.parent.mkdir(parents=True, exist_ok=True); thumbnail.write_bytes(b"thumb")
        used_resource = service.WORKSPACE / "生成资源" / "真人视频" / "已使用-测试.mp4"
        used_resource.parent.mkdir(parents=True, exist_ok=True); used_resource.write_bytes(b"reserved")
        (Path(task["paths"]["template"]) / "report.txt").write_text("process", encoding="utf-8")
        (Path(task["paths"]["finals"]) / "剧集-1.mp4").write_bytes(b"final")
        (Path(task["paths"]["root"]) / "缓存" / "成片").mkdir(parents=True, exist_ok=True)
        (Path(task["paths"]["root"]) / "缓存" / "成片" / "cache.bin").write_bytes(b"cache")

        video = service.create_finished_video_task(str(task["id"]), str(material_id))
        stamp = service.now_text()
        conn = service.connection()
        try:
            conn.execute("INSERT INTO template_jobs(id,task_id,version_no,status,draft_name,draft_path,seed,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", ("template-cleanup", task["id"], 1, "draft_ready", "模板草稿", str(template_draft), 1, stamp, stamp))
            conn.execute("UPDATE production_video_tasks SET draft_path=? WHERE id=?", (str(final_draft), video["id"]))
            conn.execute("INSERT INTO export_jobs(id,production_task_id,subject_type,subject_id,draft_name,draft_path,target_path,manual_check_required,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("export-cleanup", task["id"], "final", video["id"], "成片草稿", str(final_draft), str(Path(task["paths"]["finals"]) / "剧集-1.mp4"), 0, "completed", stamp, stamp))
            conn.execute("INSERT INTO export_attempts(id,job_id,attempt_no,status,source_output_path,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", ("attempt-cleanup", "export-cleanup", 1, "completed", str(source_output), stamp, stamp))
            conn.execute("UPDATE production_files SET thumbnail_path=? WHERE id=?", (str(thumbnail), material_id))
            conn.execute("INSERT INTO production_resource_reservations(id,task_id,resource_type,version_no,sequence_no,original_path,reserved_path,original_name,reserved_name,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("reserve-cleanup", task["id"], "real_video", 1, 1, str(used_resource), str(used_resource), "原.mp4", used_resource.name, "reserved", stamp))
            conn.execute("UPDATE production_tasks SET release_status='registered',actual_release_time='2026-08-28 08:00',process_cleanup_at='2099-01-01 08:00:00',raw_cleanup_at='2099-01-07 08:00:00',cleanup_status='active' WHERE id=?", (task["id"],))
            conn.commit()
        finally:
            conn.close()

        preview = service.cleanup_preview(str(task["id"]))
        self.assertGreaterEqual(len(preview["itemsToDelete"]), 6)
        result = service.execute_cleanup(str(task["id"]))
        self.assertEqual([], result["errors"])
        self.assertTrue(material.is_file())
        for path in (template_draft, final_draft, source_output, thumbnail, used_resource, Path(task["paths"]["template"]), Path(task["paths"]["finals"]), Path(task["paths"]["root"]) / "缓存"):
            self.assertFalse(path.exists(), str(path))
        conn = service.connection()
        try:
            row = conn.execute("SELECT cleanup_status,process_cleanup_at FROM production_tasks WHERE id=?", (task["id"],)).fetchone()
            self.assertEqual("process_cleaned", row["cleanup_status"])
            self.assertEqual("2099-01-01 08:00:00", row["process_cleanup_at"])
        finally:
            conn.close()

    def test_due_cleanup_uses_saved_deadlines_then_marks_source_metadata_cleaned(self) -> None:
        task = service.create_task({
            "source_id": "due-cleanup-scope", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-28T08:00",
        })
        material = Path(task["paths"]["materials"]) / "源素材.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        scanned_material = service.list_tasks()["items"][0]["materials"][0]
        material_id = scanned_material["id"]
        material = Path(task["paths"]["materials"]) / str(scanned_material["name"])
        thumbnail = service.DATA_ROOT / "cache" / "material-thumbnails" / "due-thumb.jpg"
        thumbnail.parent.mkdir(parents=True, exist_ok=True); thumbnail.write_bytes(b"thumb")
        (Path(task["paths"]["template"]) / "process.txt").write_text("process", encoding="utf-8")
        conn = service.connection()
        try:
            conn.execute("UPDATE production_files SET thumbnail_path=? WHERE id=?", (str(thumbnail), material_id))
            conn.execute("UPDATE production_tasks SET release_status='registered',actual_release_time='2026-01-01 08:00',process_cleanup_at='2000-01-01 08:00:00',raw_cleanup_at='2999-01-01 08:00:00',cleanup_status='active' WHERE id=?", (task["id"],))
            conn.commit()
        finally:
            conn.close()
        service.update_v2_settings({"short_term_cleanup_hours": 168, "raw_material_retention_days": 90})
        first = service.run_due_cleanup()
        self.assertEqual(1, first["process"])
        self.assertTrue(material.is_file())
        self.assertFalse(Path(task["paths"]["template"]).exists())
        self.assertFalse(thumbnail.exists())

        conn = service.connection()
        try:
            conn.execute("UPDATE production_tasks SET raw_cleanup_at='2000-01-01 08:00:00' WHERE id=?", (task["id"],))
            conn.commit()
        finally:
            conn.close()
        second = service.run_due_cleanup()
        self.assertEqual(1, second["raw"])
        self.assertFalse(material.exists())
        self.assertFalse(thumbnail.exists())
        conn = service.connection()
        try:
            row = conn.execute("SELECT cleanup_status FROM production_tasks WHERE id=?", (task["id"],)).fetchone()
            file_row = conn.execute("SELECT status,thumbnail_path FROM production_files WHERE id=?", (material_id,)).fetchone()
            self.assertEqual("raw_cleaned", row["cleanup_status"])
            self.assertEqual("source_cleaned", file_row["status"])
            self.assertEqual("", file_row["thumbnail_path"])
        finally:
            conn.close()

    def test_delete_unreleased_task_removes_owned_external_files_and_leaves_no_cleanup_history(self) -> None:
        task = service.create_task({
            "source_id": "delete-cleanup-scope", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-28T08:00",
        })
        draft_root = Path(self.temp.name) / "jianying-drafts"; draft_root.mkdir()
        service.update_v2_settings({"jianying_draft_root": str(draft_root)})
        draft = draft_root / "待删除草稿"; draft.mkdir()
        thumbnail = service.DATA_ROOT / "cache" / "material-thumbnails" / "delete-thumb.jpg"
        thumbnail.parent.mkdir(parents=True, exist_ok=True); thumbnail.write_bytes(b"thumb")
        stamp = service.now_text()
        conn = service.connection()
        try:
            conn.execute("INSERT INTO template_jobs(id,task_id,version_no,status,draft_name,draft_path,seed,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", ("template-delete", task["id"], 1, "draft_ready", "待删除草稿", str(draft), 1, stamp, stamp))
            conn.execute("INSERT INTO production_files(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,thumbnail_path,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", ("file-delete", task["id"], "original_material", "源.mp4", "源.mp4", str(Path(task["paths"]["materials"]) / "源.mp4"), "m", "s", 0, str(thumbnail), stamp, stamp))
            conn.commit()
        finally:
            conn.close()

        result = service.execute_cleanup(str(task["id"]))
        self.assertEqual([], result["errors"])
        self.assertFalse(Path(task["paths"]["root"]).exists())
        self.assertFalse(draft.exists())
        self.assertFalse(thumbnail.exists())
        conn = service.connection()
        try:
            self.assertIsNone(conn.execute("SELECT id FROM production_tasks WHERE id=?", (task["id"],)).fetchone())
            self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM cleanup_records WHERE task_id=?", (task["id"],)).fetchone()[0])
        finally:
            conn.close()

    def test_data_drive_derives_the_standard_root_and_preserves_jianying_settings(self) -> None:
        self.assertEqual(Path(r"E:\短剧推广运营系统"), service.system_root_from_drive("e:"))
        bootstrap = Path(self.temp.name) / "bootstrap-settings.json"
        executable = Path(self.temp.name) / "JianyingPro.exe"
        executable.write_bytes(b"")
        draft_root = Path(self.temp.name) / "drafts"
        draft_root.mkdir()

        def derived_root(drive: object) -> Path:
            return Path(self.temp.name) / service.normalize_data_drive(drive).replace(":", "")

        with patch.object(service, "_bootstrap_settings_path", return_value=bootstrap), patch.object(service, "system_root_from_drive", side_effect=derived_root):
            service.WORKSPACE = None
            service.DATA_ROOT = None
            first = service.update_v2_settings({
                "data_drive": "e:",
                "jianying_executable": str(executable),
                "jianying_draft_root": str(draft_root),
            })
            changed = service.update_v2_settings({"data_drive": "f:"})

        self.assertEqual("E:", first["data_drive"])
        self.assertEqual("F:", changed["data_drive"])
        self.assertEqual(str(executable), changed["jianying_executable"])
        self.assertEqual(str(draft_root), changed["jianying_draft_root"])
        self.assertEqual({"data_drive": "F:"}, json.loads(bootstrap.read_text(encoding="utf-8")))

    def test_legacy_system_root_bootstrap_migrates_to_data_drive(self) -> None:
        bootstrap = Path(self.temp.name) / "bootstrap-settings.json"
        bootstrap.write_text(json.dumps({"system_root_dir": r"D:\短剧推广运营系统"}, ensure_ascii=False), encoding="utf-8")
        with patch.object(service, "_bootstrap_settings_path", return_value=bootstrap):
            self.assertEqual("D:", service._configured_data_drive())
        self.assertEqual({"data_drive": "D:"}, json.loads(bootstrap.read_text(encoding="utf-8")))

    def test_batch_theater_import_skips_existing_names_and_keeps_new_names(self) -> None:
        imported = service.create_theaters_batch({"items": [
            {"name": "剧场甲", "default_commission_rate": 70, "default_tax_rate": 6, "status": "启用"},
            {"name": "剧场乙", "default_commission_rate": 68, "default_tax_rate": 6, "status": "停用"},
        ]})
        self.assertEqual(2, imported["created_count"])
        second = service.create_theaters_batch({"items": [
            {"name": "剧场丙", "default_commission_rate": 70, "default_tax_rate": 6},
            {"name": "剧场甲", "default_commission_rate": 70, "default_tax_rate": 6},
        ]})
        self.assertEqual(1, second["created_count"])
        self.assertEqual(["剧场甲"], second["skipped_names"])
        self.assertEqual({"剧场甲", "剧场乙", "剧场丙"}, {item["name"] for item in service.list_theaters()["items"]})

    def test_theater_can_update_and_delete_only_without_accounts(self) -> None:
        theater = service.create_theater({"name": "待编辑剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        updated = service.update_theater(str(theater["id"]), {
            "name": "已编辑剧场", "default_commission_rate": 66, "default_tax_rate": 5, "status": "停用",
        })
        self.assertEqual("已编辑剧场", updated["name"])
        self.assertEqual("停用", updated["status"])
        service.delete_theater(str(theater["id"]))
        self.assertEqual([], service.list_theaters()["items"])

    def test_sub_theaters_persist_and_global_duplicate_names_are_skipped(self) -> None:
        first = service.create_theater({"name": "剧场甲", "default_commission_rate": 70, "default_tax_rate": 6})
        second = service.create_theater({"name": "剧场乙", "default_commission_rate": 70, "default_tax_rate": 6})
        created = service.create_sub_theater({
            "theater_id": first["id"], "name": "云展品读", "commission_rate": 70, "status": "启用",
        })
        self.assertEqual("云展品读", service.list_sub_theaters()["items"][0]["name"])
        service.create_account({
            "nickname": "绑定账号", "channel_id": "bound-channel", "theater_id": first["id"],
            "sub_theater_name": "云展品读", "status": "正常",
        })
        sub_row = next(item for item in service.list_sub_theaters()["items"] if item["id"] == created["id"])
        self.assertEqual(1, sub_row["bound_accounts_count"])
        theater_row = next(item for item in service.list_theaters()["items"] if item["id"] == first["id"])
        self.assertEqual(1, theater_row["sub_theaters_count"])
        batch = service.create_sub_theaters_batch({"items": [
            {"theater_id": second["id"], "name": "云展品读", "commission_rate": 15, "status": "启用"},
            {"theater_id": second["id"], "name": "映雪品读", "commission_rate": 15, "status": "启用"},
        ]})
        self.assertEqual(created["id"], service.list_sub_theaters()["items"][0]["id"])
        self.assertEqual(1, batch["created_count"])
        self.assertEqual(["云展品读"], batch["skipped_names"])

    def test_account_batch_resolves_theater_and_skips_existing_accounts(self) -> None:
        theater = service.create_theater({"name": "账号剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        first = service.create_accounts_batch({"items": [
            {"nickname": "账号甲", "channel_id": "channel-a", "theater_name": "账号剧场", "status": "正常"},
            {"nickname": "账号乙", "channel_id": "channel-b", "theater_name": "账号剧场", "status": "正常"},
        ]})
        second = service.create_accounts_batch({"items": [
            {"nickname": "账号甲", "channel_id": "channel-a2", "theater_name": "账号剧场", "status": "正常"},
            {"nickname": "账号丙", "channel_id": "channel-c", "theater_name": "账号剧场", "status": "正常"},
        ]})
        self.assertEqual(2, first["created_count"])
        self.assertEqual(1, second["created_count"])
        self.assertEqual(["账号甲"], second["skipped_names"])
        self.assertEqual(str(theater["id"]), service.list_accounts()["items"][0]["theater_id"])
        ordered = service.create_accounts_batch({"items": [
            {"nickname": "停用账号", "channel_id": "channel-stop", "theater_name": "账号剧场", "status": "停用"},
            {"nickname": "观察账号", "channel_id": "channel-watch", "theater_name": "账号剧场", "status": "观察"},
        ]})
        self.assertEqual(2, ordered["created_count"])
        statuses = [item["status"] for item in service.list_accounts()["items"]]
        self.assertEqual(["正常", "正常", "正常", "观察", "停用"], statuses)

    def test_account_batch_rejects_missing_or_wrong_sub_theater(self) -> None:
        theater = service.create_theater({"name": "账号归属剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        with self.assertRaisesRegex(ValueError, "子剧场不存在"):
            service.create_accounts_batch({"items": [{
                "nickname": "账号甲", "channel_id": "channel-a", "theater_name": "账号归属剧场", "sub_theater_name": "不存在子剧场",
            }]})

    def test_drama_is_global_unique_and_keeps_history_names(self) -> None:
        theater = service.create_theater({"name": "剧集剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        drama = service.create_drama({"current_name": "春风", "history_names": ["旧春风"], "theater_id": theater["id"]})
        theater_row = next(item for item in service.list_theaters()["items"] if item["id"] == theater["id"])
        self.assertEqual(1, theater_row["dramas_count"])
        with self.assertRaisesRegex(ValueError, "已被其他剧集使用"):
            service.create_drama({"current_name": "旧春风", "history_names": [], "theater_id": theater["id"]})
        updated = service.update_drama(str(drama["id"]), {"current_name": "春风新名", "history_names": ["春风", "旧春风"]})
        self.assertEqual(["春风", "旧春风"], updated["history_names"])
        self.assertFalse((service.WORKSPACE / "剧集资料" / "春风" / "原片").exists())
        self.assertFalse((service.WORKSPACE / "剧集资料" / "春风" / "封面").exists())

    def test_drama_list_returns_real_production_summary_for_schedule(self) -> None:
        theater = service.create_theater({"name": "排期剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        drama = service.create_drama({"current_name": "排期剧", "history_names": [], "theater_id": theater["id"]})
        service.create_task({"source_id": "schedule-drama-summary", "account_name": "账号甲", "drama_name": "排期剧", "planned_publish_at": "2026-08-30T19:30"})
        item = next(row for row in service.list_dramas()["items"] if row["id"] == drama["id"])
        self.assertEqual(1, item["production_count"])
        self.assertEqual("2026-08-30T19:30", item["last_scheduled_at"])
        self.assertEqual(0, item["active_production_count"])

    def test_cover_upload_creates_named_cover_directory_only_on_upload(self) -> None:
        theater = service.create_theater({"name": "封面剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        drama = service.create_drama({"current_name": "封面测试", "history_names": [], "theater_id": theater["id"]})
        result = service.upload_drama_cover(str(drama["id"]), {"filename": "poster.PNG", "content_base64": base64.b64encode(b"image").decode()})
        self.assertEqual("封面测试-封面.png", result["filename"])
        self.assertTrue(Path(result["file_path"]).is_file())
