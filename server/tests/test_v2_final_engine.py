import tempfile
import threading
import unittest
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from server import v2_file_service as service
from server.final_engine import runner


class V2FinalEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        service.WORKSPACE = root / "workspace"
        service.DATA_ROOT = root / "system-data"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_missing_template_or_donor_is_persisted_as_generation_failure(self) -> None:
        task = service.create_task({"source_id": "final-test", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-27T08:00"})
        material = Path(task["paths"]["materials"]) / "剧集-1.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        listed = service.list_tasks()["items"][0]
        material_id = str(listed["materials"][0]["id"])
        video_id = service.create_finished_video_task(str(task["id"]), material_id)["id"]
        runner.run_finished_video(video_id)
        conn = service.connection()
        try:
            row = conn.execute("SELECT status,error_message FROM production_video_tasks WHERE id=?", (video_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual("generation_failed", row["status"])
        self.assertIn("模板视频", row["error_message"])

    def test_start_finished_video_queues_only_ready_retry_states(self) -> None:
        with self.assertRaises(ValueError):
            runner.start_finished_video("missing")

    def test_opening_cover_model_invalid_json_is_a_generation_error(self) -> None:
        from server.final_engine.scripts import detect_opening_cover

        with patch.object(detect_opening_cover, "request_chat", side_effect=ValueError("empty model response")):
            with self.assertRaisesRegex(ValueError, "empty model response"):
                detect_opening_cover.ask_local_vision("qwen2.5vl:3b", [])

    def test_numbered_uses_file_names_not_path_objects(self) -> None:
        promotion = Path(self.temp.name) / "promotion"
        promotion.mkdir()
        (promotion / "中插2.mp4").write_bytes(b"")
        (promotion / "中插10.mp4").write_bytes(b"")

        self.assertEqual("中插10.mp4", runner._numbered(promotion, "中插").name)

    def test_numbered_accepts_newer_mov_insertion(self) -> None:
        promotion = Path(self.temp.name) / "promotion"
        promotion.mkdir()
        (promotion / "尾插02.mp4").write_bytes(b"")
        (promotion / "尾插03.mov").write_bytes(b"")

        self.assertEqual("尾插03.mov", runner._numbered(promotion, "尾插").name)

    def test_v2_template_pairing_uses_current_window_ratios(self) -> None:
        from server.final_engine.jianying59_final.composition import _pairing_window

        geometry = _pairing_window({
            "schema_version": 1,
            "kind": "v2_template_pairing",
            "canvas": {"width": 1080, "height": 2400},
            "central_window": {
                "width_ratio": 0.91707,
                "height_ratio": 0.759641,
                "mask_width_material": 0.733656,
                "mask_height_material": 0.759641,
                "feather": 0.01,
            },
        })

        self.assertEqual(0.91707, geometry["rectangle"]["width"])
        self.assertEqual(0.759641, geometry["rectangle"]["height"])
        self.assertEqual(0.01, geometry["rectangle"]["feather"])

    def test_processed_command_uses_the_v1_equivalent_batch_entry(self) -> None:
        root = Path(self.temp.name)
        command = runner._processed_composition_command(
            source=root / "素材-1.mp4", template_video=root / "模板.mp4", pairing=root / "配对.json",
            draft_root=root / "drafts", user_data_root=root / "User Data", jianying_app_root=root / "JianyingPro",
            real_photo_dir=root / "真人图片",
            draft_prefix="2026-08-28-账号-剧集-成片", account_id="账号", midroll=root / "中插01.mp4",
            endroll=root / "尾插01.mp4", bgm=root / "bgm.m4a", work_dir=root / "work",
        )

        self.assertTrue(command[1].endswith("run_jianying_composition_batch.py"))
        self.assertEqual(str(root / "素材-1.mp4"), command[command.index("--source-file") + 1])
        self.assertIn("--no-bgm-auto-replenish", command)
        self.assertEqual(str(root / "JianyingPro"), command[command.index("--jianying-app-root") + 1])
        self.assertEqual("compatibility", command[command.index("--local-vision-ai-mode") + 1])

    def test_every_final_detector_receives_the_selected_vision_policy(self) -> None:
        from server.final_engine.scripts.run_jianying_composition_batch import vision_worker_arguments

        self.assertEqual(["--model", "qwen2.5vl:3b"], vision_worker_arguments("qwen2.5vl:3b"))
        self.assertEqual(["--model", "qwen2.5vl:7b"], vision_worker_arguments("qwen2.5vl:7b"))
        self.assertEqual(["--disable-vlm"], vision_worker_arguments(None))

    def test_disabled_tail_analysis_never_calls_ollama_and_keeps_fixed_safety_rules(self) -> None:
        from server.final_engine.scripts import detect_tail_guidance as tail

        source = Path(self.temp.name) / "source.mp4"
        source.write_bytes(b"test source")
        report = Path(self.temp.name) / "tail.json"
        frames = [tail.Frame(index=index, time_seconds=float(index), path=f"frame-{index}.jpg") for index in range(12)]
        guard_frames = [tail.Frame(index=index, time_seconds=7.0 + index / 10, path=f"guard-{index}.jpg") for index in range(30)]
        with patch.object(tail, "probe_video", return_value=(10.0, 30.0)), \
             patch.object(tail, "extract_frames", side_effect=[frames, guard_frames]), \
             patch.object(tail, "ask_tail_model") as coarse_model, \
             patch.object(tail, "ask_short_tail_model") as guard_model, \
             patch.object(tail, "find_tail_ocr_endcard", return_value={"has_endcard_marker": False}), \
             patch.object(tail, "final_visual_endcard_transition", return_value=None):
            result = tail.detect(source, report, Path(self.temp.name) / "evidence", None, 0.0, 10.0, 45.0, 2.0, 6.0, 60)

        coarse_model.assert_not_called()
        guard_model.assert_not_called()
        self.assertEqual("disabled", result["local_model"])
        self.assertEqual("NO_TRAILING_GUIDANCE", result["decision"]["action"])
        self.assertEqual("disabled", result["short_tail_guard"]["decision"]["status"])
        self.assertTrue(all(len(group["frames"]) <= 3 for group in result["groups"]))

    def test_context_or_missing_model_error_is_not_retried(self) -> None:
        from server.final_engine.scripts import ollama_local

        error = HTTPError("http://127.0.0.1:11434/api/chat", 400, "bad request", {}, BytesIO(b'{"error":"context too large"}'))
        with patch.object(ollama_local, "_request_json", side_effect=error) as request:
            with self.assertRaisesRegex(ollama_local.LocalOllamaError, "HTTP 400"):
                ollama_local.request_chat({"model": "qwen2.5vl:3b"})
        self.assertEqual(1, request.call_count)

    def test_final_work_dir_is_under_the_production_task_cache(self) -> None:
        root = Path(self.temp.name) / "production-task"
        self.assertEqual(root / "缓存" / "成片" / "video-1", runner._final_work_dir(task_root=root, video_id="video-1"))

    def test_batch_failure_detail_uses_the_actual_source_error(self) -> None:
        root = Path(self.temp.name)
        source = root / "素材-1.mp4"
        summary = root / "批量结果.json"
        summary.write_text(json.dumps({"results": [
            {"source": str(source), "status": "FAILED", "error": "FileNotFoundError: 缺少模板配对参数"},
        ]}, ensure_ascii=False), encoding="utf-8")
        self.assertEqual("FileNotFoundError: 缺少模板配对参数", runner._batch_failure_detail(summary, source))

    def test_short_lived_worker_trace_is_relayed_after_process_exit(self) -> None:
        trace = Path(self.temp.name) / "执行过程.jsonl"
        trace.write_text(json.dumps({"phase": "写入成片草稿失败", "message": "RuntimeError: 明确原因"}, ensure_ascii=False) + "\n", encoding="utf-8")
        task = service.create_task({"source_id": "trace-final", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-27T08:00"})
        state = {"seen": 0}
        with patch.object(service, "record_executor_trace") as record:
            relayed = runner._relay_worker_trace(video_id="video", task_id=str(task["id"]), worker_trace=trace,
                                                 state=state, lock=threading.Lock())
        self.assertTrue(relayed)
        self.assertEqual(1, state["seen"])
        self.assertEqual("写入成片草稿失败", record.call_args.kwargs["phase"])

    def test_retry_cleans_only_failed_video_process_files_and_requeues_same_task(self) -> None:
        task = service.create_task({"source_id": "retry-final", "account_name": "账号", "drama_name": "剧集", "planned_publish_at": "2026-08-27T08:00"})
        material = Path(task["paths"]["materials"]) / "剧集-1.mp4"
        material.write_bytes(b"source")
        service.scan_task(str(task["id"]))
        material_id = service.list_tasks()["items"][0]["materials"][0]["id"]
        video = service.create_finished_video_task(str(task["id"]), str(material_id))
        video_id = str(video["id"])
        work_dir = runner._final_work_dir(task_root=Path(task["paths"]["root"]), video_id=video_id)
        work_dir.mkdir(parents=True)
        (work_dir / "临时文件").write_text("x", encoding="utf-8")
        draft_root = Path(self.temp.name) / "drafts"
        draft_root.mkdir()
        old_draft = draft_root / "旧失败草稿"
        old_draft.mkdir()
        stale_named_draft = draft_root / f"{task['created_date']}-账号-剧集-成片-1_成片草稿"
        stale_named_draft.mkdir()
        conn = service.connection()
        try:
            conn.execute("UPDATE production_video_tasks SET status='generation_failed', draft_path=?, error_message='旧错误', started_at='old', finished_at='old' WHERE id=?", (str(old_draft), video_id))
            conn.commit()
        finally:
            conn.close()
        with patch.object(service, "get_v2_settings", return_value={"jianying_draft_root": str(draft_root)}):
            for status in ("generation_failed", "generation_timeout", "generating"):
                conn = service.connection()
                try:
                    conn.execute("UPDATE production_video_tasks SET status=?, draft_path=?, error_message='旧错误', started_at='old', finished_at='old' WHERE id=?", (status, str(old_draft), video_id))
                    conn.commit()
                finally:
                    conn.close()
                old_draft.mkdir(exist_ok=True)
                result = service.requeue_finished_video(video_id)
                self.assertEqual({"id": video_id, "status": "pending_generation"}, result)
                self.assertFalse(old_draft.exists())
                self.assertFalse(stale_named_draft.exists())
        self.assertEqual({"id": video_id, "status": "pending_generation"}, result)
        self.assertFalse(work_dir.exists())
        self.assertTrue(material.is_file())
        conn = service.connection()
        try:
            row = conn.execute("SELECT status, draft_path, error_message, started_at, finished_at FROM production_video_tasks WHERE id=?", (video_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual("pending_generation", row["status"])
        self.assertEqual("", row["draft_path"])
        self.assertEqual("", row["error_message"])
        self.assertEqual("", row["started_at"])
        self.assertEqual("", row["finished_at"])
