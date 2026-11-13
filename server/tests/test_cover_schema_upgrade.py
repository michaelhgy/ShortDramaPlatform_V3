import base64
import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from PIL import Image
from server import v2_file_service as files
from server.cover_editor import CoverStore


class CoverSchemaUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.old=(files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH)
        files.WORKSPACE=self.root/'workspace';files.DATA_ROOT=self.root/'system';files.DATABASE_INITIALIZED_PATH=None
        theater=files.create_theater({'name':'原有剧场'})
        self.drama=files.create_drama({'current_name':'原有剧集','theater_id':theater['id']})['id']
        self.task=files.create_task({'source_id':'upgrade-fixture','account_name':'未配置发布平台的旧账号','drama_name':'原有剧集','planned_publish_at':''})['id']
        self.image=self.root/'旧封面.jpg';Image.new('RGB',(80,120),'orange').save(self.image)
        with closing(files.connection()) as conn:
            conn.execute('INSERT INTO drama_profiles(id,drama_id,root_path,master_path,cover_path,updated_at) VALUES(?,?,?,?,?,?)',('profile',self.drama,str(self.root),str(self.root/'master'),str(self.image),'old'))
            conn.commit()
        self.original_hash=hashlib.sha256(self.image.read_bytes()).hexdigest()
    def tearDown(self):
        files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH=self.old;self.temp.cleanup()
    def remove_feature_tables(self,version):
        with closing(files.connection()) as conn:
            for table in files.FEATURE_TABLES:conn.execute(f'DROP TABLE IF EXISTS {table}')
            conn.execute(f'PRAGMA user_version={version}');conn.commit()
        files.DATABASE_INITIALIZED_PATH=None
    def test_existing_v5_database_gets_only_additive_tables_and_original_cover(self):
        with closing(files.connection()) as conn:
            before={table:[tuple(r)for r in conn.execute('SELECT * FROM '+table)]for table in ('dramas','production_tasks','drama_profiles')}
        self.remove_feature_tables(5)
        with closing(files.connection()) as conn:
            self.assertEqual(files.SCHEMA_VERSION,conn.execute('PRAGMA user_version').fetchone()[0])
            present={r[0]for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue(files.FEATURE_TABLES<=present)
            for table,rows in before.items():self.assertEqual(rows,[tuple(r)for r in conn.execute('SELECT * FROM '+table)])
        context=CoverStore(files.WORKSPACE,files.connection).task_context(self.task)
        self.assertTrue(context['cover']['exists']);self.assertEqual(str(self.image),context['cover']['path'])
        self.assertFalse(context['sheep_cover_visible']);self.assertEqual(self.original_hash,hashlib.sha256(self.image.read_bytes()).hexdigest())
    def test_current_version_missing_tables_is_repaired_on_next_process_init(self):
        self.remove_feature_tables(6)
        self.assertEqual([],CoverStore(files.WORKSPACE,files.connection).templates()['templates'])
        with closing(files.connection()) as conn:self.assertTrue(files.FEATURE_TABLES<={r[0]for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")})
    def test_cover_read_is_independent_of_publishing_table_and_missing_platform_account(self):
        with closing(files.connection()) as conn:conn.execute('DROP TABLE v3_publish_documents');conn.commit()
        context=CoverStore(files.WORKSPACE,files.connection).task_context(self.task)
        self.assertEqual(self.drama,context['drama']['id']);self.assertTrue(context['cover']['exists'])
    def test_additive_repair_does_not_modify_any_existing_table_rows(self):
        self.remove_feature_tables(5)
        # This tests the exact additive operation used to repair a running installation.
        with closing(sqlite3.connect(files.db_path())) as conn:
            tables=[r[0]for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            before={t:conn.execute(f'SELECT * FROM "{t}"').fetchall()for t in tables}
            files._upgrade_feature_schema(conn)
            for t,rows in before.items():self.assertEqual(rows,conn.execute(f'SELECT * FROM "{t}"').fetchall())
            conn.commit()

if __name__=='__main__':unittest.main()
