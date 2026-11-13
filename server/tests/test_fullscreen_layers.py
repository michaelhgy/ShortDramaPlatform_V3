import copy
import json
import tempfile
import unittest
import uuid
import subprocess
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from server.ffmpeg_templates.config import DEFAULTS,validate
from server.ffmpeg_templates import fullscreen_layers as layers
from server.ffmpeg_templates.service import TemplateMaker
from server.ffmpeg_templates.renderer import sha


class FullscreenLayersTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.photo_root=self.root/'生成资源/真人图片';self.photo_root.mkdir(parents=True)
        for i in range(8):Image.new('RGB',(120+i,180),(i*27,110,190)).save(self.photo_root/f'{i}.png')
        self.materials=[]
        for i in range(8):
            p=self.root/f'{i}.mp4';p.write_bytes(bytes([i]))
            self.materials.append({'id':sha(p),'path':str(p),'name':p.name,'size':1,'mtime_ns':p.stat().st_mtime_ns,'frames':(i+4)*30})
        def render(folder,plan,progress):
            layers.prepare(folder/'layers',plan)
            p=folder/'preview.mp4';p.write_bytes(str(plan['seed']).encode());return p
        self.maker=TemplateMaker(self.root,self.root/'system',render=render)
        self.maker.scan=lambda:(self.materials,[]);self.maker.start=lambda:None
        self.maker.save_config(dict(DEFAULTS,duration_seconds=10,duration_jitter=0,scenery_count=4,
                                    scenery_usage_limit=100,photo_layer_enabled=True,photo_layer_count=[6,6],photo_usage_limit=1))

    def tearDown(self):self.temp.cleanup()
    def create(self,n=1):return self.maker.create(n,str(uuid.uuid4()))
    def plan(self):
        with self.maker.connect() as c:return json.loads(c.execute('SELECT plan FROM jobs ORDER BY rowid DESC LIMIT 1').fetchone()[0])

    def test_success_counts_once_retires_files_but_keeps_rendered_layer(self):
        self.create();plan=self.plan();photos=layers.photo_sources(plan)
        self.assertEqual(6,len({p['id'] for p in photos}))
        self.maker.run_next();job=self.maker.snapshot()['jobs'][0]
        self.assertEqual('done',job['status']);self.assertTrue(Path(job['package_path'],'layers/combined.png').is_file())
        self.assertTrue(all(not Path(p['path']).exists() for p in photos))
        with self.maker.connect() as c:
            self.assertEqual(6,c.execute('SELECT COUNT(*) FROM photo_usages').fetchone()[0])
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM photo_reservations').fetchone()[0])
            self.assertEqual(6,c.execute("SELECT COUNT(*) FROM photo_sources WHERE state='retired'").fetchone()[0])
        self.assertFalse(self.maker.run_next())

    def test_batch_shortage_rolls_back_all_jobs_and_reservations(self):
        with self.assertRaisesRegex(ValueError,'真人图片'):self.create(2)
        with self.maker.connect() as c:
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0])
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM photo_reservations').fetchone()[0])

    def test_failed_job_releases_quota_and_retry_preserves_recipe(self):
        self.create();plan=self.plan();render=self.maker.render
        self.maker.render=lambda *args:(_ for _ in ()).throw(RuntimeError('expected failure'))
        self.maker.run_next();job=self.maker.snapshot()['jobs'][0]
        self.assertEqual('error',job['status'])
        with self.maker.connect() as c:
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM photo_usages').fetchone()[0])
            self.assertEqual(0,c.execute('SELECT COUNT(*) FROM photo_reservations').fetchone()[0])
        self.assertEqual(8,len(list(self.photo_root.glob('*.png'))))
        self.maker.retry(job['id']);self.assertEqual(plan,self.plan())
        self.maker.render=render;self.maker.run_next();self.assertEqual('done',self.maker.snapshot()['jobs'][0]['status'])

    def test_cancel_and_crash_recovery_release_reservations(self):
        self.create();job=self.maker.snapshot()['jobs'][0]['id'];self.maker.cancel(job)
        self.create();job=next(j for j in self.maker.snapshot()['jobs'] if j['status']=='waiting')['id']
        with self.maker.connect() as c:c.execute("UPDATE jobs SET status='running' WHERE id=?",(job,))
        self.maker.recover()
        with self.maker.connect() as c:self.assertEqual(0,c.execute('SELECT COUNT(*) FROM photo_reservations').fetchone()[0])
        self.assertEqual(8,len(list(self.photo_root.glob('*.png'))))

    def test_changed_picture_fails_without_consumption_or_deletion(self):
        self.create();p=Path(layers.photo_sources(self.plan())[0]['path']);p.write_bytes(b'replacement')
        self.maker.run_next();self.assertEqual('error',self.maker.snapshot()['jobs'][0]['status'])
        self.assertEqual(b'replacement',p.read_bytes())
        with self.maker.connect() as c:self.assertEqual(0,c.execute('SELECT COUNT(*) FROM photo_usages').fetchone()[0])

    def test_pending_reservation_prevents_cleanup_after_limit_reduced(self):
        self.maker.save_config(dict(self.maker.config(),photo_layer_count=[8,8],photo_usage_limit=2))
        self.create(2);self.maker.run_next()
        self.maker.save_config(dict(self.maker.config(),photo_usage_limit=1))
        self.assertEqual(8,len(list(self.photo_root.glob('*.png'))))
        waiting=next(j for j in self.maker.snapshot()['jobs'] if j['status']=='waiting')
        self.maker.cancel(waiting['id']);self.assertEqual(0,len(list(self.photo_root.glob('*.png'))))

    def test_blocked_deletion_reports_error_then_refresh_retries(self):
        self.create()
        original=Path.unlink
        def locked(p,*a,**k):
            if p.parent==self.photo_root:raise PermissionError('fixture locked picture')
            return original(p,*a,**k)
        with patch.object(Path,'unlink',locked):self.maker.run_next()
        with self.maker.photos.connect() as c:
            self.assertEqual(6,sum(bool(r['error']) for r in self.maker.photos.items(c)))
        self.maker.photos.refresh();self.assertEqual(2,len(list(self.photo_root.glob('*.png'))))

    def test_reimported_content_does_not_reset_success_count(self):
        self.create();p=Path(layers.photo_sources(self.plan())[0]['path']);saved=p.read_bytes()
        self.maker.run_next();p.write_bytes(saved)
        inventory=self.maker.photos.refresh()
        self.assertEqual(0,next(a for a in inventory if a['id']==sha(p))['remaining'])
        with self.maker.photos.connect() as c:
            self.assertNotIn(sha(p),{r['id'] for r in self.maker.photos.candidates(c,1)})

    def test_sticker_pool_disjoint_and_opacity_is_applied_to_whole_layer(self):
        catalog=layers.sticker_catalog()
        old=json.loads(Path('tools/ffmpeg_overlay_lab/sticker_library/v1_20261018/inventory.json').read_text(encoding='utf8'))
        self.assertFalse(set(old['resources'])&{a['resource_id'] for a in catalog})
        self.maker.save_config(dict(self.maker.config(),photo_layer_enabled=False,overlay_sticker_enabled=True,overlay_sticker_count=[48,48]))
        self.create();plan=self.plan();p=layers.prepare(self.root/'overlay',plan)
        with Image.open(p) as im:
            self.assertEqual((1080,2400),im.size)
            self.assertLessEqual(im.getchannel('A').getextrema()[1],5)
        self.assertEqual(48,len(plan['fullscreen_layers']['stickers']['placements']))

    def test_partition_covers_canvas_for_variable_counts_without_distortion(self):
        self.assertEqual([[0,0,540,800],[540,0,1080,800],[0,800,540,1600],[540,800,1080,1600],[0,1600,540,2400],[540,1600,1080,2400]],layers.cells(6))
        for n in range(1,65):
            cells=layers.cells(n);self.assertEqual(n,len(cells))
            self.assertEqual(1080*2400,sum((r-x)*(b-y) for x,y,r,b in cells))
        for change in ({'photo_layer_enabled':1},{'photo_layer_count':[7,6]},{'photo_usage_limit':0}):
            with self.assertRaises(ValueError):validate(dict(DEFAULTS,**change))

    def test_full_and_regional_precomposition_keep_overlay_in_center(self):
        from server.ffmpeg_templates.precompose import base_graph,_full_base_graph
        from server.tool_resolver import resolve_ffmpeg
        from server.ffmpeg_templates.renderer import hidden
        cache={}
        scene=self.root/'scene.png';Image.new('RGB',(1080,600),'green').save(scene)
        mask=self.root/'mask.png';Image.new('L',(1080,600),128).save(mask)
        sticker=self.root/'stick.png';Image.new('RGBA',(1080,960)).save(sticker)
        overlay=self.root/'full.png';Image.new('RGBA',(1080,2400),(255,0,255,128)).save(overlay)
        cache={'scenery':[{'video':str(scene),'mask':str(mask)}]*2,'stickers':str(sticker),'fullscreen_overlay':str(overlay)}
        plan={'frames':300,'tracks':[{'height':600}]*2,'stickers':{'start_frame':0},'config':{'sticker_alpha_percent':80}}
        results=[]
        for i,fn in enumerate((base_graph,_full_base_graph)):
            args,g=fn(plan,cache,0,1,'black');script=self.root/f'graph{i}.txt';script.write_text(g,encoding='utf8')
            p=subprocess.run([str(resolve_ffmpeg()),'-v','error','-filter_complex_threads','2',*args,
                              '-filter_complex_script',str(script),'-map','[base]','-frames:v','1',
                              '-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,**hidden())
            self.assertEqual(0,p.returncode,p.stderr.decode(errors='replace'))
            results.append(p.stdout)
        self.assertEqual(results[0],results[1])
        center=(1200*1080+540)*3
        self.assertEqual(bytes([128,0,128]),results[0][center:center+3])


if __name__=='__main__':unittest.main()
