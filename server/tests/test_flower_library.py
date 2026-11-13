import copy
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from PIL import Image
from server.flower_library import FlowerLibrary, initialize, validate_style

def style(color=None):
    return {'fill':{'alpha':1,'content':{'render_type':'solid','solid':{'color':color or [1,0,0],'alpha':1}}},'strokes':[],'shadows':[],'inner_shadows':[]}

class FlowerLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/'data.sqlite'
        self.local=self.root/'另一用户/本地应用';self.user=self.local/'JianyingPro/User Data';self.cache=self.user/'Cache/artistEffect'
        self.cache.mkdir(parents=True);self.machine=self.root/'machine.json'
        with closing(self.connection()) as conn:initialize(conn);conn.commit()
        self.builtin=[{'id':'11','name':'内置花字','icon':'','style':style()}]
        self.library=self.make()
    def connection(self):return sqlite3.connect(self.db)
    def make(self,settings=None,environ=None):
        return FlowerLibrary(self.root,self.connection,settings,environ=environ or {'LOCALAPPDATA':str(self.local)},builtins=self.builtin,machine_path=self.machine)
    def package(self,identifier='90001',value=None,cache=None,version='version1'):
        folder=(cache or self.cache)/identifier/version;folder.mkdir(parents=True,exist_ok=True)
        (folder/'config.json').write_text(json.dumps({'effect':{'Link':[{'type':'TextStyle'}]}}))
        (folder/'effectStyle.json').write_text(json.dumps(value or style()))
        Image.new('RGBA',(60,30),'red').save(folder/'cover_icon.png');return folder
    def tearDown(self):self.temp.cleanup()
    def test_scan_reads_actual_files_and_reports_unsupported_without_import(self):
        self.package();self.package('90002',{'fill':{'alpha':1,'content':{'render_type':'texture'}},'shadows':[],'strokes':[]})
        before=sorted(str(p)for p in self.cache.rglob('*'));result=self.library.scan()
        self.assertEqual(1,result['ready_count']);self.assertEqual(2,len(result['items']));self.assertIn('纹理',result['items'][1]['reason'])
        self.assertEqual(before,sorted(str(p)for p in self.cache.rglob('*')));self.assertEqual(1,len(self.library.load()['styles']))
    def test_other_windows_user_and_custom_install_draft_roots_are_discovered(self):
        self.package();self.assertEqual([self.cache.resolve()],self.library.discover())
        alternate=self.root/'E盘/剪映用户数据/User Data';cache=alternate/'Cache/artistEffect';self.package(cache=cache)
        self.assertEqual([cache.resolve()],self.make({'jianying_user_data_root':str(alternate)}, {'LOCALAPPDATA':str(self.root/'missing')}).discover())
        draft=alternate/'Projects/com.lveditor.draft/某草稿';draft.mkdir(parents=True)
        self.assertEqual([cache.resolve()],self.make({'jianying_draft_root':str(draft)},{'LOCALAPPDATA':str(self.root/'missing')}).discover())
        exe=alternate.parent/'Apps/5.9/JianyingPro.exe'
        self.assertEqual([cache.resolve()],self.make({'jianying_executable':str(exe)},{'LOCALAPPDATA':str(self.root/'missing')}).discover())
    def test_selected_cache_or_user_root_and_per_machine_remember(self):
        self.package();self.assertEqual(1,self.library.scan(str(self.user),True)['ready_count']);self.assertTrue(self.machine.is_file())
        self.assertEqual([self.cache.resolve()],self.make().discover())
        self.assertEqual([self.cache.resolve()],self.library.discover(str(self.cache.parent)))
        with self.assertRaisesRegex(ValueError,'没有找到'):self.library.scan(str(self.root/'missing'),True)
    def test_import_is_selective_idempotent_and_survives_cache_removal(self):
        package=self.package();self.package('90002');self.library.import_styles(['90001'])
        self.assertEqual(2,len(self.library.load()['styles']));self.library.import_styles(['90001']);self.assertEqual(2,len(self.library.load()['styles']))
        self.assertTrue(package.resolve().is_relative_to(self.root.resolve()));shutil.rmtree(package)
        loaded=self.make().load()['styles'];self.assertEqual(style(),next(s['style']for s in loaded if s['id']=='90001'))
    def test_unsupported_or_missing_selection_never_partially_imports(self):
        self.package()
        with self.assertRaises(ValueError):self.library.import_styles(['90001','missing'])
        self.assertEqual(1,len(self.library.load()['styles']))
    def test_latest_cached_package_wins(self):
        older=self.package();newer=self.package(version='version2',value=style([0,1,0]))
        os.utime(older/'effectStyle.json',(1,1));os.utime(newer/'effectStyle.json',(2,2))
        rows=self.library.import_styles(['90001'])['styles'];self.assertEqual([0,1,0],next(s for s in rows if s['id']=='90001')['style']['fill']['content']['solid']['color'])
    def test_favorites_usage_dedupe_soft_remove_and_reimport_keep_history(self):
        self.package();self.library.import_styles(['90001']);self.library.preference({'id':'90001','favorite':True})
        for _ in range(2):self.library.record_export({'ids':['90001','90001'],'eventId':'one'})
        row=next(s for s in self.library.load()['styles']if s['id']=='90001');self.assertEqual(1,row['usageCount']);self.assertTrue(row['favorite']);self.assertTrue(row['lastUsed'])
        self.library.preference({'id':'90001','enabled':False});row=next(s for s in self.library.load()['styles']if s['id']=='90001');self.assertFalse(row['enabled']);self.assertIn('style',row)
        self.library.import_styles(['90001']);row=next(s for s in self.library.load()['styles']if s['id']=='90001');self.assertTrue(row['enabled']);self.assertTrue(row['favorite']);self.assertEqual(1,row['usageCount'])
    def test_invalid_style_and_unknown_usage_are_rejected(self):
        bad=style();bad['fill']['content']['solid']['color']=[float('nan'),0,0]
        with self.assertRaises(ValueError):validate_style(bad)
        with self.assertRaises(ValueError):self.library.record_export({'ids':['unknown'],'eventId':'one'})
        self.assertEqual(0,self.library.load()['styles'][0]['usageCount'])

    def test_texture_import_embeds_pixels_and_survives_deleted_cache(self):
        textured=style();textured['fill']['content']={'render_type':'texture','texture':{'path':'gold.png','range':1,'scale':1,'angle':0,'alpha':1,'blend':'no'}}
        package=self.package(value=textured);Image.new('RGBA',(80,80),'gold').save(package/'gold.png')
        self.assertEqual(1,self.library.scan()['ready_count'])
        rows=self.library.import_styles(['90001'])['styles'];source=next(s for s in rows if s['id']=='90001')['style']['fill']['content']['texture']['source']
        self.assertTrue(source.startswith('data:image/png;base64,'));shutil.rmtree(package)
        self.assertEqual(source,next(s for s in self.make().load()['styles']if s['id']=='90001')['style']['fill']['content']['texture']['source'])

    def test_missing_outside_texture_and_special_layout_are_rejected(self):
        textured=style();textured['fill']['content']={'render_type':'texture','texture':{'path':'missing.png','range':1}}
        package=self.package(value=textured)
        self.assertEqual(0,self.library.scan()['ready_count'])
        Image.new('RGB',(8,8),'red').save(package.parent/'outside.png')
        textured['fill']['content']['texture']['path']='../outside.png'
        with self.assertRaisesRegex(ValueError,'路径无效'):validate_style(textured,package)
        textured['fill']['content']['texture'].update(path='cover_icon.png',range=20)
        with self.assertRaisesRegex(ValueError,'分格数量'):validate_style(textured,package)

    def test_texture_tint_and_atlas_counts_are_validated_without_style_ids(self):
        textured=style();content=textured['fill']['content'];content['render_type']='texture'
        content['texture']={'path':'cover_icon.png','range':4,'blend':'solid','scale':1,'alpha':.5}
        package=self.package(value=textured)
        for count in range(1,7):
            content['texture']['range']=count
            self.assertEqual(count,validate_style(textured,package)['fill']['content']['texture']['range'])
        content['solid']['color']=[float('nan'),0,0]
        with self.assertRaises(ValueError):validate_style(textured,package)

    def test_compact_library_uses_immutable_images_without_changing_stored_styles(self):
        textured=style();textured['fill']['content']={'render_type':'texture','texture':{'path':'gold.png','range':1}}
        folder=self.package(value=textured);Image.new('RGBA',(100,100),'gold').save(folder/'gold.png');self.library.import_styles(['90001'])
        full=self.library.load();source=full['styles'][-1]['style']['fill']['content']['texture']['source']
        compact=self.library.compact(copy.deepcopy(full));url=compact['styles'][-1]['style']['fill']['content']['texture']['source'];digest=url.rsplit('/',1)[1][:-4]
        self.assertTrue(url.startswith('/api/v2/cover-editor/flowers/textures/90001/'))
        import base64
        self.assertEqual(base64.b64decode(source.split(',')[1]),self.library.texture('90001',digest))
        self.assertEqual(source,self.library.load()['styles'][-1]['style']['fill']['content']['texture']['source'])
        shutil.rmtree(folder);self.assertTrue(self.library.texture('90001',digest).startswith(b'\x89PNG'))
        with self.assertRaises(FileNotFoundError):self.library.texture('90002',digest)
        with self.assertRaises(FileNotFoundError):self.library.texture('90001','0'*64)

if __name__=='__main__':unittest.main()
