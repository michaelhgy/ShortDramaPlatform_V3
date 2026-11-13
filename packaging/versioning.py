"""Release identity shared by the V3 program, installer and updater builders."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def release_identity():
    value=json.loads((ROOT/'packaging/version.json').read_text(encoding='utf8'))
    for key,count in (('product_version',3),('release_id',4)):
        parts=value[key].split('.')
        if len(parts)!=count or any(not p.isascii() or not p.isdecimal() or not 0<=int(p)<=65535 for p in parts):
            raise ValueError('Invalid release identity: '+key)
    return value

def write_installer_identity(value):
    (ROOT/'packaging/version.iss').write_text(
        '// Generated from packaging/version.json; run the V3 builder to refresh.\n'
        + '#define DefaultProductVersion "'+value['product_version']+'"\n'
        + '#define DefaultReleaseVersion "'+value['release_id']+'"\n',encoding='utf-8-sig')
