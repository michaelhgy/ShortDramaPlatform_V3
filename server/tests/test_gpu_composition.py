import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server.ffmpeg_finals.pipeline import Pipeline
from server.ffmpeg_templates import precompose as pc
from server.ffmpeg_templates.renderer import save,sha
from server.ffmpeg_finals.cached import render_cached
from server.ffmpeg_finals.gpu_transfer import supports
from server.ffmpeg_finals.renderer import validate_output_video


class InputAndCompatibilityTests(unittest.TestCase):
    def test_repeated_source_check_hashes_once_but_changes_invalidate(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source';source.write_bytes(b'original')
            digest=sha(source)
            with patch.object(pc,'sha',wraps=pc.sha) as hashing:
                self.assertTrue(pc.verified_file(source,digest))
                self.assertTrue(pc.verified_file(source,digest))
                self.assertEqual(hashing.call_count,1)
                source.write_bytes(b'changed source')
                self.assertFalse(pc.verified_file(source,digest))
                self.assertEqual(hashing.call_count,2)

    def test_mutation_during_hash_never_enters_verified_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source';source.write_bytes(b'original')
            digest=sha(source)
            def changing(path):
                path.write_bytes(b'changed source')
                return digest
            with patch.object(pc,'sha',side_effect=changing):
                self.assertFalse(pc.verified_file(source,digest))

    def test_legacy_cache_remains_read_only_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);template={'plan':{'frames':3},'caches':{}}
            version=pc.LEGACY_VERSIONS[0];key=pc.cache_key(template,version)
            root=base/key;root.mkdir();video=root/'transfer.mkv';video.write_bytes(b'legacy')
            manifest={'version':version,'key':key,'frames':3,'parts':[
                {'kind':'affine','file':video.name,'start':0,'end':3,'identities':{video.name:sha(video)}}]}
            save(root/'manifest.json',manifest)
            snapshot=(root/'manifest.json').read_bytes()
            result=pc.load_completed_cycle(template,base)
            self.assertEqual(result['version'],version)
            self.assertTrue(result['reused'])
            self.assertEqual(result['preparation_seconds'],0)
            self.assertEqual(snapshot,(root/'manifest.json').read_bytes())
            self.assertFalse((base/pc.cache_key(template)).exists())
            # A corrupt new cache must not be silently replaced by an old one.
            save(base/pc.cache_key(template)/'manifest.json',{'version':'invalid'})
            with self.assertRaisesRegex(ValueError,'版本不匹配'):pc.load_completed_cycle(template,base)

    def test_fps_order_only_moves_duplication_for_low_rate(self):
        for rate in ('24/1','24000/1001'):
            graph=pc.main_graph(300,source_fps=rate)
            self.assertLess(graph.index('scale='),graph.index('fps=30'))
            self.assertLess(graph.index('format=gbrp'),graph.index('fps=30'))
        for rate in ('30/1','60/1',None,'0/0'):
            graph=pc.main_graph(300,source_fps=rate)
            self.assertLess(graph.index('fps=30'),graph.index('scale='))


class ValidationTests(unittest.TestCase):
    def test_correct_resolution_cannot_hide_stretched_display_aspect(self):
        video={'width':1080,'height':2400,'avg_frame_rate':'30/1','nb_frames':'1500',
               'sample_aspect_ratio':'1:1','display_aspect_ratio':'9:20'}
        validate_output_video(video,1500)
        # This is the actual GPU regression: correct pixels/frame count,
        # but the encoder inherited the three-panel atlas's pixel aspect.
        for sar,dar in [('3:1','27:20'),('1:1','27:20'),(None,None)]:
            with self.subTest(sar=sar,dar=dar):
                with self.assertRaisesRegex(RuntimeError,'显示比例不符'):
                    validate_output_video({**video,'sample_aspect_ratio':sar,'display_aspect_ratio':dar},1500)

    def make(self,folder):
        r=SimpleNamespace(folder=Path(folder),hardware={'vulkan_h264':True},progress=lambda *a:None)
        return Pipeline(r,30,load_assets=False)

    def test_full_validation_decodes_audio_and_video_without_gpu_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.make(folder);calls=[]
            def command(name,args,*rest):
                calls.append((name,args));(p.r.folder/(name+'.log')).write_text('')
                p.processed_frames=30
            p.command=command;p.validate('output.mp4')
            self.assertEqual([c[0] for c in calls],['decode_check'])
            self.assertNotIn('-hwaccel',calls[0][1])
            self.assertIn('0:a?',calls[0][1])
            self.assertIn('-xerror',calls[0][1])

    def test_corrupt_media_does_not_get_hidden_as_hardware_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.make(folder)
            with patch.object(p,'command',side_effect=RuntimeError('Invalid NAL unit')) as command:
                with self.assertRaisesRegex(RuntimeError,'Invalid NAL'):p.validate('bad.mp4')
                self.assertEqual(command.call_count,1)

    def test_truncated_decode_cannot_pass_on_clean_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            p=self.make(folder)
            def command(name,*args):
                (p.r.folder/(name+'.log')).write_text('');p.processed_frames=29
            p.command=command
            with self.assertRaisesRegex(RuntimeError,'帧数不完整'):p.validate('truncated.mp4')


