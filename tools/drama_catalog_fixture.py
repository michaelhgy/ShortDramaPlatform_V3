"""Built V3 UI + isolated DB; only the Xiao V boundary is a deterministic fixture."""
import io
import json
import sys
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import v2_file_service as files
from server import drama_catalog as module

out = ROOT/'local-test-output/vcat-catalog-integration-20261026'
run = out/('isolated-'+time.strftime('%H%M%S')); run.mkdir(parents=True)
files.WORKSPACE=run/'workspace'; files.DATA_ROOT=run/'system'; files.DATABASE_INITIALIZED_PATH=None
theater=files.create_theater({'name':'联动验收剧场'})
other=files.create_theater({'name':'不同剧场'})
account=files.create_account({'nickname':'同步验收账号','channel_id':'fixture-uid','theater_id':theater['id']})
account2=files.create_account({'nickname':'同剧场账号','channel_id':'fixture-uid-b','theater_id':theater['id']})
account3=files.create_account({'nickname':'其他剧场账号','channel_id':'fixture-uid-c','theater_id':other['id']})
existing=files.create_drama({'current_name':'手工名称保留','history_names':['生恩如纸，养恩如山'],'theater_id':theater['id']})
stream=io.BytesIO(); Image.new('RGB',(120,160),'#697da3').save(stream,format='PNG'); picture=stream.getvalue()

class Cat:
    def __init__(self, writable=False): assert not writable
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def accounts(self):return [{'uid':uid,'platform':'Channels','loginStatus':'登录有效','avatar':'https://fixture.test/avatar'} for uid in ('fixture-uid','fixture-uid-b')]
    def worker(self,uid,method,params):
        assert method=='getDramaComponent'
        source='video' if params.get('sceneType')==3 else 'mini'
        rows=[]
        for n in range(33):
            row={'id':f'{source}-{n}','name':'生恩如纸 养恩如山' if n==0 else f'同步测试剧{n:02d}','mediaCount':104 if n==0 else 80+n,'usable':n!=32,'unusableReason':'未版权保护' if n==32 else '', 'coverUrl':f'{info["url"]}/fixture-cover.png'}
            if source=='mini':row.update(miniAppName='绿泡泡短剧',miniAppIconUrl=f'{info["url"]}/fixture-cover.png',questFlag=1)
            rows.append(row)
        page=params['page'];time.sleep(.04)
        return {'list':rows[(page-1)*20:page*20],'totalCount':len(rows),'baseResp':{'errcode':0}}

original=module.Catalogue
module.Catalogue=lambda workspace,connection:original(workspace,connection,Cat,lambda url:picture)

class Handler(files.Handler):
    def do_GET(self):
        if urlparse(self.path).path=='/fixture-cover.png':
            self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(picture)));self.end_headers();self.wfile.write(picture)
        else: super().do_GET()

server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
info={'url':f'http://127.0.0.1:{server.server_port}','account_id':account['id'],'second_account_id':account2['id'],'other_account_id':account3['id'],'drama_id':existing['id'],'root':str(run)}
(out/'current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info),flush=True)
try:server.serve_forever()
finally:server.server_close()
