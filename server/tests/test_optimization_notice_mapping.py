import json
import sqlite3
import unittest

from tools.replace_optimization_demo_notices import CONFIG, apply_replacement, plan_replacement


class NoticeReplacementTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute('CREATE TABLE v3_video_post_punishments(id TEXT PRIMARY KEY,source_kind TEXT,punish_state TEXT,payload_json TEXT)')

    def tearDown(self):
        self.conn.close()

    def add(self, notice_id, source, meta, state='推荐曝光减少'):
        self.conn.execute('INSERT INTO v3_video_post_punishments VALUES(?,?,?,?)', (notice_id, source, state, json.dumps(meta, ensure_ascii=False)))

    def test_only_marked_legacy_demo_notices_change_and_repeat_is_a_noop(self):
        self.add('dev', 'development_seed', {'generated': True, 'notice': '开发场景：旧标签', 'severity': '严重', 'detectedDate': '2026-10-31'})
        self.add('ui', 'simulation_ui', {'simulation': True})
        self.add('cache', 'xiao_v_cache', {'notice': '平台缓存原始内容'})
        self.add('manual', 'development_seed', {'generated': True, 'notice': '人工已经改写的内容'})
        original = {row[0]: row for row in self.conn.execute('SELECT * FROM v3_video_post_punishments')}
        plan = plan_replacement(self.conn)
        self.assertEqual({item['id'] for item in plan}, {'dev', 'ui'})
        with self.conn:
            apply_replacement(self.conn, plan)
        current = {row[0]: row for row in self.conn.execute('SELECT * FROM v3_video_post_punishments')}
        self.assertEqual(current['cache'], original['cache'])
        self.assertEqual(current['manual'], original['manual'])
        self.assertEqual(len(current), len(original))
        for notice_id in ('dev', 'ui'):
            meta = json.loads(current[notice_id][3])
            self.assertEqual(current[notice_id][2], '')
            self.assertNotIn('severity', meta)
            self.assertEqual(meta['noticeMappingVersion'], CONFIG['version'])
            self.assertTrue(any(rule['tag'] == meta['simplifiedReason'] and rule['analysis'] == meta['notice'] for rule in CONFIG['rules']))
        self.assertEqual(json.loads(current['dev'][3])['detectedDate'], '2026-10-31')
        self.assertEqual(plan_replacement(self.conn), [])

    def test_stale_plan_rolls_back_all_changes(self):
        for notice_id in ('a', 'b'):
            self.add(notice_id, 'development_seed', {'generated': True, 'notice': '开发场景：旧标签'})
        self.conn.commit()
        plan = plan_replacement(self.conn)
        self.conn.execute("UPDATE v3_video_post_punishments SET punish_state='手动改动' WHERE id='b'")
        self.conn.commit()
        before = self.conn.execute('SELECT * FROM v3_video_post_punishments ORDER BY id').fetchall()
        with self.assertRaises(RuntimeError), self.conn:
            apply_replacement(self.conn, plan)
        self.assertEqual(before, self.conn.execute('SELECT * FROM v3_video_post_punishments ORDER BY id').fetchall())

    def test_registry_has_exactly_five_distinct_rules_and_only_originality_counts_as_homogeneous(self):
        rules = CONFIG['rules']
        self.assertEqual(len(rules), 5)
        self.assertEqual(len({rule['id'] for rule in rules}), 5)
        self.assertEqual([rule['tag'] for rule in rules if rule['homogeneous']], ['原创优化'])


if __name__ == '__main__':
    unittest.main()
