import copy
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from server.ffmpeg_templates.config import DEFAULTS,RANGES,validate
from server.ffmpeg_templates.parameter_info import field_info
from server.ffmpeg_templates.service import TemplateMaker
from server.ffmpeg_templates.renderer import make_plan,sha,draw,read,BORDERS


class ParameterGuidanceTests(unittest.TestCase):
    def expanded(self):
        return dict(copy.deepcopy(DEFAULTS),duration_seconds=3600,duration_jitter=400,
                    scenery_count=40,scenery_count_jitter=12,scenery_usage_limit=2000,template_usage_limit=5000,
                    height_large_percent=[35,45],height_small_percent=[10,15],mask_percent=[0,100],feather_percent=[0,100],
                    sticker_alpha_percent=95,overlay_sticker_count=[128,128],photo_layer_count=[36,36],photo_usage_limit=2000,
                    effect_count=[25,30],effect_segment_seconds=[1,240],effect_pair_percent=[40,70],
                    effect_transition_seconds=[3,8],border_width=[1,30])

    def test_recommendations_do_not_reject_or_clamp_valid_values(self):
        value=self.expanded();self.assertEqual(value,validate(value))
        self.assertGreater(value['border_width'][1],RANGES['border_width'][1])
        self.assertGreater(value['overlay_sticker_count'][0],RANGES['overlay_sticker_count'][1])

    def test_usage_limit_service_does_not_keep_an_independent_old_cap(self):
        with tempfile.TemporaryDirectory() as t:
            maker=TemplateMaker(Path(t),Path(t)/'system')
            value=self.expanded();self.assertEqual(value,maker.save_config(value));self.assertEqual(value,maker.config())

    def test_only_intrinsic_units_types_and_order_are_rejected(self):
        invalid=[dict(duration_seconds=0),dict(duration_seconds=5,duration_jitter=5),dict(duration_jitter=-1),
                 dict(scenery_count=3),dict(scenery_count_jitter=3),dict(photo_usage_limit=0),
                 dict(photo_layer_count=[4,3]),dict(effect_count=[1.5,2]),dict(feather_percent=[-1,5]),
                 dict(sticker_alpha_percent=101),dict(border_width=[1,1081]),dict(height_large_percent=[0,10]),
                 dict(width=720),dict(fps=True),dict(photo_layer_enabled=1),dict(duration_seconds=2**53)]
        for change in invalid:
            with self.subTest(change=change),self.assertRaises(ValueError):validate(dict(DEFAULTS,**change))

    def test_zero_opacity_and_zero_feather_are_valid(self):
        value=dict(DEFAULTS,sticker_alpha_percent=0,overlay_sticker_opacity_percent=0,
                   photo_layer_opacity_percent=0,feather_percent=[0,0],effect_strength_percent=[0,0],effect_pair_percent=[0,0])
        self.assertEqual(value,validate(value));self.assertEqual(0,draw(random.Random(1),24,[1,1],2))

    def test_each_editable_field_has_label_purpose_and_intrinsic_rule(self):
        info=field_info();self.assertEqual(set(DEFAULTS)-{'width','height','fps'},set(info))
        for key,item in info.items():
            with self.subTest(key=key):
                self.assertTrue(item['label']);self.assertGreater(len(item['description']),20);self.assertTrue(item['rule'])

    def test_parameter_api_marks_ranges_as_suggestions_and_returns_help(self):
        from server.ffmpeg_templates.http import handle
        captured={};handler=SimpleNamespace(_json=lambda status,data:captured.update(status=int(status),data=data))
        with patch('server.ffmpeg_templates.http.get_maker',return_value=SimpleNamespace(config=lambda:dict(DEFAULTS))):
            self.assertTrue(handle(handler,'GET','/api/v3/template-generation/config'))
        self.assertEqual(200,captured['status']);self.assertEqual(RANGES,captured['data']['suggested_ranges'])
        self.assertEqual(field_info(),captured['data']['fields'])

    def test_wide_border_ranges_keep_valid_crop_coordinates(self):
        from tools.ffmpeg_overlay_lab.side_strip_library.library import make_plan as border_plan
        catalogue=read(BORDERS/'catalog.json')
        for width_range in ([1,1],[15,30],[1080,1080]):
            for seed in range(15):
                p=border_plan(catalogue,seed,width_range=width_range)
                a,b=p['sides'];self.assertGreaterEqual(abs(a['crop_x']-b['crop_x']),p['minimum_position_separation'])
                for side in p['sides']:
                    self.assertTrue(width_range[0]<=side['width']<=width_range[1])
                    self.assertTrue(0<=side['crop_x']<=p['scaled_size'][0]-side['width'])

    def test_short_segments_and_long_transitions_plan_without_overlapping_windows(self):
        with tempfile.TemporaryDirectory() as t:
            materials=[]
            for i in range(8):
                p=Path(t)/str(i);p.write_bytes(bytes([i]))
                materials.append(dict(id=sha(p),path=str(p),name=p.name,frames=(i+2)*30,size=1,mtime_ns=p.stat().st_mtime_ns))
            config=dict(DEFAULTS,duration_seconds=5,duration_jitter=0,scenery_count=4,
                        height_large_percent=[35,45],height_small_percent=[10,15],mask_percent=[0,100],
                        feather_percent=[0,0],effect_count=[25,30],effect_segment_seconds=[1,1],
                        effect_transition_seconds=[7,9],border_width=[20,30])
            for seed in range(12):
                p=make_plan(validate(config),materials,seed);segments=p['effects']['segments']
                self.assertEqual(150,p['frames']);self.assertTrue(all(x['feather']==0 for x in p['tracks']))
                for a,b,transition in zip(segments,segments[1:],p['effects']['transitions']):
                    self.assertLessEqual(transition['duration_frames'],min(a['end_frame']-a['start_frame'],b['end_frame']-b['start_frame']))
                for a,b in zip(p['effects']['transitions'],p['effects']['transitions'][1:]):
                    self.assertLessEqual(a['end_frame'],b['start_frame'])


if __name__=='__main__':unittest.main()
