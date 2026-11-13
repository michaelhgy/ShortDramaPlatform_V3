import hashlib
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from tools.seed_recent_operations import seed, put
from tools.bind_operations_visual_assets import bind


class VisualAssetBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [patch.object(service, 'WORKSPACE', root/'workspace'), patch.object(service, 'DATA_ROOT', root/'system-data'),
                        patch.object(service, 'DATABASE_INITIALIZED_PATH', None)]
        for p in self.patches: p.start()
        self.conn = service.connection()
        seed(self.conn, date(2026,10,31), days=10, account_count=14)
        self.asset = root/'visual.png';self.asset.write_bytes(b'unchanged local fixture')
        self.hash = hashlib.sha256(self.asset.read_bytes()).hexdigest()
        theater = self.conn.execute('SELECT id FROM theaters LIMIT 1').fetchone()[0]
        for i in range(12):
            aid=f'real{i:02d}'
            put(self.conn,'accounts',dict(id=aid,nickname=f'真实昵称{i}',channel_id=f'channel{i}',theater_id=theater,
                sub_theater_name='',status='正常',reporting_date='',registration_date='',notes='',created_at='now',updated_at='now'))
            self.conn.execute('INSERT INTO v3_catalog_avatars VALUES(?,?,?,?)',(aid,'',str(self.asset),'now'))
        for i,r in enumerate(self.conn.execute('SELECT id FROM dramas LIMIT 3').fetchall()):
            put(self.conn,'drama_profiles',dict(id=f'profile{i}',drama_id=r['id'],root_path=str(root),master_path=str(root),cover_path=str(self.asset),updated_at='now'))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_merge_preserves_metrics_and_uses_unique_real_identities(self):
        before = self.conn.execute('SELECT sum(view) FROM v3_video_account_daily').fetchone()[0]
        works = self.conn.execute('SELECT count(*) FROM v3_video_posts').fetchone()[0]
        result = bind(self.conn)
        self.conn.commit()
        self.assertTrue(result['changed'])
        self.assertEqual(12,result['real_accounts'])
        self.assertEqual(12,result['bound_profiles'])
        self.assertEqual(before,self.conn.execute('SELECT sum(view) FROM v3_video_account_daily').fetchone()[0])
        self.assertEqual(works,self.conn.execute('SELECT count(*) FROM v3_video_posts').fetchone()[0])
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM accounts WHERE channel_id LIKE 'dev-%'").fetchone()[0])
        self.assertEqual([],self.conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(0,self.conn.execute('SELECT count(*) FROM v3_video_posts p JOIN accounts a ON a.id=p.account_id WHERE p.uid<>a.channel_id OR p.account_name<>a.nickname').fetchone()[0])

    def test_rebinding_covers_keeps_asset_files_and_revenue_links(self):
        bind(self.conn);self.conn.commit()
        self.assertEqual(self.hash,hashlib.sha256(self.asset.read_bytes()).hexdigest())
        self.assertEqual(0,self.conn.execute('SELECT count(*) FROM v3_revenue_details r LEFT JOIN drama_profiles p ON p.drama_id=r.matched_drama_id WHERE p.id IS NULL').fetchone()[0])
        self.assertEqual(0,self.conn.execute('SELECT count(*) FROM (SELECT account_id,post_time,count(*) n FROM v3_video_posts GROUP BY account_id,post_time HAVING n>1)').fetchone()[0])
        self.assertFalse(bind(self.conn)['changed'])

    def test_unexpected_dependency_rolls_back_in_callers_transaction(self):
        fake=self.conn.execute("SELECT id FROM accounts WHERE channel_id LIKE 'dev-%' LIMIT 1").fetchone()[0]
        self.conn.execute('CREATE TABLE protected_record(account_id TEXT)')
        self.conn.execute('INSERT INTO protected_record VALUES(?)',(fake,));self.conn.commit()
        before=self.conn.execute('SELECT count(*) FROM accounts').fetchone()[0]
        try:
            with self.conn:
                bind(self.conn)
        except ValueError:
            pass
        else:
            self.fail('unexpected dependency was silently removed')
        self.assertEqual(before,self.conn.execute('SELECT count(*) FROM accounts').fetchone()[0])
        self.assertEqual(1,self.conn.execute('SELECT count(*) FROM accounts WHERE id=?',(fake,)).fetchone()[0])
