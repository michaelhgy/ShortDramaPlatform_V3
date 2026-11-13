"""按阶段恢复原片任务的隔离检查，不连接手机、网络或业务数据库。"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from server import drama_download_reader as reader


class StageResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = dict(reader._STATE)
        self.addCleanup(lambda: (reader._STATE.clear(), reader._STATE.update(self.old), reader._CANCEL_EVENT.clear()))
        env = patch.dict(os.environ, {"V3_DRAMA_READ_TASK_STATE": str(self.root / "state.json")})
        env.start(); self.addCleanup(env.stop)
        thread = patch.object(reader, "_THREAD", None)
        thread.start(); self.addCleanup(thread.stop)
        reader._CANCEL_EVENT.clear()
        identity = hashlib.sha256(json.dumps([str(self.root).casefold(), "剧场", "剧"], ensure_ascii=False).encode()).hexdigest()[:24]
        self.journal = self.root / "tasks" / (identity + ".json")
        self.journal.parent.mkdir(); self.journal.write_text("{}")
        reader._STATE.clear()
        reader._STATE.update(status="failed", phase="parse-download", task={"drama_name":"剧", "task_label":"#剧", "chat_name":"任务群"},
            journal_path=str(self.journal), download_root=str(self.root), theater_name="剧场", expected_count=50,
            episodes={str(n):{"link":f"fixture:{n}", "verified":n!=47} for n in range(1,51)},
            stage_states={"read-task":"done", "collect-links":"done", "parse-download":"failed"},
            logs=["第47集下载失败"], stage_logs={"parse-download":["第47集下载失败"]}, missing_video_episodes=list(range(1,51)))

    def test_status_corrects_legacy_missing_list_without_changing_record(self):
        reader._save()
        before = (self.root / "state.json").read_bytes()
        result = reader.status()
        self.assertEqual(result["missing_video_episodes"], [47])
        self.assertEqual(result["resume_phase"], "parse-download")
        self.assertEqual((self.root / "state.json").read_bytes(), before)

    def test_live_summary_updates_missing_list_after_each_success(self):
        reader._summarize_episodes()
        self.assertEqual(reader._STATE["missing_video_episodes"], [47])
        reader._STATE["episodes"]["47"]["verified"] = True
        reader._summarize_episodes()
        self.assertEqual(reader._STATE["missing_video_episodes"], [])

    def run_resume(self, phase, complete47=False):
        reader._STATE["phase"] = phase
        if complete47:
            reader._STATE["episodes"]["47"]["verified"] = True
        calls = []
        def prepare():
            calls.append("prepare")
            reader._STATE.update(missing_link_episodes=[], verified_count=49 if not complete47 else 50)
        def download(_):
            calls.append("download47")
            self.assertFalse(reader._STATE["episodes"]["47"]["verified"])
            reader._STATE["episodes"]["47"]["verified"] = True
            reader._STATE.update(status="succeeded", parse_failed_episodes=[])
        def verify():
            calls.append("verify")
            reader._STATE.update(status="succeeded", complete=True)
        def cleanup():
            calls.append("cleanup")
            reader._STATE.update(status="succeeded")
        with patch.object(reader, "_context", return_value=("剧", "剧场", self.root)), \
             patch.object(reader, "_prepare_task", side_effect=prepare), \
             patch.object(reader, "_read_worker") as read, \
             patch.object(reader, "_collect_worker") as collect, \
             patch.object(reader, "_download_worker", side_effect=download) as dl, \
             patch.object(reader, "_verify_worker", side_effect=verify), \
             patch.object(reader, "_delete_worker", side_effect=cleanup):
            reader._pipeline_worker({"_resume_phase":phase, "task_limit":1})
        read.assert_not_called(); collect.assert_not_called()
        self.assertEqual(reader._STATE["phase"], "completed")
        return calls, dl

    def test_download_resume_skips_phone_and_then_verifies(self):
        calls, _ = self.run_resume("parse-download")
        self.assertEqual(calls, ["prepare", "download47", "verify", "cleanup"])

    def test_verify_resume_skips_phone_and_download(self):
        calls, download = self.run_resume("verify-download", complete47=True)
        self.assertEqual(calls, ["prepare", "verify", "cleanup"])
        download.assert_not_called()

    def test_verify_resume_repairs_invalid_file_before_verifying(self):
        calls, _ = self.run_resume("verify-download")
        self.assertEqual(calls, ["prepare", "download47", "verify", "cleanup"])

    def test_retry_download_command_only_contains_episode47(self):
        def run(command, _):
            self.assertEqual(command[command.index("--episodes")+1], "47")
            reader._STATE["episodes"]["47"]["verified"] = True
            return 0, []
        with patch.object(reader, "_context", return_value=("剧", "剧场", self.root)), \
             patch.object(reader, "_sync_links"), patch.object(reader, "_run", side_effect=run):
            reader._download_worker({})
        self.assertEqual(reader._STATE["planned_download_episodes"], [47])
        self.assertEqual(reader._STATE["status"], "succeeded")

    def test_start_preserves_history_and_uses_resume_phase(self):
        observed = {}
        def run(payload):
            observed.update(phase=reader._STATE["phase"], logs=list(reader._STATE["logs"]), options=payload,
                            journal=reader._STATE["journal_path"])
            reader._set(status="failed")
        with patch.object(reader, "_pipeline_worker", side_effect=run):
            reader.start_pipeline({"task_limit":1})
            reader._THREAD.join(3)
        self.assertEqual(observed["phase"], "parse-download")
        self.assertEqual(observed["logs"], ["第47集下载失败"])
        self.assertEqual(observed["options"]["_resume_phase"], "parse-download")
        self.assertEqual(observed["journal"], str(self.journal))

    def test_changed_destination_does_not_run_download_or_phone(self):
        with patch.object(reader, "_context", return_value=("剧", "其他剧场", self.root)), \
             patch.object(reader, "_download_worker") as download, patch.object(reader, "_read_worker") as read:
            with self.assertRaisesRegex(ValueError, "下载目录或剧场已变化"):
                reader._pipeline_worker({"_resume_phase":"parse-download"})
        download.assert_not_called(); read.assert_not_called()

    def test_missing_journal_does_not_offer_resume(self):
        self.journal.unlink()
        self.assertIsNone(reader.status()["resume_phase"])

    def test_missing_links_go_to_collection_without_starting_phone(self):
        def prepare():
            reader._STATE.update(missing_link_episodes=[47])
        with patch.object(reader, "_context", return_value=("剧", "剧场", self.root)), \
             patch.object(reader, "_prepare_task", side_effect=prepare), \
             patch.object(reader, "_read_worker") as read, patch.object(reader, "_download_worker") as download:
            reader._pipeline_worker({"_resume_phase":"parse-download"})
        self.assertEqual(reader._STATE["phase"], "collect-links")
        self.assertEqual(reader._STATE["status"], "failed")
        read.assert_not_called(); download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
