import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from server.ffmpeg_templates import precompose as pc
from server.ffmpeg_templates.renderer import read, save, sha


def template():
    segment={'asset_id':'sample','asset_key':'key','start_frame':0,'end_frame':300,'phase_frame':4,
             'flatten_mode':'screen','background_dependent':False,'relative_strength_percent':95}
    return {'plan':{'frames':300,'fps':30,'canvas':[1080,2400],'seconds':10,
                    'effects':{'segments':[segment],'transitions':[]},'config':{'effect_transition_seconds':[1,2]}},
            'caches':{},'identities':{},'package_path':'unused'}


class PrecomposedRules(unittest.TestCase):
    def test_completed_period_repeats_references_and_truncates_without_gaps(self):
        from server.ffmpeg_finals.cached import repeated_parts,ending
        cache={'frames':300,'loop_frames':300,'parts':[{'start':0,'end':150,'kind':'affine','file':'a.mkv'},
                                                     {'start':150,'end':300,'kind':'affine','file':'b.mkv'}]}
        original=copy.deepcopy(cache)
        for frames in (1,149,150,299,300,301,615,901):
            rows=repeated_parts(cache,frames)
            coverage=[f for row in rows for f in range(row['start'],min(row['end'],frames))]
            self.assertEqual(list(range(frames)),coverage)
            for row in rows:self.assertEqual('a.mkv' if row['start']%300==0 else 'b.mkv',row['file'])
            self.assertIsNone(ending(cache,frames))
        self.assertEqual(original,cache)

    def test_source_dependent_repeat_moves_footage_clock_but_reuses_fixed_inputs(self):
        from server.ffmpeg_finals.cached import repeated_parts
        part={'start':0,'end':300,'kind':'source_blend','directory':'ready','render_start':0,'render_frames':300,'trim':[0,300],'inputs':['-i','ready.mkv']}
        rows=repeated_parts({'frames':300,'loop_frames':300,'parts':[part]},620)
        self.assertEqual([0,300,600],[x['render_start'] for x in rows])
        self.assertTrue(all(x['inputs']==part['inputs'] and x['trim']==part['trim'] for x in rows))

    def test_finite_ending_uses_same_fade_duration_as_original_schedule(self):
        from server.ffmpeg_finals.cached import ending
        from server.ffmpeg_finals.renderer import repeat_effects
        plan=template()['plan'];long=repeat_effects(plan,900)
        cache={'tails':{str(t['boundary_frame']):{'transition':t,'branches':[]} for t in long['effects']['transitions']}}
        for frames in (285,286,299,300,301,302,310,315,329,330,599,600,601,615):
            tail=ending(cache,frames)
            if tail is None:continue
            old=repeat_effects(plan,frames)
            matching=[t for t in old['effects']['transitions'] if t['boundary_frame']==tail['transition']['boundary_frame']]
            self.assertEqual(matching[0]['duration_frames'] if matching else 0,tail['duration'])

    def test_colour_screen_needs_rgb_transmission_and_reconstructs(self):
        # A coloured screen cannot use a single scalar alpha without changing colour.
        source=(.18,.63,.81);scenery=(.5,.2,.9);alpha=.37;screen=(.4,.08,.2)
        direct=[1-(1-(s*(1-alpha)+c*alpha))*(1-f) for s,c,f in zip(source,scenery,screen)]
        black=[1-(1-c*alpha)*(1-f) for c,f in zip(scenery,screen)]
        white=[1-(1-((1-alpha)+c*alpha))*(1-f) for c,f in zip(scenery,screen)]
        self.assertNotEqual(white[0]-black[0],white[1]-black[1])
        for s,k,w,d in zip(source,black,white,direct):self.assertAlmostEqual(k+s*(w-k),d)

    def test_nonlinear_and_background_effects_do_not_get_flattened_as_alpha(self):
        for mode in ('addition','overlay','softlight'):
            self.assertFalse(pc.affine_asset({'layers':[{'mode':mode}]}))
        self.assertFalse(pc.affine_asset({'layers':[],'background':{'kind':'bubble_filter'}}))
        self.assertTrue(pc.affine_asset({'layers':[{'mode':'normal'},{'mode':'screen'}]}))

    def test_extensions_keep_seam_clock_and_original_transition_duration(self):
        plan=template()['plan'];_,left=pc.schedule_range(plan,0,300);_,right=pc.schedule_range(plan,300,600)
        self.assertEqual(left[-1]['start'],right[0]['start'])
        self.assertEqual(left[-1]['end'],right[0]['end'])
        self.assertEqual([0,15],left[-1]['cache_trim']);self.assertEqual([15,30],right[0]['cache_trim'])
        for start,end in [(0,300),(300,600),(600,901)]:
            _,parts=pc.schedule_range(plan,start,end);covered=[]
            for p in parts:
                a,b=p.get('cache_trim',[0,p['end']-p['start']]);covered+=list(range(p['start']+a,p['start']+b))
            self.assertEqual(list(range(start,end)),covered)


class CacheLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.effects=self.root/'effects';self.effects.mkdir()
        save(self.effects/'catalog.json',{'assets':[{'id':'sample','layers':[{'mode':'screen'}]}]})
        self.template=template();self.parent=SimpleNamespace(progress=lambda *a:None)
        self.compiled=[]
        def child(folder,progress):folder.mkdir(parents=True);return SimpleNamespace(folder=folder,progress=progress)
        def compile_piece(r,t,s,p,name):
            output=r.folder/'transfer.mkv';output.write_bytes(str(p).encode());self.compiled.append((p,output));return output
        class Verify:
            def __init__(self,r,n,**kw):self.r=r;self.processed_frames=n
            def command(self,name,*args): (self.r.folder/(name+'.log')).write_text('')
        self.patches=[patch.object(pc,'EFFECTS',self.effects),patch('server.ffmpeg_templates.renderer.Renderer',side_effect=child),
                      patch.object(pc,'compile_piece',side_effect=compile_piece),patch.object(pc,'Pipeline',Verify),
                      patch.object(pc,'probe',return_value={'streams':[{'codec_type':'video','width':2160,'height':2400}]})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def prepare(self,n):return pc.ensure_cache(self.parent,self.template,n,self.root/'cache')
    def test_hit_never_renders_or_reads_original_effect_library(self):
        first=self.prepare(300);before=len(self.compiled);(self.effects/'catalog.json').unlink()
        self.assertFalse(first.get('tails'))
        second=self.prepare(200)
        self.assertTrue(second['reused']);self.assertEqual(before,len(self.compiled));self.assertEqual(first['parts'],second['parts'])
    def test_final_reads_only_original_period_from_an_expanded_cache(self):
        self.prepare(300);self.prepare(600);before=len(self.compiled);(self.effects/'catalog.json').unlink()
        manifest=next((self.root/'cache').glob('*/manifest.json'));snapshot=manifest.read_bytes()
        cache=pc.load_completed_cycle(self.template,self.root/'cache')
        self.assertEqual(300,cache['frames']);self.assertEqual(300,cache['loop_frames'])
        self.assertEqual(300,cache['parts'][-1]['end']);self.assertEqual(0,cache['preparation_seconds'])
        self.assertEqual(snapshot,manifest.read_bytes());self.assertEqual(before,len(self.compiled))
    def test_missing_cache_does_not_create_files_or_start_template_render(self):
        root=self.root/'absent'
        with self.assertRaisesRegex(ValueError,'缺少已完成'):pc.load_completed_cycle(self.template,root)
        self.assertFalse(root.exists());self.assertEqual([],self.compiled)
    def test_final_rejects_incomplete_first_period_without_repairing_it(self):
        value=self.prepare(300);manifest=Path(value['root'])/'manifest.json';v=read(manifest);v['parts'].pop();save(manifest,v)
        before=manifest.read_bytes()
        with self.assertRaisesRegex(ValueError,'不完整'):pc.load_completed_cycle(self.template,self.root/'cache')
        self.assertEqual(before,manifest.read_bytes())
    def test_longer_request_only_appends_immutable_frames(self):
        first=self.prepare(300);hashes={str(p):sha(p) for _,p in self.compiled};second=self.prepare(470)
        self.assertEqual(600,second['frames']);self.assertEqual(first['parts'],second['parts'][:len(first['parts'])])
        self.assertTrue(all(sha(p)==digest for p,digest in hashes.items()))
        self.assertFalse(second['reused'])
    def test_corruption_stops_and_does_not_replace_evidence(self):
        self.prepare(300);file=self.compiled[0][1];file.write_bytes(b'damaged');before=len(self.compiled)
        with self.assertRaisesRegex(ValueError,'损坏'):self.prepare(300)
        self.assertEqual(b'damaged',file.read_bytes());self.assertEqual(before,len(self.compiled))
    def test_interrupted_extension_keeps_previous_complete_manifest(self):
        first=self.prepare(300);manifest=Path(first['root'])/'manifest.json';previous=manifest.read_bytes()
        with patch.object(pc,'compile_piece',side_effect=RuntimeError('interrupted')):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):self.prepare(600)
        self.assertEqual(previous,manifest.read_bytes());self.assertTrue(self.prepare(300)['reused'])
    def test_recipe_change_gets_an_independent_cache(self):
        first=self.prepare(300);self.template['plan']['effects']['segments'][0]['phase_frame']=7
        second=self.prepare(300);self.assertNotEqual(first['root'],second['root']);self.assertTrue(Path(first['root']).is_dir())
    def test_manifest_frame_gaps_fail_before_render(self):
        first=self.prepare(300);manifest=Path(first['root'])/'manifest.json';value=read(manifest);value['parts'][0]['start']=1;save(manifest,value)
        with self.assertRaisesRegex(ValueError,'时间轴'):self.prepare(300)


if __name__=='__main__':unittest.main()
