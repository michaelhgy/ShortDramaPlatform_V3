"""Read-only samples of both Xiao V Cat drama component entry points."""
import json
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server.publishing.vcat import VcatClient

out=ROOT/'local-test-output/vcat-drama-discovery-20261026';out.mkdir(parents=True,exist_ok=True)
rows=[]
with VcatClient(writable=False) as client:
    accounts=[a for a in client.accounts() if a.get('platform')=='Channels' and a.get('loginStatus')=='登录有效']
    for account in accounts:
        for kind in ('mini_drama','channels_drama'):
            params={'page':1,'queryString':''}
            if kind=='channels_drama':params['sceneType']=3
            args=json.dumps([account['uid'],params],ensure_ascii=True);start=time.monotonic()
            expression="""(async()=>{const [uid,params]=ARGS;const accounts=await window.CatBridge.getCall('AccountManager.getAllAccounts');const account=accounts.find(a=>a.uid===uid&&a.platform==='Channels');if(!account)return {probeError:'Account not found'};try{return await window.CatBridge.getCall('AccountManager.getWorkerCall',account,'getDramaComponent',params);}catch(error){return {probeError:String(error?.message||error).slice(0,400)};}})()""".replace('ARGS',args)
            try:result=client.evaluate(expression)
            except Exception as exc:result={'probeError':str(exc)}
            record={'uid':account['uid'],'nickname':account.get('nickname'),'source':kind,'params':params,'seconds':round(time.monotonic()-start,3),'result':result};rows.append(record)
            (out/'component-samples.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
            result=result if isinstance(result,dict) else {};items=result.get('list')or[]
            print(json.dumps({'nickname':record['nickname'],'source':kind,'seconds':record['seconds'],'count':len(items),'totalCount':result.get('totalCount'),'baseResp':result.get('baseResp'),'probeError':result.get('probeError'),'topFields':list(result),'sampleFields':list(items[0])if items else [],'examples':[{k:item.get(k)for k in ('id','name','miniAppName','mediaCount','usable','unusableReason')}for item in items[:2]]},ensure_ascii=True),flush=True)
