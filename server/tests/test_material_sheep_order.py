import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from server.template_library import TemplateLibrary


class SheepMaterialScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.originals = service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH
        service.WORKSPACE, service.DATA_ROOT = root / "workspace", root / "state"
        service.DATABASE_INITIALIZED_PATH = None
        self.addCleanup(self.restore_paths)
        self.task = service.create_task({
            "source_id": "sheep-scan", "account_name": "扫描测试", "drama_name": "测试剧",
            "planned_publish_at": "2026-10-25T08:00",
        })
        self.folder = Path(self.task["paths"]["materials"])
        self.probe = patch.object(service, "probe_material", return_value=(1.0, ""))
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.resolution = patch.object(service, "media_resolution", return_value="96x64")
        self.resolution.start()
        self.addCleanup(self.resolution.stop)

    def restore_paths(self):
        service.WORKSPACE, service.DATA_ROOT, service.DATABASE_INITIALIZED_PATH = self.originals

    def source(self, name, payload=None):
        path = self.folder / name
        path.write_bytes(payload or name.encode("utf-8"))
        return path

    def scan(self):
        return service.scan_task(self.task["id"])["items"]

    def records(self):
        conn = service.connection()
        try:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM production_files WHERE task_id=? ORDER BY sequence_no", (self.task["id"],))]
        finally:
            conn.close()

    def test_twenty_interleaved_sources_become_two_contiguous_groups_and_rescan_is_stable(self):
        for i in range(1, 11):
            self.source(f"download{i}-羊头.MP4", f"sheep{i}".encode())
            self.source(f"download{i}.mp4", f"normal{i}".encode())
        expected = [f"测试剧-{i}.mp4" for i in range(1, 11)]
        expected += [f"羊-测试剧-{i}.mp4" for i in range(11, 21)]
        self.assertEqual(expected, [row["name"] for row in self.scan()])
        first = self.records()
        for i, name in enumerate(expected):
            payload = f"normal{i + 1}" if i < 10 else f"sheep{i - 9}"
            self.assertEqual(payload.encode(), (self.folder / name).read_bytes())
        self.assertEqual(expected, [row["name"] for row in self.scan()])
        self.assertEqual([(r["id"], r["original_name"], r["sha256"]) for r in first],
                         [(r["id"], r["original_name"], r["sha256"]) for r in self.records()])
        self.assertEqual(expected, [r["name"] for r in service.list_tasks()["items"][0]["materials"]])

    def test_add_ordinary_source_appends_after_existing_sheep_without_renumbering(self):
        self.source("download1.mp4", b"normal")
        self.source("download2-羊头.mp4", b"sheep")
        self.scan()
        old_sheep = self.records()[1]
        self.source("new.mp4", b"new normal")
        result = self.scan()
        self.assertEqual(["测试剧-1.mp4", "羊-测试剧-2.mp4", "测试剧-3.mp4"], [r["name"] for r in result])
        sheep = self.records()[1]
        self.assertEqual(old_sheep["id"], sheep["id"])
        self.assertEqual(old_sheep["original_name"], sheep["original_name"])
        self.assertEqual(b"sheep", Path(sheep["file_path"]).read_bytes())
        self.assertTrue(all(r["status"] == "available" for r in self.records()))
        self.assertEqual(3, len(self.scan()))

    def test_new_ordinary_clips_keep_the_existing_sheep_group_fixed(self):
        for i in range(1, 4):
            self.source(f"a{i}.mp4", f"normal{i}".encode())
            self.source(f"b{i}羊头.mp4", f"sheep{i}".encode())
        self.scan()
        old_ids = [r["id"] for r in self.records()[3:]]
        self.source("new1.mp4", b"new normal1")
        self.source("new2.mp4", b"new normal2")
        self.assertEqual([f"测试剧-{i}.mp4" for i in range(1, 4)] +
                         [f"羊-测试剧-{i}.mp4" for i in range(4, 7)] +
                         ["测试剧-7.mp4", "测试剧-8.mp4"], [r["name"] for r in self.scan()])
        self.assertEqual(old_ids, [r["id"] for r in self.records()[3:6]])
        self.assertEqual([b"sheep1", b"sheep2", b"sheep3"],
                         [(self.folder / f"羊-测试剧-{i}.mp4").read_bytes() for i in range(4, 7)])

    def test_append_is_allowed_with_existing_video_records(self):
        self.source("a.mp4")
        self.source("b羊头.mp4")
        self.scan()
        video = service.create_finished_video_task(self.task["id"], self.records()[-1]["id"])
        self.assert_append_keeps_existing()
        conn = service.connection()
        try:
            row = conn.execute("SELECT source_material_id FROM production_video_tasks WHERE id=?", (video["id"],)).fetchone()
            self.assertEqual(self.records()[1]["id"], row["source_material_id"])
        finally:
            conn.close()

    def test_append_is_allowed_with_unprojected_ffmpeg_job(self):
        self.source("a.mp4")
        self.source("b羊头.mp4")
        self.scan()
        lib = TemplateLibrary(service.WORKSPACE, service.DATA_ROOT, service.connection, lambda *a: (1, "", ""))
        conn = lib.connect()
        try:
            conn.execute("INSERT INTO final_jobs(id,task_id,material_id,template_id,status,plan,created_at) "
                         "VALUES('job',?,?,'template','waiting','{}',?)",
                         (self.task["id"], self.records()[-1]["id"], service.now_text()))
            conn.commit()
        finally:
            conn.close()
        self.assert_append_keeps_existing()

    def assert_append_keeps_existing(self):
        before_files = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        before_records = self.records()
        self.source("new.mp4", b"new normal")
        self.assertEqual(["测试剧-1.mp4", "羊-测试剧-2.mp4", "测试剧-3.mp4"], [r["name"] for r in self.scan()])
        self.assertEqual(before_files, {name: (self.folder / name).read_bytes() for name in before_files})
        keys = ("id", "file_path", "file_name", "sequence_no", "original_name", "sha256")
        self.assertEqual([tuple(r[k] for k in keys) for r in before_records],
                         [tuple(r[k] for k in keys) for r in self.records()[:2]])

    def test_screenshot_case_last_sheep_ten_then_sheep_eleven_then_normals_twelve_thirteen(self):
        for i in range(1, 11):
            self.source(f"{'羊-' if i >= 5 else ''}测试剧-{i}.mp4")
        self.scan()
        old = self.records()
        self.source("7.mp4", b"normal7")
        self.source("8.mp4", b"normal8")
        self.source("羊头.mp4", b"sheep")
        result = self.scan()
        self.assertEqual(["羊-测试剧-11.mp4", "测试剧-12.mp4", "测试剧-13.mp4"],
                         [r["name"] for r in result[-3:]])
        self.assertEqual([r["id"] for r in old], [r["id"] for r in self.records()[:10]])
        self.assertEqual(b"normal7", (self.folder / "测试剧-12.mp4").read_bytes())
        self.assertEqual(b"normal8", (self.folder / "测试剧-13.mp4").read_bytes())
        self.assertEqual([r["name"] for r in result], [r["name"] for r in self.scan()])

    def test_last_ordinary_takes_priority_over_new_sheep_and_uses_numeric_max(self):
        self.source("羊-测试剧-9.mp4")
        self.source("测试剧-10.mp4")
        self.source("羊头1.mp4")
        self.source("raw10.mp4", b"ten")
        self.source("raw2.mp4", b"two")
        self.assertEqual(["羊-测试剧-9.mp4", "测试剧-10.mp4", "测试剧-11.mp4", "测试剧-12.mp4", "羊-测试剧-13.mp4"],
                         [r["name"] for r in self.scan()])
        self.assertEqual(b"two", (self.folder / "测试剧-11.mp4").read_bytes())

    def test_missing_tail_type_falls_back_to_available_type(self):
        self.source("羊-测试剧-10.mp4")
        self.source("raw.mp4")
        self.assertEqual(["羊-测试剧-10.mp4", "测试剧-11.mp4"], [r["name"] for r in self.scan()])
        self.source("new羊头.mp4")
        self.assertEqual(["羊-测试剧-10.mp4", "测试剧-11.mp4", "羊-测试剧-12.mp4"], [r["name"] for r in self.scan()])

    def test_duplicate_existing_numbers_stop_before_changes(self):
        self.source("测试剧-1.mp4", b"ordinary")
        self.source("羊-测试剧-1.mp4", b"sheep")
        self.source("new.mp4", b"new")
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        with self.assertRaisesRegex(ValueError, "序号 1 重复"):
            self.scan()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})
        self.assertEqual([], self.records())

    def test_all_sheep_and_already_marked_files_keep_marker_and_numeric_order(self):
        self.source("羊-测试剧-2.mp4")
        self.source("羊-测试剧-10.mp4")
        self.source("new羊头.mp4")
        expected = ["羊-测试剧-2.mp4", "羊-测试剧-10.mp4", "羊-测试剧-11.mp4"]
        self.assertEqual(expected, [r["name"] for r in self.scan()])
        self.assertEqual(expected, [r["name"] for r in self.scan()])

    def test_normal_scan_keeps_numbers_and_does_not_treat_sheep_in_drama_title_as_marker(self):
        self.source("测试剧-10.mp4")
        self.source("download2.mp4")
        self.assertEqual([10, 11], [r["sequence_no"] for r in self.scan()])
        self.assertFalse(service.is_sheep_material(Path("羊头风暴-1.mp4"), "羊头风暴"))
        self.assertTrue(service.is_sheep_material(Path("羊-羊头风暴-2.mp4"), "羊头风暴"))
        self.assertEqual(2, service.canonical_sequence(Path("羊-羊头风暴-2.mp4"), "羊头风暴"))

    def test_collision_is_rejected_without_renaming_any_source(self):
        self.source("a.mp4", b"keep")
        (self.folder / "测试剧-1.mp4").mkdir()
        with self.assertRaisesRegex(ValueError, "覆盖"):
            self.scan()
        self.assertEqual(b"keep", (self.folder / "a.mp4").read_bytes())
        self.assertEqual([], self.records())

    def test_failed_destination_move_restores_original_files_and_database(self):
        self.source("download1.mp4", b"normal")
        self.source("download2羊头.mp4", b"sheep")
        real_rename = Path.rename

        def fail_second_destination(path, target):
            if path.name.startswith(".__v2_renaming__") and Path(target).name == "羊-测试剧-2.mp4":
                raise OSError("injected destination failure")
            return real_rename(path, target)

        with patch.object(Path, "rename", fail_second_destination):
            with self.assertRaisesRegex(RuntimeError, "回滚"):
                self.scan()
        self.assertEqual({"download1.mp4": b"normal", "download2羊头.mp4": b"sheep"},
                         {p.name: p.read_bytes() for p in self.folder.iterdir()})
        self.assertEqual([], self.records())