class TransferCompatibilityTests(unittest.TestCase):
    def job(self):
        return {'source_width':720,'source_height':1280,'source_pix_fmt':'yuv420p',
                'source_sar':'1:1','source_color_space':'bt709','source_color_trc':'bt709',
                'source_field_order':'progressive','source_codec_name':'h264',
                'source_path':'source.mp4','source_fps':'30/1','frames':30,'has_audio':True}

    def test_unusual_picture_metadata_keeps_cpu_renderer(self):
        self.assertTrue(supports(self.job()))
        for change in ({'source_sar':'4:3'},{'source_color_trc':'smpte2084'},
                       {'source_pix_fmt':'yuv420p10le'},{'source_rotation':90},
                       {'source_field_order':'tt'},{'source_color_space':None},
                       {'source_width':None},{'still_image':True}):
            with self.subTest(change=change):self.assertFalse(supports({**self.job(),**change}))

    def setup_render(self,folder,codec):
        r=SimpleNamespace(folder=Path(folder),hardware={
            'vulkan_transfer':True,'vulkan_h264':True,'vulkan_hevc':True},
            progress=lambda *a:None,encoder='h264_nvenc')
        part={'kind':'affine','start':0,'end':30,'file':'transfer.mkv'}
        if codec:part['codec']=codec
        return r,{'root':folder,'frames':30,'loop_frames':30,'parts':[part]}

    def test_legacy_cache_uses_cpu_decode_new_hevc_cache_uses_gpu(self):
        for codec,decoders in ((None,1),('h264',1),('hevc',2)):
            with self.subTest(codec=codec),tempfile.TemporaryDirectory() as folder:
                r,cache=self.setup_render(folder,codec)
                with patch.object(Pipeline,'command') as command:
                    result,pipeline=render_cached(r,self.job(),cache)
                args=command.call_args.args[1]
                self.assertEqual(args.count('-hwaccel'),decoders)
                self.assertEqual(result.name,'final_gpu.mp4')
                self.assertEqual(pipeline.acceleration['cache_decode'],'vulkan' if codec=='hevc' else 'cpu')

    def test_device_failure_keeps_failed_file_and_retries_original_graph(self):
        with tempfile.TemporaryDirectory() as folder:
            r,cache=self.setup_render(folder,'hevc');calls=[]
            def command(name,args,*rest):
                calls.append((name,args))
                if name=='compose_gpu':
                    (r.folder/'final_gpu.mp4').write_bytes(b'failed attempt')
                    raise RuntimeError('Vulkan device lost')
            with patch.object(Pipeline,'command',side_effect=command):
                result,_=render_cached(r,self.job(),cache)
            self.assertEqual([c[0] for c in calls],['compose_gpu','compose'])
            self.assertNotIn('-hwaccel',calls[1][1])
            self.assertEqual(result.name,'final.mp4')
            self.assertEqual((r.folder/'final_gpu.mp4').read_bytes(),b'failed attempt')
            self.assertTrue((r.folder/'acceleration_fallback.json').is_file())

    def test_bad_media_is_not_retried_as_device_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            r,cache=self.setup_render(folder,'hevc')
            error='Stream mapping: h264 -> libplacebo (vulkan)\nInvalid NAL unit'
            with patch.object(Pipeline,'command',side_effect=RuntimeError(error)) as command:
                with self.assertRaisesRegex(RuntimeError,'Invalid NAL'):
                    render_cached(r,self.job(),cache)
                self.assertEqual(command.call_count,1)


if __name__=='__main__':unittest.main()
