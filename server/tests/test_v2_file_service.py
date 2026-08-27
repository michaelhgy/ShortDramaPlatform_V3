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
        self.assertEqual(2, len(listed[0]["videos"]))
        self.assertTrue(all(item["status"] == "pending_generation" for item in listed[0]["videos"]))
        self.assertEqual(0, listed[0]["pending_material_count"])
        (materials / "testDrama-1.mp4").unlink()
        missing_before_scan = service.list_tasks()["items"][0]
        self.assertEqual(["testDrama-2.mp4"], [item["name"] for item in missing_before_scan["materials"]])
        self.assertEqual(["testDrama-2.mp4"], [item["name"] for item in missing_before_scan["videos"]])
        service.scan_task(str(task["id"]))
        refreshed = service.list_tasks()["items"][0]
        self.assertEqual(["testDrama-2.mp4"], [item["name"] for item in refreshed["materials"]])
        self.assertEqual(["testDrama-2.mp4"], [item["name"] for item in refreshed["videos"]])
        conn = service.connection()
        try:
            self.assertEqual("source_missing", conn.execute("SELECT status FROM production_files WHERE file_name='testDrama-1.mp4'").fetchone()[0])
            self.assertEqual("cancelled", conn.execute("SELECT status FROM production_video_tasks WHERE source_material_id=(SELECT id FROM production_files WHERE file_name='testDrama-1.mp4')").fetchone()[0])
        finally:
            conn.close()

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

    def test_cover_upload_creates_named_cover_directory_only_on_upload(self) -> None:
        theater = service.create_theater({"name": "封面剧场", "default_commission_rate": 70, "default_tax_rate": 6})
        drama = service.create_drama({"current_name": "封面测试", "history_names": [], "theater_id": theater["id"]})
        result = service.upload_drama_cover(str(drama["id"]), {"filename": "poster.PNG", "content_base64": base64.b64encode(b"image").decode()})
        self.assertEqual("封面测试-封面.png", result["filename"])
        self.assertTrue(Path(result["file_path"]).is_file())
