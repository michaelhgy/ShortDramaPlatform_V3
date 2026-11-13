import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from server import operations_collection as ops
from server import optimization_analysis as analysis


class OptimizationAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'isolated.sqlite'
        with closing(self.connect()) as c:
            c.executescript("CREATE TABLE accounts(id TEXT,channel_id TEXT,status TEXT); INSERT INTO accounts VALUES('a','u','正常'),('b','v','正常'),('c','retired','注销'); CREATE TABLE v3_publish_documents(kind TEXT,key TEXT,content TEXT,updated_at TEXT,PRIMARY KEY(kind,key));")
            ops.initialize(c)
            for idx, uid, text in [('1','u','第一行。第二行。'),('2','v','作品分析：\n第一行。<br>第二行。'),('3','u','不同的分析'),('4','retired','注销账号分析')]:
                c.execute("INSERT INTO v3_work_notices(id,uid,export_id,detail_json,feed_json,first_seen_at,last_seen_at) VALUES(?,?,?,?,'{}','2026-11-04','2026-11-05')", (idx,uid,idx,json.dumps({'reason':text},ensure_ascii=False)))
            c.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def test_grouping_is_exact_read_only_and_includes_unmatched_notices(self):
        with closing(self.connect()) as c:
            before = c.total_changes
            result = analysis.groups(c)
            self.assertEqual(c.total_changes,before)
            self.assertEqual(result['configuration'],{'version':0,'mappings':[]})
            self.assertEqual(len(result['groups']),3)
            group = result['groups'][0]
            self.assertEqual(group['record_count'],2)
            self.assertEqual(group['account_count'],2)
            self.assertEqual(len(group['variants']),2)
            self.assertNotEqual(analysis.analysis_key('第一行。第二行。'),analysis.analysis_key('第一行。第二行。补充'))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_publish_documents').fetchone()[0],0)

    def test_free_labels_persist_conflict_preserves_and_reset_only_removes_mapping(self):
        with closing(self.connect()) as c:
            original = [tuple(r) for r in c.execute('SELECT * FROM v3_work_notices ORDER BY id')]
            key = analysis.groups(c)['groups'][0]['key']
            for version,tag in enumerate(['同质化','ALL','__proto__','待归类']):
                result=analysis.save_mapping(c,{'key':key,'tag':tag,'expected_version':version})
                c.commit()
                self.assertEqual(result['configuration']['mappings'][0]['tag'],tag)
        with closing(self.connect()) as c:
            self.assertEqual(analysis.configuration(c)['version'],4)
            with self.assertRaises(analysis.MappingConflict):
                analysis.save_mapping(c,{'key':key,'tag':'过时修改','expected_version':0})
            c.rollback()
            self.assertEqual(analysis.configuration(c)['mappings'][0]['tag'],'待归类')
            result = analysis.save_mapping(c,{'key':key,'tag':None,'expected_version':4})
            c.commit()
            self.assertEqual(result['configuration'],{'version':5,'mappings':[]})
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM v3_work_notices ORDER BY id')],original)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v3_optimization_action_settings').fetchone()[0],0)

    def test_bad_requests_do_not_save(self):
        with closing(self.connect()) as c:
            key=analysis.groups(c)['groups'][0]['key']
            for change in [{'tag':''},{'tag':' '*2},{'tag':'字'*81},{'tag':3},{'expected_version':True},{'expected_version':-1},{'key':'0'*64},{'extra':1}]:
                with self.subTest(change=change),self.assertRaises(ValueError):
                    analysis.save_mapping(c,{'key':key,'tag':'自由标签','expected_version':0,**change})
                c.rollback()
            self.assertEqual(analysis.configuration(c)['version'],0)

    def test_saved_group_survives_retired_source_account(self):
        with closing(self.connect()) as c:
            key=analysis.groups(c)['groups'][0]['key']
            analysis.save_mapping(c,{'key':key,'tag':'自由标签','expected_version':0})
            c.execute("UPDATE accounts SET status='注销'")
            c.commit()
            groups=analysis.groups(c)['groups']
            self.assertEqual(len(groups),3)
            group=next(group for group in groups if group['key']==key)
            self.assertEqual(group['record_count'],2)

    def test_http_routes_read_save_and_reject_stale_version(self):
        import io
        from unittest.mock import Mock, patch
        from server import v2_file_service as service
        handler=service.Handler.__new__(service.Handler)
        handler.path='/api/v3/operations-dashboard/optimization/analysis'
        handler._json=Mock()
        with patch.object(service,'connection',self.connect):
            service.Handler.do_GET(handler)
            status,data=handler._json.call_args.args
            self.assertEqual(status,200)
            payload={'key':data['groups'][0]['key'],'tag':'自由标签','expected_version':0}
            for expected_status in (200,409):
                body=json.dumps(payload).encode()
                handler.headers={'Content-Length':str(len(body))}
                handler.rfile=io.BytesIO(body)
                service.Handler.do_POST(handler)
                self.assertEqual(handler._json.call_args.args[0],expected_status)

if __name__ == '__main__':
    unittest.main()
