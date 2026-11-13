from __future__ import annotations

import hashlib
import http.client
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from server.template_library import TemplateLibrary
from server.template_library_http import stream_video


class TemplateLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.business_db = self.root / "business.db"
        with closing(self.business()) as conn:
            conn.executescript("""
                CREATE TABLE production_tasks(id TEXT PRIMARY KEY,account_name TEXT,drama_name TEXT,release_status TEXT,cleanup_status TEXT);
                CREATE TABLE accounts(id TEXT,nickname TEXT);
                CREATE TABLE dramas(id TEXT,current_name TEXT);
                CREATE TABLE drama_aliases(drama_id TEXT,alias_name TEXT);
                INSERT INTO accounts VALUES('account-a','账号A'),('account-b','账号B');
                INSERT INTO dramas VALUES('drama-a','剧甲'),('drama-b','剧乙');
                INSERT INTO drama_aliases VALUES('drama-a','甲剧旧名');
                INSERT INTO production_tasks VALUES('a','账号A','剧甲','unregistered','active'),
                    ('b','账号B','剧甲','unregistered','active'),('c','账号B','剧乙','unregistered','active'),
                    ('alias','账号B','甲剧旧名','unregistered','active');
            """)
            conn.commit()
        self.probe_calls = []

        def probe(path, key):
            self.probe_calls.append(path)
            return 30.0, "1080x2400", ""

        self.library = TemplateLibrary(self.root / "workspace", self.root / "state", self.business, probe)
        self.library.directory.mkdir(parents=True)
        self.video = self.library.directory / "模板一.mp4"
        self.video.write_bytes(b"test fixture video")
        self.library.refresh()
        self.template_id = hashlib.sha256(self.video.read_bytes()).hexdigest()

    def business(self):
        conn = sqlite3.connect(self.business_db)
        conn.row_factory = sqlite3.Row
        return conn

    def tearDown(self):
        self.temp.cleanup()

    def test_current_schema_restores_missing_defaults_after_data_reset(self):
        with closing(self.library.connect()) as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            conn.execute('DELETE FROM library_settings')
            conn.commit()
        with closing(self.library.connect()) as conn:
            self.assertEqual(self.library.usage_limit(conn), 20)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], version)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM templates').fetchone()[0], 1)

    def test_existing_usage_limit_is_preserved_without_writing_on_connect(self):
        self.library.set_usage_limit(37)
        with closing(self.library.connect()) as conn:
            self.assertEqual(self.library.usage_limit(conn), 37)
            self.assertEqual(conn.total_changes, 0)

    def test_select_persists_without_incrementing_usage(self):
        self.library.select("a", self.template_id)
        fresh = TemplateLibrary(self.library.workspace, self.library.data_root, self.business, self.library.probe)
        result = fresh.catalogue("a")
        self.assertEqual(self.template_id, result["selected_template_id"])
        self.assertEqual(0, result["items"][0]["usage_count"])

    def test_same_drama_other_account_is_blocked_but_other_drama_allowed(self):
        self.library.select("a", self.template_id)
        with self.assertRaisesRegex(ValueError, "账号A"):
            self.library.select("b", self.template_id)
        self.library.select("c", self.template_id)

    def test_drama_alias_cannot_bypass_conflict(self):
        self.library.select("a", self.template_id)
        with self.assertRaisesRegex(ValueError, "账号A"):
            self.library.select("alias", self.template_id)

    def test_cancel_unstarted_selection_releases_scope(self):
        self.library.select("a", self.template_id)
        self.library.select("a", None)
        self.library.select("b", self.template_id)

    def test_deleted_task_releases_reservation(self):
        self.library.select("a", self.template_id)
        with closing(self.business()) as conn:
            conn.execute("DELETE FROM production_tasks WHERE id='a'")
            conn.commit()
        self.library.catalogue("b")
        self.library.select("b", self.template_id)

    def test_successful_output_is_idempotent_and_locks_selection(self):
        self.library.select("a", self.template_id)
        output = self.library.workspace / "成片.mp4"
        output.write_bytes(b"verified output fixture")
        self.library.record_output("a", "output-1", output)
        self.library.record_output("a", "output-1", output)
        result = self.library.catalogue("a")
        self.assertEqual(1, result["items"][0]["usage_count"])
        self.assertTrue(result["selection_locked"])
        with self.assertRaisesRegex(ValueError, "已有成片"):
            self.library.select("a", None)
        with self.assertRaisesRegex(ValueError, "账号A"):
            self.library.select("b", self.template_id)

    def test_missing_or_external_output_cannot_increment(self):
        self.library.select("a", self.template_id)
        with self.assertRaises(ValueError):
            self.library.record_output("a", "missing", self.library.workspace / "missing.mp4")
        with self.assertRaises(ValueError):
            self.library.record_output("a", "external", self.business_db)
        self.assertEqual(0, self.library.catalogue("a")["items"][0]["usage_count"])

    def test_repeated_refresh_reuses_probe_and_rename_preserves_identity(self):
        self.library.select("a", self.template_id)
        self.library.refresh()
        self.assertEqual(1, len(self.probe_calls))
        renamed = self.video.with_name("改名后.MP4")
        self.video.rename(renamed)
        self.library.refresh()
        result = self.library.catalogue("a")
        self.assertEqual(self.template_id, result["selected_template_id"])
        self.assertTrue(result["items"][0]["available"])
        self.assertEqual(renamed, self.library.media(self.template_id))

    def test_missing_and_replaced_template_is_unavailable(self):
        self.video.write_bytes(b"new content")
        self.assertEqual([],self.library.catalogue("a")["items"])
        with self.assertRaises(ValueError):
            self.library.select("a", self.template_id)
        with self.assertRaises(ValueError):
            self.library.media(self.template_id)

    def test_registered_task_cannot_change_selection(self):
        with closing(self.business()) as conn:
            conn.execute("UPDATE production_tasks SET release_status='registered' WHERE id='a'")
            conn.commit()
        with self.assertRaisesRegex(ValueError, "已结束"):
            self.library.select("a", self.template_id)

    def test_empty_library_remains_empty(self):
        self.video.unlink()
        self.library.refresh()
        result = self.library.catalogue("a")
        self.assertEqual([], result['items'])

    def test_deleted_file_hidden_even_before_refresh(self):
        self.library.select('a',self.template_id)
        self.video.unlink()
        self.assertEqual([],self.library.catalogue('a')['items'])
        self.library.refresh()
        self.assertEqual([],self.library.catalogue('a')['items'])

    def test_usage_limit_hides_completed_templates(self):
        self.library.set_usage_limit(1);self.library.select('a',self.template_id)
        output=self.library.workspace/'output.mp4';output.write_bytes(b'output')
        self.library.record_output('a','out',output)
        self.assertEqual(1,self.library.catalogue('a')['items'][0]['usage_count'])
        self.assertEqual([],self.library.catalogue('c')['items'])
        with self.assertRaisesRegex(ValueError,'上限'):self.library.select('c',self.template_id)
        self.library.set_usage_limit(2)
        self.assertEqual(1,len(self.library.catalogue('a')['items']))

    def test_drama_count_survives_task_delete_and_same_drama_recreation(self):
        self.library.set_usage_limit(1);self.library.select('a',self.template_id)
        output=self.library.workspace/'output.mp4';output.write_bytes(b'output')
        for i in range(5):self.library.record_output('a',f'output-{i}',output)
        self.assertEqual(1,self.library.catalogue('a')['items'][0]['usage_count'])
        with closing(self.business()) as c:
            c.execute("DELETE FROM production_tasks WHERE id='a'");c.execute("UPDATE production_tasks SET account_name='账号A' WHERE id='alias'");c.commit()
        # alias is the same drama/account in a different card.
        self.library.select('alias',self.template_id)
        self.library.record_output('alias','output-6',output)
        self.assertEqual(1,self.library.catalogue('alias')['items'][0]['usage_count'])
        with self.assertRaisesRegex(ValueError,'上限'):self.library.select('c',self.template_id)

    def test_manual_delete_moves_video_and_sidecar_keeps_output_history(self):
        self.video.with_suffix('.template.json').write_text('{}')
        self.library.select('a',self.template_id)
        output=self.library.workspace/'output.mp4';output.write_bytes(b'keep')
        self.library.record_output('a','out',output)
        result=self.library.delete(self.template_id)
        self.assertFalse(self.video.exists());self.assertTrue(output.is_file())
        self.assertTrue((Path(result['trash_path'])/self.video.name).is_file())
        self.assertTrue((Path(result['trash_path'])/self.video.with_suffix('.template.json').name).is_file())
        self.library.refresh();self.assertEqual([],self.library.catalogue('a')['items'])
        with closing(self.library.connect()) as conn:self.assertEqual(1,conn.execute('SELECT COUNT(*) FROM outputs').fetchone()[0])

    def test_existing_video_identity_not_changed_by_refresh(self):
        old = self.video.stat()
        before = self.video.read_bytes()
        self.library.refresh()
        self.assertEqual(before, self.video.read_bytes())
        self.assertEqual(old.st_mtime_ns, self.video.stat().st_mtime_ns)


class TemplateMediaRangeTests(unittest.TestCase):
    def test_real_http_range_full_suffix_and_invalid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "video.mp4"
            path.write_bytes(b"0123456789")

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    stream_video(self, path)

                def log_message(self, *_args):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for header, status, body in [(None, 200, b"0123456789"), ("bytes=2-5", 206, b"2345"), ("bytes=-3", 206, b"789"), ("bytes=30-", 416, b""), ("bytes=-0", 416, b"")]:
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
                    conn.request("GET", "/", headers={"Range": header} if header else {})
                    response = conn.getresponse()
                    self.assertEqual(status, response.status)
                    self.assertEqual(body, response.read())
                    conn.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
