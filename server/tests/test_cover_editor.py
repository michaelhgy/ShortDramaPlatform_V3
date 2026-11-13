import base64
import copy
import io
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from PIL import Image
from server import v2_file_service as files
from server.cover_editor import CoverStore
from server.publishing.service import PublishingService


def image(color='red'):
    stream=io.BytesIO(); Image.new('RGB',(54,72),color).save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


class CoverEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.previous=(files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH)
        files.WORKSPACE=self.root/'workspace';files.DATA_ROOT=self.root/'data';files.DATABASE_INITIALIZED_PATH=None
        theater=files.create_theater({'name':'封面测试'})
        self.drama=files.create_drama({'current_name':'封面测试剧','theater_id':theater['id']})['id']
        self.store=CoverStore(files.WORKSPACE,files.connection)
    def tearDown(self):
        files.WORKSPACE,files.DATA_ROOT,files.DATABASE_INITIALIZED_PATH=self.previous;self.temp.cleanup()
    def upload(self,kind='drama',color='red'):
        return self.store.replace_original(self.drama,{'filename':'picture.png','content_base64':image(color)},kind)
    def version(self,snapshot,kind,id='version1',color='blue'):
        snapshot['project'][kind]['versions'].append({'id':id,'image':image(color),'sourceImage':snapshot['project'][kind]['original'],'layers':[],'createdAt':'2026-10-26'})
        snapshot['project'][kind]['activeId']=id
        return self.store.save(self.drama,snapshot)
    def test_get_is_readonly_and_initial_sheep_copy_is_hidden(self):
        self.store.snapshot(self.drama);self.assertFalse(self.store._root(self.drama).exists())
        self.upload();info=self.store.cover_info(self.drama)
        self.assertFalse(info['sheep_cover_visible']);self.assertEqual(info['cover']['path'],info['sheep_cover']['path'])
        with closing(files.connection()) as conn: profile=conn.execute('SELECT root_path FROM drama_profiles WHERE drama_id=?',(self.drama,)).fetchone()
        self.assertTrue(Path(profile[0]).is_dir())
    def test_original_replace_preserves_sheep_and_old_modified_source(self):
        self.upload();initial=self.store.cover_info(self.drama);old=Path(initial['cover']['path']).read_bytes()
        snap=self.version(self.store.snapshot(self.drama),'drama')
        version_source=snap['project']['drama']['versions'][0]['sourceImage']
        self.upload(color='green');info=self.store.cover_info(self.drama)
        self.assertNotEqual(info['cover']['path'],info['sheep_cover']['path']);self.assertFalse(info['sheep_cover_visible'])
        self.assertEqual(Path(initial['cover']['path']).read_bytes(),old)
        self.assertEqual(self.store.snapshot(self.drama)['project']['drama']['versions'][0]['sourceImage'],version_source)
    def test_custom_sheep_original_is_independent_but_still_hidden(self):
        self.upload();self.upload('sheep','yellow');self.assertFalse(self.store.cover_info(self.drama)['sheep_cover_visible'])
        self.assertNotEqual(self.store.cover_info(self.drama)['cover']['path'],self.store.cover_info(self.drama)['sheep_cover']['path'])
    def test_explicit_same_image_sheep_upload_is_still_independent(self):
        self.upload();self.upload('sheep');self.assertFalse(self.store.cover_info(self.drama)['sheep_cover_visible']);self.assertTrue(self.store.snapshot(self.drama)['project']['sheepCustomOriginal'])
    def test_sheep_visibility_follows_selection_instead_of_saved_version_count(self):
        self.upload();saved=self.version(self.store.snapshot(self.drama),'sheep')
        self.assertTrue(saved['sheep_visible']);self.assertTrue(self.store.cover_info(self.drama)['sheep_cover_visible'])
        saved['project']['sheep']['activeId']='original';hidden=self.store.save(self.drama,saved)
        self.assertFalse(hidden['sheep_visible']);self.assertFalse(self.store.cover_info(self.drama)['sheep_cover_visible']);self.assertEqual(1,len(hidden['project']['sheep']['versions']))
        hidden['project']['sheep']['activeId']='version1';self.assertTrue(self.store.save(self.drama,hidden)['sheep_visible'])
    def test_sheep_version_delete_falls_back_and_hides_default_copy(self):
        self.upload();self.version(self.store.snapshot(self.drama),'sheep');self.assertTrue(self.store.cover_info(self.drama)['sheep_cover_visible'])
        snap=self.store.snapshot(self.drama);snap['project']['sheep']['versions']=[];snap['project']['sheep']['activeId']='original';self.store.save(self.drama,snap)
        self.assertFalse(self.store.cover_info(self.drama)['sheep_cover_visible'])
    def test_each_three_versions_limit_restart_and_concurrent_conflict(self):
        self.upload();stale=self.store.snapshot(self.drama)
        for kind in ('drama','sheep'):
            for i in range(3):self.version(self.store.snapshot(self.drama),kind,f'{kind}{i}')
        before=self.store.snapshot(self.drama)
        with self.assertRaisesRegex(ValueError,'3张'):self.version(copy.deepcopy(before),'sheep','four')
        with self.assertRaisesRegex(ValueError,'其他窗口'):self.store.save(self.drama,stale)
        self.assertEqual(before,CoverStore(files.WORKSPACE,files.connection).snapshot(self.drama))
        self.assertTrue(list((self.store._root(self.drama)/'history').glob('*.json')))
    def test_assets_reject_unknown_reference_and_bad_image_preserves_state(self):
        self.upload();before=self.store.snapshot(self.drama)
        with self.assertRaises(FileNotFoundError):self.store.asset(self.drama,'0'*32)
        bad=copy.deepcopy(before);bad['project']['drama']['original']='file:///C:/Windows/win.ini'
        with self.assertRaises(ValueError):self.store.save(self.drama,bad)
        with self.assertRaises(ValueError):self.store.replace_original(self.drama,{'filename':'a.png','content_base64':base64.b64encode(b'not-an-image').decode()})
        bad=copy.deepcopy(before);bad['project']['drama']['original']=''
        with self.assertRaisesRegex(ValueError,'不能删除'):self.store.save(self.drama,bad)
        self.assertEqual(before,self.store.snapshot(self.drama))
    def test_templates_global_five_limit_conflicts_and_no_image_fields(self):
        values=[{'id':str(i),'name':f'模板{i}','width':540,'height':720,'layers':[],'image':'never-save-this'} for i in range(5)]
        saved=self.store.save_templates({'templates':values,'revision':0})
        self.assertEqual(5,len(saved['templates']));self.assertNotIn('image',saved['templates'][0])
        with self.assertRaisesRegex(ValueError,'5个'):self.store.save_templates({'templates':values+[dict(values[0],id='six')],'revision':1})
        with self.assertRaisesRegex(ValueError,'其他窗口'):self.store.save_templates({'templates':values,'revision':0})
    def test_legacy_profile_is_seeded_without_overwriting_legacy_file(self):
        legacy=self.root/'original.png';legacy.write_bytes(base64.b64decode(image().split(',')[1]))
        with closing(files.connection()) as conn:
            conn.execute('INSERT INTO drama_profiles(id,drama_id,root_path,master_path,cover_path,updated_at) VALUES(?,?,?,?,?,?)',('profile',self.drama,str(self.root),str(self.root/'master'),str(legacy),'old'));conn.commit()
        old=legacy.read_bytes();self.upload(color='blue')
        self.assertEqual(str(legacy),self.store.cover_info(self.drama)['sheep_cover']['path']);self.assertEqual(old,legacy.read_bytes())
    def test_publish_payload_routes_by_video_kind_even_in_mixed_group(self):
        self.upload();self.upload('sheep','yellow');info=self.store.cover_info(self.drama)
        publisher=PublishingService(files.connection,lambda t:{})
        group={'schedule_type':'now','copies':1,'interval':3,'order':'round','cover_mode':'drama','mount_required':False}
        ctx={**info,'binding':None,'account':{'uid':'fixture'},'settings':{}}
        for sheep in (False,True):
            item={'group':group,'video':{'exists':True,'name':'fixture','path':'fixture.mp4','sheep':sheep},'time':''}
            payload=publisher.payload(ctx,item)
            self.assertEqual(info['sheep_cover' if sheep else 'cover']['path'],payload['cover'])
        group['cover_mode']='none';self.assertNotIn('cover',publisher.payload(ctx,item))

if __name__=='__main__':unittest.main()
