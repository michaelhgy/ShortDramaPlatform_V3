import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from server.ffmpeg_templates.config import DEFAULTS
from server.ffmpeg_templates.renderer import sha
from server.ffmpeg_templates.service import TemplateMaker
from server.ffmpeg_templates.scenery_usage import scheduled_scenery
from server.scenery.service import SceneryLibrary


class ActualSceneryUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'system'
        self.library=SceneryLibrary(self.root,self.data);self.library.ready.mkdir(parents=True)
        self.sources={}
        for i in range(40):
            p=self.library.ready/f'风景{i+1}.mp4';p.write_bytes(f'unique scenery {i}'.encode())
            identity=sha(p);self.sources[identity]=p;st=p.stat()
            with self.library.connect() as c:
                c.execute("INSERT INTO assets(id,job_id,ordinal,name,path,sha256,frames,width,height,size,mtime,state,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (str(i),'',i,p.name,str(p),identity,600,360,200,st.st_size,st.st_mtime_ns,'ready',''))
        self.maker=self.new_maker()
        self.maker.save_config(dict(DEFAULTS,duration_seconds=60,duration_jitter=0,scenery_count=20,scenery_count_jitter=0,scenery_usage_limit=1))

    def new_maker(self):
        def render(folder,plan,progress):
            p=folder/'preview.mp4';p.write_bytes(str(plan['seed']).encode());return p
        maker=TemplateMaker(self.root,self.data,render=render);maker.start=lambda:None
        return maker

    def create(self,count=1):self.maker.create(count,str(uuid.uuid4()))
    def jobs(self):
        with self.maker.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY rowid')]
    def ids(self,table,job=None):
        with self.maker.connect() as c:
            rows=c.execute(f'SELECT source_id FROM {table}'+(' WHERE job_id=?' if job else ''),(job,) if job else ()).fetchall()
        return {r[0] for r in rows}
    def played(self,job):
        return {s['id'] for s in scheduled_scenery(json.loads(job['plan']))}
    def candidates(self,job):
        return {m['id'] for t in json.loads(job['plan'])['tracks'] for m in t['materials']}

    def test_sixty_seconds_twenty_candidates_only_six_are_reserved_counted_and_retired(self):
        self.create();job=self.jobs()[0];played=self.played(job);unused=self.candidates(job)-played
        self.assertEqual(20,len(self.candidates(job)));self.assertEqual(6,len(played));self.assertEqual(14,len(unused))
        self.assertEqual(played,self.ids('reservations',job['id']))
        available={a['sha256']:a for a in self.library.ready_assets()}
        self.assertTrue(all(available[i]['reserved']==0 and available[i]['remaining']==1 for i in unused))
        self.maker.run_next();self.assertEqual('done',self.jobs()[0]['status'])
        self.assertEqual(played,self.ids('usages',job['id']));self.assertEqual(set(),self.ids('reservations'))
        self.assertTrue(all(not self.sources[i].exists() for i in played))
        self.assertTrue(all(self.sources[i].exists() for i in unused))

    def test_batch_reserves_only_played_sources_and_later_jobs_survive_unused_candidate_deletion(self):
        self.create(4);jobs=self.jobs();expected=set()
        for job in jobs:
            used=self.played(job);self.assertFalse(expected&used);expected|=used
        self.assertEqual(24,len(expected));self.assertEqual(expected,self.ids('reservations'))
        for _ in jobs:self.maker.run_next()
        self.assertTrue(all(j['status']=='done' for j in self.jobs()))
        self.assertEqual(expected,self.ids('usages'));self.assertEqual(16,sum(p.exists() for p in self.sources.values()))

    def test_failure_and_retry_only_reacquire_the_same_played_sources(self):
        self.create();job=self.jobs()[0];expected=self.played(job);original=self.maker.render
        self.maker.render=lambda *a:(_ for _ in ()).throw(RuntimeError('fixture render failure'))
        self.maker.run_next();self.assertFalse(self.ids('usages'));self.assertFalse(self.ids('reservations'))
        unused=self.candidates(job)-expected
        # A formerly selected but unplayed candidate can disappear or exhaust its quota.
        with self.maker.connect() as c:
            for identity in unused:c.execute('INSERT INTO usages VALUES(?,?)',('other-success',identity))
        for identity in unused:self.sources[identity].unlink()
        self.maker.retry(job['id']);self.assertEqual(expected,self.ids('reservations',job['id']))
        self.assertEqual(job['plan'],self.jobs()[0]['plan'])
        self.maker.render=original;self.maker.run_next();self.assertEqual('done',self.jobs()[0]['status'])
        self.assertEqual(expected,self.ids('usages',job['id']))

    def test_unused_missing_or_changed_files_do_not_fail_this_template(self):
        self.create();job=self.jobs()[0];unused=list(self.candidates(job)-self.played(job))
        self.sources[unused[0]].unlink();self.sources[unused[1]].write_bytes(b'replacement')
        self.maker.run_next();self.assertEqual('done',self.jobs()[0]['status'])
        self.assertEqual(b'replacement',self.sources[unused[1]].read_bytes())

    def test_changed_played_file_fails_without_usage_or_retirement(self):
        self.create();job=self.jobs()[0];played=self.played(job)
        self.sources[next(iter(played))].write_bytes(b'changed')
        self.maker.run_next();self.assertEqual('error',self.jobs()[0]['status'])
        self.assertFalse(self.ids('usages'));self.assertFalse(self.ids('reservations'))
        self.assertTrue(all(p.exists() for p in self.sources.values()))

    def test_only_positive_frames_count_and_looped_materials_count_once(self):
        self.maker.save_config(dict(self.maker.config(),scenery_count=4,scenery_group_gap_percent=[0,100]))
        with self.library.connect() as c:c.execute('UPDATE assets SET frames=60')
        self.create();job=self.jobs()[0];plan=json.loads(job['plan'])
        self.assertGreater(sum(len(t['sequence']) for t in plan['tracks']),4)
        self.assertEqual(4,len(self.played(job)));self.maker.run_next()
        self.assertEqual(4,len(self.ids('usages',job['id'])))

    def test_partial_two_frame_tail_counts_as_one_use(self):
        with self.library.connect() as c:c.execute('UPDATE assets SET frames=899')
        self.create();job=self.jobs()[0];plan=json.loads(job['plan'])
        self.assertTrue(all(t['sequence'][-1]['frames']==2 for t in plan['tracks']))
        self.maker.run_next();self.assertEqual(self.played(job),self.ids('usages',job['id']))

    def test_old_waiting_over_reservation_is_trimmed_but_historical_usage_is_preserved(self):
        self.maker.save_config(dict(self.maker.config(),scenery_usage_limit=5));self.create(2)
        historical,waiting=self.jobs()
        with self.maker.connect() as c:
            c.execute("UPDATE jobs SET status='done' WHERE id=?",(historical['id'],))
            c.execute('DELETE FROM reservations WHERE job_id=?',(historical['id'],))
            for identity in self.candidates(historical):c.execute('INSERT INTO usages VALUES(?,?)',(historical['id'],identity))
            for identity in self.candidates(waiting):c.execute('INSERT OR IGNORE INTO reservations VALUES(?,?)',(waiting['id'],identity))
        history=self.ids('usages',historical['id']);self.assertEqual(20,len(self.ids('reservations',waiting['id'])))
        self.maker=self.new_maker()
        self.assertEqual(self.played(waiting),self.ids('reservations',waiting['id']))
        self.assertEqual(history,self.ids('usages',historical['id']))

    def test_settlement_does_not_charge_old_extra_reservations(self):
        self.create();job=self.jobs()[0]
        with self.maker.connect() as c:
            for identity in self.candidates(job):c.execute('INSERT OR IGNORE INTO reservations VALUES(?,?)',(job['id'],identity))
        self.maker.run_next();self.assertEqual(self.played(job),self.ids('usages',job['id']))

    def test_missing_played_reservation_preserves_publication_and_retry_is_idempotent(self):
        self.create();job=self.jobs()[0];identity=next(iter(self.played(job)))
        with self.maker.connect() as c:c.execute('DELETE FROM reservations WHERE job_id=? AND source_id=?',(job['id'],identity))
        self.maker.run_next();self.assertEqual('error',self.jobs()[0]['status']);self.assertFalse(self.ids('usages'))
        published=self.maker.output/(job['display_name']+'.mp4');self.assertTrue(published.is_file())
        before=published.read_bytes();self.maker.retry(job['id']);self.maker.run_next()
        self.assertEqual('done',self.jobs()[0]['status']);self.assertEqual(before,published.read_bytes())
        self.assertEqual(self.played(job),self.ids('usages',job['id']))

    def test_cancel_and_crash_recovery_release_only_reserved_usage(self):
        self.create();one=self.jobs()[0];self.maker.cancel(one['id'])
        self.assertFalse(self.ids('reservations'));self.assertFalse(self.ids('usages'))
        self.create();two=self.jobs()[-1]
        with self.maker.connect() as c:c.execute("UPDATE jobs SET status='running' WHERE id=?",(two['id'],))
        self.maker.recover();self.assertFalse(self.ids('reservations'));self.assertFalse(self.ids('usages'))

    def test_zero_length_candidate_is_not_a_dependency(self):
        sources=list(self.sources.items())[:2]
        track={'materials':[{'id':i,'path':str(p)} for i,p in sources],
               'sequence':[{'id':sources[0][0],'frames':1},{'id':sources[1][0],'frames':0}]}
        self.assertEqual([sources[0][0]],[m['id'] for m in scheduled_scenery({'tracks':[track,copy.deepcopy(track)]})])


if __name__=='__main__':unittest.main()
