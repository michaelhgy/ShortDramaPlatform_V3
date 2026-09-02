import os
import tempfile
import time
import unittest
from pathlib import Path

from server.final_engine.scripts import jianying_export_queue as queue


class FinishedExportQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "queue.json"
        queue.write_json(self.path, {"schema_version": 1, "mode": "MANUAL_CONFIRM", "jobs": [], "events": []})

    def tearDown(self):
        self.temp.cleanup()

    def job(self, *, job_id="finished-001", output="result.mp4"):
        return {"job_id": job_id, "kind": "finished_video", "status": queue.READY, "output_path": str(self.root / output)}

    def test_normal_enqueue(self):
        queue.enqueue_job(self.path, self.job())
        payload = queue.load_queue(self.path)
        self.assertEqual([item["job_id"] for item in payload["jobs"]], ["finished-001"])

    def test_duplicate_job_is_rejected(self):
        queue.enqueue_job(self.path, self.job())
        with self.assertRaisesRegex(queue.QueueError, "Duplicate job-id"):
            queue.enqueue_job(self.path, self.job())

    def test_live_lock_blocks_writer(self):
        lock = self.path.with_suffix(".json.lock")
        lock.write_text("active", encoding="ascii")
        with self.assertRaises(queue.QueueError):
            with queue._queue_lock(self.path, timeout_seconds=0):
                pass

    def test_stale_lock_is_recovered(self):
        lock = self.path.with_suffix(".json.lock")
        lock.write_text("stale", encoding="ascii")
        old = time.time() - 121
        os.utime(lock, (old, old))
        queue.enqueue_job(self.path, self.job())
        self.assertFalse(lock.exists())
        self.assertEqual(1, len(queue.load_queue(self.path)["jobs"]))

    def test_invalid_schema_is_rejected(self):
        queue.write_json(self.path, {"schema_version": 9, "mode": "MANUAL_CONFIRM", "jobs": []})
        with self.assertRaisesRegex(queue.QueueError, "Unsupported or malformed queue"):
            queue.enqueue_job(self.path, self.job())

    def test_invalid_mode_is_rejected(self):
        queue.write_json(self.path, {"schema_version": 1, "mode": "UNKNOWN", "jobs": []})
        with self.assertRaisesRegex(queue.QueueError, "Unsupported queue mode"):
            queue.enqueue_job(self.path, self.job())
