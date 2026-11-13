"""Read release identity without opening any business database."""
import json
import sys
from pathlib import Path

def get_product_version():
    if getattr(sys,'frozen',False):
        metadata=json.loads((Path(sys.executable).parent/'build-metadata.json').read_text(encoding='utf8'))
        return {'product':'短剧推广运营系统','line':'V3','product_version':metadata.get('product_version',''),
                'release_id':metadata.get('release_id',metadata['version']),'channel':metadata.get('channel','stable')}
    return json.loads((Path(__file__).resolve().parents[1]/'packaging/version.json').read_text(encoding='utf8'))
