import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from server import v2_file_service as files
from server import task_center_service as center


class PlannedDateTests(unittest.TestCase):
    def test_input_date_and_legacy_time_are_normalized_without_timezone_conversion(self):
        self.assertEqual('',files.parse_planned_publish_at(''))
        self.assertEqual('2026-10-26',files.parse_planned_publish_at('2026-10-26'))
        self.assertEqual('2026-10-26',files.parse_planned_publish_at('2026-10-26T23:50'))
        self.assertEqual('2026-10-26',files.parse_planned_publish_at('2026-10-26 08:00:00'))
        with self.assertRaises(ValueError):files.parse_planned_publish_at('2026-02-30')
        with self.assertRaises(ValueError):files.parse_planned_publish_at('2026-10-26Tinvalid')

    def test_same_day_old_clock_does_not_override_creation_or_manual_priority(self):
        conn=sqlite3.connect(':memory:');self.addCleanup(conn.close);conn.row_factory=sqlite3.Row
        conn.executescript('''CREATE TABLE production_tasks(id TEXT,planned_publish_at TEXT,created_at TEXT,manual_order INTEGER,release_status TEXT);
          CREATE TABLE template_jobs(task_id TEXT);
          CREATE TABLE production_video_tasks(task_id TEXT,id TEXT,status TEXT);
          CREATE TABLE export_jobs(id TEXT,subject_type TEXT,subject_id TEXT);
          CREATE TABLE export_attempts(job_id TEXT,status TEXT,attempt_no INTEGER);''')
        rows=[('earlier-start','2026-10-26T22:00','2026-10-25T08:00',0,''),('earlier-clock','2026-10-26T08:00','2026-10-25T09:00',0,''),('tomorrow','2026-10-27','2026-10-24T08:00',0,''),('no-date','','2026-10-23T08:00',0,'')]
        conn.executemany('INSERT INTO production_tasks VALUES(?,?,?,?,?)',rows)
        conn.executemany('INSERT INTO template_jobs VALUES(?)',[(r[0],) for r in rows])
        self.assertEqual(['earlier-start','earlier-clock','tomorrow','no-date'],center._ordered_units(conn)[0])
        self.assertEqual(['earlier-start','earlier-clock','tomorrow','no-date'],[r[0] for r in conn.execute('SELECT id FROM production_tasks t ORDER BY '+center._DEFAULT_UNIT_ORDER)])
        conn.execute("UPDATE production_tasks SET manual_order=1 WHERE id='tomorrow'")
        self.assertEqual('tomorrow',center._ordered_units(conn)[0][0])

    def test_reading_legacy_plan_does_not_rewrite_original_record(self):
        original=(files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH)
        with tempfile.TemporaryDirectory() as directory:
            files.WORKSPACE=Path(directory)/'workspace';files.DATA_ROOT=Path(directory)/'system';files.DATABASE_INITIALIZED_PATH=None
            try:
                task=files.create_task({'source_id':'date-check','account_name':'日期账号','drama_name':'日期剧','planned_publish_at':'2026-10-26'})
                with closing(files.connection()) as conn:
                    conn.execute("UPDATE production_tasks SET planned_publish_at='2026-10-26T18:37' WHERE id=?",(task['id'],));conn.commit()
                self.assertEqual('2026-10-26',files.get_task_details(task['id'])['planned_publish_at'])
                with closing(files.connection()) as conn:self.assertEqual('2026-10-26T18:37',conn.execute('SELECT planned_publish_at FROM production_tasks WHERE id=?',(task['id'],)).fetchone()[0])
            finally:files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH=original
