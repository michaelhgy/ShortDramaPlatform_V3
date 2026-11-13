import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from server.publishing.service import PublishingService, initialize


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PublishingCleanupGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = self.temp.name + "\\test.db"

        with closing(self.connect()) as conn:
            conn.execute("""CREATE TABLE production_tasks(
                id TEXT PRIMARY KEY, release_status TEXT, actual_release_time TEXT,
                process_cleanup_at TEXT, raw_cleanup_at TEXT, cleanup_status TEXT, updated_at TEXT, delivery_completed_at TEXT
            )""")
            conn.execute("INSERT INTO production_tasks VALUES(?,?,?,?,?,?,?,?)",
                         ("task-a", "unregistered", "", "", "", "active", "", ""))
            conn.execute("CREATE TABLE accounts(id TEXT,channel_id TEXT,status TEXT)")
            initialize(conn)
            conn.commit()

    def tearDown(self):
        self.temp.cleanup()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def test_verified_official_publication_starts_cleanup_clock(self):
        service = PublishingService(self.connect, lambda task: {}, FakeClient)
        with patch("server.publishing.publisher.Publisher.refresh", return_value={"items": [{"key": "k", "status": "success"}]}), \
             patch("server.operations_collection.associate_publications"), \
             patch("server.operations_collection.publication_completion", return_value={
                 "complete": True, "latest_delivery_unix": 1800000000, "matched": 1, "total": 1
             }):
            result = service.refresh_publication("task-a")

        self.assertTrue(result["cleanup_gate"]["complete"])
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM production_tasks WHERE id='task-a'").fetchone()
        self.assertEqual("registered", row["release_status"])
        self.assertEqual("2027-01-15 16:00:00", row["delivery_completed_at"])
        self.assertEqual("", row["actual_release_time"])
        self.assertEqual("2027-01-16 16:00:00", row["process_cleanup_at"])
        self.assertEqual("2027-01-22 16:00:00", row["raw_cleanup_at"])


if __name__ == "__main__":
    unittest.main()
