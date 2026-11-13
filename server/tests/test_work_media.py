import io
import tempfile
from PIL import Image
import unittest
from pathlib import Path
from unittest.mock import Mock
from server.work_media import WorkMediaCache, local_cover_url, playback_url, cover_identity, legacy_cover_identity


class WorkMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        image=io.BytesIO()
        Image.new('RGB',(12,8),'blue').save(image,format='PNG')
        self.png=image.getvalue()
        self.download = Mock(return_value=self.png)
        self.cache = WorkMediaCache(Path(self.tmp.name), self.download)

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, key='image-a', token='one', video='https://finder.video.qq.com/video?sign=one'):
        return {'postId': 'p', 'coverUrl': 'https://finder.video.qq.com/image?encfilekey=' + key + '&token=' + token,
                'videoUrl': video}

    def test_signature_change_reuses_cover_but_updates_video_address(self):
        first, errors = self.cache.prepare('u', [self.post()])
        second, later = self.cache.prepare('u', [self.post(token='two', video='https://finder.video.qq.com/video?sign=two')], first)
        self.assertEqual([], errors + later)
        self.assertEqual(first[0]['coverLocalId'], second[0]['coverLocalId'])
        self.assertEqual(1, self.download.call_count)
        self.assertTrue(second[0]['videoUrl'].endswith('sign=two'))
        self.assertTrue(self.cache.path(second[0]['coverLocalId']).is_file())

    def test_changed_remote_address_or_key_never_replaces_healthy_local_cover(self):
        first, _ = self.cache.prepare('u', [self.post()])
        self.download.side_effect = AssertionError('Existing cover must not download')
        changed=self.post(key='other-key',video='https://example.test/current-video')
        changed.update(coverUrl='https://other-cdn.test/completely/new?anything=changed',coverKey='new-key')
        rows,errors=self.cache.prepare('u',[changed],first)
        self.assertEqual(errors,[])
        self.assertEqual(rows[0]['coverLocalId'],first[0]['coverLocalId'])
        self.assertEqual(rows[0]['videoUrl'],changed['videoUrl'])
        self.assertEqual(self.download.call_count,1)

    def test_missing_empty_or_corrupt_local_cover_is_repaired(self):
        first,_=self.cache.prepare('u',[self.post()])
        path=self.cache.path(first[0]['coverLocalId'])
        for damage in (None,b'',b'not an image',self.png[:45]):
            if damage is None:path.unlink()
            else:path.write_bytes(damage)
            rows,errors=self.cache.prepare('u',[self.post(key='new-url')],first)
            self.assertEqual(errors,[])
            self.assertTrue(self.cache.valid(rows[0]['coverLocalId']))
        self.assertEqual(self.download.call_count,5)

    def test_bad_download_does_not_publish_a_broken_cover_link_and_can_retry(self):
        self.download.return_value=b'broken-image'
        rows,errors=self.cache.prepare('u',[self.post()])
        self.assertNotIn('coverLocalId',rows[0])
        self.assertEqual(errors[0]['stage'],'cover')
        self.assertEqual(list(Path(self.tmp.name).glob('*')),[])
        self.download.return_value=self.png
        rows,errors=self.cache.prepare('u',[self.post()],rows)
        self.assertEqual(errors,[])
        self.assertTrue(self.cache.valid(rows[0]['coverLocalId']))

    def test_legacy_cover_is_reused_without_redownload_or_migration(self):
        old_id=legacy_cover_identity('u',self.post())
        self.cache.path(old_id).write_bytes(self.png)
        prior=[{'postId':'p','coverLocalId':old_id}]
        rows,errors=self.cache.prepare('u',[self.post(key='changed')],prior)
        self.assertEqual(errors,[])
        self.assertEqual(rows[0]['coverLocalId'],old_id)
        self.download.assert_not_called()
        # Old URL cache can also be found when the previous list has no local link.
        rows,_=self.cache.prepare('u',[self.post()])
        self.assertEqual(rows[0]['coverLocalId'],old_id)
        self.download.assert_not_called()

    def test_stable_work_cache_survives_missing_previous_list_or_remote_address(self):
        first,_=self.cache.prepare('u',[self.post()])
        rows,errors=WorkMediaCache(self.tmp.name,self.download).prepare('u',[{'postId':'p'}])
        self.assertEqual(errors,[])
        self.assertEqual(rows[0]['coverLocalId'],first[0]['coverLocalId'])
        self.assertEqual(self.download.call_count,1)

    def test_invalid_local_cover_is_not_exposed_during_local_only_or_stopped_collection(self):
        asset=cover_identity('u',self.post());self.cache.path(asset).write_bytes(b'broken')
        previous=[{'postId':'p','coverLocalId':asset}]
        for options in ({'download':False},{'should_stop':lambda:True}):
            rows,errors=self.cache.prepare('u',[self.post()],previous,**options)
            self.assertEqual(errors,[])
            self.assertNotIn('coverLocalId',rows[0])
        self.download.assert_not_called()

    def test_same_post_id_on_two_accounts_has_separate_cover_identity(self):
        a, _ = self.cache.prepare('u', [self.post()])
        b, _ = self.cache.prepare('v', [self.post()])
        self.assertNotEqual(a[0]['coverLocalId'], b[0]['coverLocalId'])

    def test_local_only_collection_does_not_download_and_missing_remote_cover_keeps_old(self):
        empty, errors = self.cache.prepare('u', [self.post()], download=False)
        self.download.assert_not_called()
        self.assertNotIn('coverLocalId', empty[0])
        first, _ = self.cache.prepare('u', [self.post()])
        preserved, _ = self.cache.prepare('u', [{'postId': 'p'}], first, download=False)
        self.assertEqual(first[0]['coverLocalId'], preserved[0]['coverLocalId'])

    def test_local_cover_http_route_serves_cached_image_without_touching_database(self):
        import io
        from unittest.mock import patch
        from server import v2_file_service as service
        root=Path(self.tmp.name)/'data'
        cache=WorkMediaCache(root/'cache'/'work-covers',self.download)
        rows,_=cache.prepare('u',[self.post()])
        handler=service.Handler.__new__(service.Handler)
        handler.path=local_cover_url(rows[0]['coverLocalId'])
        handler.headers={}
        handler.wfile=io.BytesIO()
        handler.send_response=Mock();handler.send_header=Mock();handler.end_headers=Mock()
        with patch.object(service,'DATA_ROOT',root),patch.object(service,'connection',side_effect=AssertionError('Image route must not open database')):
            handler.do_GET()
        self.assertEqual(self.png,handler.wfile.getvalue())
        handler.send_response.assert_called_with(200)
        handler.send_header.assert_any_call('Content-Type','image/png')

    def test_local_route_cannot_escape_cache_and_playback_rejects_non_http_schemes(self):
        self.assertEqual('', local_cover_url('../outside'))
        with self.assertRaises(ValueError): self.cache.path('../outside')
        for value in ('javascript:alert(1)', 'file:///D:/private.mp4', None):
            self.assertEqual('', playback_url(value))
        self.assertEqual('https://finder.video.qq.com/v', playback_url('https://finder.video.qq.com/v'))


if __name__ == '__main__':
    unittest.main()
