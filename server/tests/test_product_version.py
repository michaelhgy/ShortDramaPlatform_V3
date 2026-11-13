import json
import sys
from pathlib import Path
from unittest.mock import patch
from server.product_version import get_product_version


def test_development_version_uses_single_configuration():
    value=get_product_version()
    root=Path(__file__).resolve().parents[2]
    assert value==json.loads((root/'packaging/version.json').read_text(encoding='utf8'))
    assert json.loads((root/'package.json').read_text())['version']==value['product_version']


def test_frozen_identity_uses_external_release_metadata(tmp_path):
    (tmp_path/'build-metadata.json').write_text(json.dumps({'version':'2026.11.03.1','product_version':'3.0.0','release_id':'2026.11.03.1','channel':'stable'}),encoding='utf8')
    with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(tmp_path/'ShortDramaPlatformV3.exe')):
        assert get_product_version()['product_version']=='3.0.0'
        assert get_product_version()['release_id']=='2026.11.03.1'


def test_product_version_is_carried_by_update_manifest():
    from server.tests.test_v3_updates import builder
    import tempfile
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name,release in [('base','2026.10.30.1'),('target','2026.11.03.1')]:
            path=root/name;path.mkdir();(path/'ShortDramaPlatformV3.exe').write_bytes(name.encode())
            (path/'build-metadata.json').write_text(json.dumps({'product':'ShortDramaPlatform V3','version':release,'product_version':'3.0.0'}))
        assert builder.make_manifest(root/'base',root/'target')['target_product_version']=='3.0.0'
