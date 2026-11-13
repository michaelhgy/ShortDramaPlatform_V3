"""Isolated account-import acceptance server. Xiao V boundary only is a fixture."""
import io
import json
import sys
import time
from pathlib import Path
from contextlib import closing
from http.server import ThreadingHTTPServer
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server import v2_file_service as files
from server import account_import as module

out=ROOT/'local-test-output/account-import-20261026';out.mkdir(parents=True,exist_ok=True)
run=out/('isolated-'+time.strftime('%H%M%S'));run.mkdir()
files.WORKSPACE=run/'workspace';files.DATA_ROOT=run/'system';files.DATABASE_INITIALIZED_PATH=None
theater=files.create_theater({'name':'已有剧场','default_commission_rate':40,'default_tax_rate':6})
old=files.create_account({'nickname':'旧账号保持不变','channel_id':'old-uid','theater_id':theater['id'],'status':'观察','notes':'导入不应修改'})
files.create_account({'nickname':'同名账号','channel_id':'local-only','theater_id':theater['id']})
stream=io.BytesIO();Image.new('RGB',(80,80),'#7796ae').save(stream,format='PNG');image=stream.getvalue()

class Cat:
    def __init__(self,writable=False):assert writable is False
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def accounts(self, *, resolve_groups=False):
        assert resolve_groups is True
        names=[('old-uid','平台改过的名字'),('new-a','待添加甲'),('new-b','待添加乙'),('same-name','同名账号')]
        names += [('extra-'+str(i),'分页账号'+str(i)) for i in range(19)]
        return [dict(uid=uid,nickname=name,avatar='',platform='Channels',platformName='视频号',loginStatus='登录失效' if uid=='new-b' else '登录有效',groupName='分组甲',tags=[],fansTotal=None) for uid,name in names]

module.CLIENT_FACTORY=Cat
original=module.AccountImport
class Import(original):
    def __init__(self,workspace,connection):
        super().__init__(workspace,connection)
        self.avatars.downloader=lambda url:image
        sync=self.avatars.sync_avatar
        self.avatars.sync_avatar=lambda account,entry:sync(account,{**entry,'avatar':'https://fixture.test/avatar'})
module.AccountImport=Import
server=ThreadingHTTPServer(('127.0.0.1',0),files.Handler)
info={'url':f'http://127.0.0.1:{server.server_port}','root':str(run),'theater_id':theater['id'],'existing_id':old['id']}
(out/'current.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(info),flush=True)
try:server.serve_forever()
finally:server.server_close()
