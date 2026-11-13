import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from unittest.mock import patch

from server import v2_file_service as service
from tools.seed_recent_operations import seed, put
from tools.reprofile_operations_samples import load_reference, reprofile, protected_digest


class OperationsReprofileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patches = [patch.object(service,'WORKSPACE',self.root/'workspace'),
                        patch.object(service,'DATA_ROOT',self.root/'data'),
                        patch.object(service,'DATABASE_INITIALIZED_PATH',None)]
        for p in self.patches:
            p.start()
        self.conn = service.connection()
        seed(self.conn,date(2026,10,31),days=10,account_count=8)
        original = dict(self.conn.execute('SELECT * FROM v3_video_posts LIMIT 1').fetchone())
        original.update(id='original-real-snapshot',post_id='original-real-post',source_kind='xiao_v_cache',view=2468)
        put(self.conn,'v3_video_posts',original)
        attempt = dict(self.conn.execute('SELECT * FROM v2_revenue_collection_attempts LIMIT 1').fetchone())
        attempt.update(id='original-qingning-attempt',adapter_key='qingning',amount='17.23')
        put(self.conn,'v2_revenue_collection_attempts',attempt)
        self.conn.execute('UPDATE v2_daily_revenues SET source_attempt_id=?,amount=? WHERE account_id=? AND revenue_date=?',
                          (attempt['id'],'17.23',attempt['account_id'],attempt['revenue_date']))
        self.conn.commit()
        self.reference = self.root/'reference.sqlite'
        with closing(sqlite3.connect(self.reference)) as ref:
            ref.executescript('''CREATE TABLE accounts(id TEXT,nickname TEXT,theater_id TEXT,created_at TEXT);
                CREATE TABLE theaters(id TEXT,name TEXT);
                CREATE TABLE v2_revenue_video_details(account_id TEXT,source_video_id TEXT,revenue_date TEXT,
                    video_views INTEGER,drama_views INTEGER,gross_revenue TEXT);''')
            ref.execute('INSERT INTO theaters VALUES(?,?)',('t','青柠剧场'))
            ref.executemany('INSERT INTO accounts VALUES(?,?,?,?)',[(f'old{i}',f'历史{i}','t','2026-08-01') for i in range(2)])
            for i in range(20):
                ref.executemany('INSERT INTO v2_revenue_video_details VALUES(?,?,?,?,?,?)',[
                    (f'old{i%2}',f'v{i}','2026-08-01',3 if i<15 else 1000,999999,'0.00' if i<15 else '10.00'),
                    (f'old{i%2}',f'v{i}','2026-08-03',1 if i<15 else 80,999999,'0.00' if i<15 else '2.50')])
            ref.commit()
        self.profiles,self.reference_stats=load_reference(self.reference)

    def tearDown(self):
        self.conn.close()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def run_reprofile(self):
        with self.conn:
            return reprofile(self.conn,self.profiles,date(2026,11,1),days=10)

    def test_read_only_reference_pairs_preserve_calendar_gaps_and_ignore_drama_views(self):
        self.assertEqual(40,self.reference_stats['observation_rows'])
        self.assertEqual(20,self.reference_stats['videos'])
        profile=self.profiles['old0'][0]
        self.assertEqual({0,2},set(profile['points']))
        self.assertEqual((3,0),profile['points'][0])

    def test_preserves_original_snapshots_catalog_assets_and_work_links(self):
        before=protected_digest(self.conn)
        assets={r['post_id']:json.loads(r['payload_json'])['drama_id'] for r in self.conn.execute("SELECT * FROM v3_video_posts WHERE source_kind='development_seed'")}
        result=self.run_reprofile()
        self.assertTrue(result['protected_records_unchanged'])
        self.assertEqual(before,protected_digest(self.conn))
        self.assertEqual(assets,{r['post_id']:json.loads(r['payload_json'])['drama_id'] for r in self.conn.execute("SELECT * FROM v3_video_posts WHERE source_kind='development_seed'")})
        self.assertEqual(2468,self.conn.execute("SELECT view FROM v3_video_posts WHERE post_id='original-real-post'").fetchone()[0])

    def test_daily_metrics_reconcile_and_do_not_predate_simulated_publication(self):
        self.run_reprofile()
        self.assertEqual([],self.conn.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM v3_video_post_daily d JOIN v3_video_posts p ON p.post_id=d.post_id WHERE d.source_kind='development_seed' AND d.stat_date<substr(p.post_time,1,10)").fetchone()[0])
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM v3_video_posts p WHERE p.source_kind='development_seed' AND p.view<>(SELECT sum(d.view) FROM v3_video_post_daily d WHERE d.post_id=p.post_id AND d.source_kind='development_seed')").fetchone()[0])
        self.assertEqual(0,self.conn.execute("SELECT count(*) FROM v3_video_account_daily a WHERE a.source_kind='development_seed' AND a.view<>coalesce((SELECT sum(d.view) FROM v3_video_post_daily d WHERE d.account_id=a.account_id AND d.stat_date=a.stat_date AND d.source_kind='development_seed'),0)").fetchone()[0])

    def test_revenue_is_paired_has_many_zeroes_and_monthly_totals_are_not_split(self):
        self.run_reprofile()
        rows=list(self.conn.execute("SELECT * FROM v3_revenue_details WHERE source_kind='development_seed'"))
        self.assertTrue(any(r['video_views']>0 and float(r['gross_revenue'])==0 for r in rows))
        self.assertTrue(all(r['drama_views']==0 for r in rows))
        for r in rows:
            if float(r['gross_revenue'])>0:
                # Fixture large day: 1000 views / 10 yuan; later day: 80 views / 2.50 yuan.
                base_views,base_cents=(1000,1000) if r['video_views']>500 else (80,250)
                self.assertLess(abs(float(r['gross_revenue'])*100-r['video_views']/base_views*base_cents),3)
        periods=list(self.conn.execute("SELECT * FROM v3_revenue_account_periods WHERE source_kind='development_seed'"))
        self.assertTrue(any(r['period_type']=='month_cumulative' for r in periods))
        self.assertTrue(all(r['include_in_analysis']==1 for r in periods))
        for r in periods:
            if r['period_type']=='day':
                total=sum(float(d['gross_revenue']) for d in rows if d['account_id']==r['account_id'] and d['detail_date']==r['period_end'])
                self.assertAlmostEqual(float(r['amount']),total,places=2)

    def test_repeat_replaces_developer_keys_without_growing_or_erasing_history(self):
        self.run_reprofile()
        before={t:self.conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['v3_video_posts','v3_video_post_daily','v3_revenue_account_periods','v2_daily_revenues','v2_revenue_collection_attempts']}
        self.run_reprofile()
        after={t:self.conn.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in before}
        self.assertEqual(before,after)

    def test_detected_catalog_change_rolls_back_entire_replacement(self):
        before=protected_digest(self.conn)
        count=self.conn.execute('SELECT count(*) FROM v3_video_post_daily').fetchone()[0]
        self.conn.executescript('''CREATE TRIGGER unexpected_catalog_change AFTER INSERT ON v3_video_account_daily
            BEGIN UPDATE accounts SET nickname=nickname||'unexpected' WHERE id=new.account_id; END;''')
        with self.assertRaisesRegex(ValueError,'事务应回滚'):
            self.run_reprofile()
        self.assertEqual(before,protected_digest(self.conn))
        self.assertEqual(count,self.conn.execute('SELECT count(*) FROM v3_video_post_daily').fetchone()[0])


if __name__=='__main__':
    unittest.main()
