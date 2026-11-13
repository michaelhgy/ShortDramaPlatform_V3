import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.ffmpeg_templates.renderer import Renderer,sha


class SceneryTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.r=Renderer.__new__(Renderer);self.r.folder=Path(self.temp.name)
        self.r.progress=lambda *a:None;self.r.timings=[];self.r.caches={};self.r.encoder='h264_nvenc'

    def test_repeated_full_segments_and_partial_tail_are_prepared_once(self):
        a=self.r.folder/'a.bin';a.write_bytes(b'a')
        b=self.r.folder/'b.bin';b.write_bytes(b'b')
        materials=[{'id':sha(p),'path':str(p),'name':p.name,'frames':n} for p,n in [(a,30),(b,45)]]
        sequence=[{'id':materials[i]['id'],'frames':n} for i,n in [(0,30),(1,45),(0,30),(1,12)]]
        plan={'frames':117,'tracks':[{'side':'top','height':96,'center':45,'feather':60,'materials':materials,'sequence':sequence}]}
        prepared=[];joined=[]
        def run(name,inputs,graph,output,frames,extra):
            prepared.append((name,frames,graph,extra));return output
        def join(name,paths,frames,height):
            joined.extend(paths);return self.r.folder/'timeline.mp4'
        with patch.object(self.r,'run',side_effect=run),patch.object(self.r,'check_scenery'),patch.object(self.r,'join_scenery',side_effect=join):
            self.r.scenery(plan,preview=False)
        self.assertEqual([p[1] for p in prepared],[30,45,12])
        self.assertEqual(joined[0],joined[2]);self.assertNotEqual(joined[1],joined[3])
        self.assertTrue(all('out_range=tv' in p[2] and '-color_range' in p[3] for p in prepared))

    def test_short_timeline_is_rejected_before_effects(self):
        bad={'streams':[{'codec_type':'video','width':1080,'height':540,'avg_frame_rate':'30/1','nb_frames':'1860'}]}
        with patch('server.ffmpeg_templates.renderer.probe',return_value=bad):
            with self.assertRaisesRegex(RuntimeError,'预期5400帧'):
                self.r.check_scenery('top_timeline.mp4',5400,540)

    def test_unplayed_candidate_can_be_missing_without_blocking_render(self):
        source=self.r.folder/'played.bin';source.write_bytes(b'played')
        materials=[{'id':sha(source),'path':str(source),'name':source.name,'frames':30},
                   {'id':'not-played','path':str(self.r.folder/'missing.bin'),'name':'missing.bin','frames':600}]
        plan={'frames':30,'tracks':[{'side':'top','height':96,'center':45,'feather':60,'materials':materials,
                                    'sequence':[{'id':materials[0]['id'],'frames':30}]}]}
        with patch.object(self.r,'run',return_value=self.r.folder/'part.mp4') as run,patch.object(self.r,'check_scenery'),patch.object(self.r,'join_scenery',return_value=self.r.folder/'timeline.mp4'):
            self.r.scenery(plan,preview=False)
        self.assertEqual(1,run.call_count)

    def test_concat_copies_packets_without_frame_reset_filter_and_checks_decode(self):
        calls=[]
        def command(name,args,frames,**kw):
            calls.append(args)
            (self.r.folder/(name+'.log')).write_text('')
            return frames
        with patch.object(self.r,'command',side_effect=command),patch.object(self.r,'check_scenery') as check:
            self.r.join_scenery('top',[self.r.folder/'a.mp4',self.r.folder/'b.mp4'],90,540)
        self.assertIn('copy',calls[0]);self.assertNotIn('-filter_complex_script',calls[0])
        self.assertIn('null',calls[1]);check.assert_called_once()

    def test_decode_failure_cannot_pass_on_header_count_alone(self):
        def command(name,args,frames,**kw):
            (self.r.folder/(name+'.log')).write_text('')
            return 89
        with patch.object(self.r,'command',side_effect=command),patch.object(self.r,'check_scenery'):
            with self.assertRaisesRegex(RuntimeError,'89/90'):
                self.r.join_scenery('top',[self.r.folder/'a.mp4'],90,540)


if __name__=='__main__':unittest.main()
