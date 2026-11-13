"""Copy a read-only live flower response into an explicitly isolated UI fixture."""
import json
import sqlite3
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
info=json.loads((ROOT/'local-test-output/cover-integration-20261026/current.json').read_text(encoding='utf-8'))
target=(Path(info['root'])/'system/database/v2_system.db').resolve()
if not target.is_relative_to((ROOT/'local-test-output/cover-integration-20261026').resolve()):raise RuntimeError('Fixture outside test directory')
with urllib.request.urlopen('http://127.0.0.1:8782/api/v2/cover-editor/flowers',timeout=20) as response:body=response.read()
source=json.loads(body)
with sqlite3.connect(target) as conn:
    for style in source['styles']:
        definition={key:style[key] for key in ('id','name','tags','icon','style') if key in style}
        conn.execute('INSERT OR REPLACE INTO v3_flower_assets VALUES(?,?)',(style['id'],json.dumps(definition,ensure_ascii=False)))
        conn.execute('INSERT OR REPLACE INTO v3_flower_preferences VALUES(?,?,?,?,?)',(style['id'],int(style.get('favorite',False)),int(style.get('enabled',True)),style.get('usageCount',0),style.get('lastUsed','')))
    conn.commit()
result={'source':'read-only live flowers API','styles':len(source['styles']),'full_response_bytes':len(body),'target':str(target),'real_business_writes':0}
out=ROOT/'local-test-output/cover-opening-20261026';out.mkdir(exist_ok=True)
(out/'seed.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=True))
