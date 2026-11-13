"""Local Xiao V Cat adapter with explicit draft and real-publication write gates."""
from __future__ import annotations

import json
import threading
import urllib.request
from .cdp import CDPConnection, CDPError, Target

WRITE_LOCK = threading.Lock()
READ_TOOLS = {
    'vcat_list_accounts', 'vcat_list_groups', 'vcat_list_drafts', 'vcat_list_publish_tasks', 'vcat_get_publish_options',
    'vcat_get_account_stats',
    'vcat_list_posts', 'vcat_get_post', 'vcat_get_post_daily', 'vcat_get_post_stat', 'vcat_get_post_trend', 'vcat_get_post_sync',
    'vcat_list_post_sync_records', 'vcat_list_punish_feeds', 'vcat_get_verify_result',
}
EXTERNAL_REFRESH_TOOLS = {'vcat_refresh_account_stats', 'vcat_start_post_sync', 'vcat_refresh_account_feeds'}

ALLOWED_BRIDGE = {'McpServer.getSetting', 'McpServer.getStatus', 'McpServer.getConnectInfo', 'AccountManager.getAllAccounts'}


def discard_home_visits(value):
    """Discard the unwanted metric even when the upstream sends a full payload."""
    if isinstance(value, dict):
        return {key: discard_home_visits(item) for key, item in value.items()
                if key not in {'homeView', 'home_view', 'homeViews', 'homeVisit', '主页访问'}}
    if isinstance(value, list):
        return [discard_home_visits(item) for item in value]
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DraftRejected(RuntimeError):
    """The server explicitly rejected a creation request."""


class DraftOutcomeUnknown(RuntimeError):
    """Creation may have succeeded; never retry without reconciliation."""


class PublishOutcomeUnknown(RuntimeError):
    """A real queue submission might have succeeded; reconcile before any retry."""


class PublishRejected(RuntimeError):
    """The platform explicitly rejected the publication request; no task was created."""


class VcatClient:
    def __init__(self, port=9222, *, writable=False, publishing=False, account_data=False, optimization_actions=False):
        self.cdp = None
        self.writable = writable
        self.publishing = publishing
        self.account_data = account_data
        self.optimization_actions = optimization_actions
        self.changed = False
        self.locked = False
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.headers = {'Content-Type':'application/json', 'Accept':'application/json, text/event-stream'}
        self.counter = 0
        try:
            if writable:
                if not WRITE_LOCK.acquire(timeout=5):
                    raise RuntimeError('另一批发布或草稿正在处理，请稍后继续')
                self.locked = True
            port = int(port)
            if not 1 <= port <= 65535: raise ValueError('小V猫连接端口无效')
            with self.opener.open(f'http://127.0.0.1:{port}/json/list',timeout=3) as response:
                targets = json.load(response)
            for target in targets:
                if target.get('type') != 'page' or 'index.html' not in target.get('url',''): continue
                try:
                    self.cdp=CDPConnection(target['webSocketDebuggerUrl'],timeout=4)
                    if self.evaluate("typeof window.CatBridge?.getCall==='function'"): break
                except Exception:
                    pass
                if self.cdp: self.cdp.close(); self.cdp=None
            if self.cdp is None: raise RuntimeError('未找到小V猫主窗口，请先启动小V猫并开启远程调试')
            self.setting=self.bridge('McpServer.getSetting')
            if not self.setting.get('enabled'): raise RuntimeError('请先在小V猫设置中开启 MCP')
            info=self.bridge('McpServer.getConnectInfo')
            from urllib.parse import urlparse
            url=urlparse(info['url'])
            if url.hostname not in ('127.0.0.1','localhost') or url.scheme!='http':
                raise RuntimeError('当前仅连接本机小V猫 MCP')
            self.url=info['url']
            self.headers['Authorization']='Bearer '+info['token']
            init=self.request('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'V3-local-draft-workbench','version':'1.0'}})
            self.headers['MCP-Protocol-Version']=init['result']['protocolVersion']
            self.request('notifications/initialized',{},notification=True)
        except Exception as exc:
            self.close()
            if isinstance(exc,(RuntimeError,ValueError)): raise
            raise RuntimeError('无法连接小V猫，请检查程序、MCP 与远程调试端口') from None

    def __enter__(self): return self
    def __exit__(self,*args): self.close()

    def evaluate(self, expression):
        response=self.cdp.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True},timeout=70)
        result=response.get('result',{})
        if result.get('exceptionDetails'): raise RuntimeError('小V猫查询失败，请检查账号登录状态后重试')
        return result.get('result',{}).get('value')

    def bridge(self, name):
        if name not in ALLOWED_BRIDGE: raise ValueError('不允许调用该小V猫操作')
        return self.evaluate('window.CatBridge.getCall('+json.dumps(name)+')')

    def task_action(self, name, *arguments):
        allowed={'Models.PublishLog.updateRecordsByIds','PublishController.startPublishTask'}
        if name not in allowed or not (self.writable and self.publishing):
            raise ValueError('此连接未授权该发布任务操作')
        modules=dict(self.setting.get('writeModules') or {})
        if not modules.get('publish') and not self.changed:
            modules['publish']=True;self.changed=True
            self.evaluate("window.CatBridge.getCall('McpServer.saveSetting',"+json.dumps({'writeModules':modules})+")")
        return self.evaluate('window.CatBridge.getCall('+json.dumps(name)+','+','.join(json.dumps(v,ensure_ascii=False) for v in arguments)+')')

    def worker(self, uid, method, params):
        if method not in {'getDramaComponent','getPositionsWithLocation'}: raise ValueError('仅允许查询地址和剧集')
        args=json.dumps([uid,method,params],ensure_ascii=True)
        # The account object stays in Xiao V Cat. Never persist cookies or login data.
        return self.evaluate("(async()=>{const [uid,method,params]="+args+";const accounts=await window.CatBridge.getCall('AccountManager.getAllAccounts');const matches=accounts.filter(a=>a.uid===uid&&a.platform==='Channels');if(matches.length!==1)throw Error('Account unavailable');const r=await window.CatBridge.getCall('AccountManager.getWorkerCall',matches[0],method,params);if(method==='getDramaComponent')return {list:r.list||[],totalCount:r.totalCount||0,baseResp:r.baseResp};return {list:r.list||[],address:r.address,_searchQuery:r._searchQuery};})()")

    def request(self, method, params, notification=False):
        self.counter+=1
        request_id=self.counter
        body={'jsonrpc':'2.0','method':method,'params':params}
        if not notification: body['id']=request_id
        req=urllib.request.Request(self.url,json.dumps(body,ensure_ascii=False).encode('utf-8'),headers=self.headers)
        with self.opener.open(req,timeout=70) as response:
            session=response.headers.get('Mcp-Session-Id')
            if session:self.headers['Mcp-Session-Id']=session
            raw=response.read().decode('utf-8')
        if not raw:return {}
        if raw.lstrip().startswith('{'):return json.loads(raw)
        for line in raw.splitlines():
            if line.startswith('data:'):
                result=json.loads(line[5:].strip())
                if result.get('id')==request_id:return result
        raise RuntimeError('小V猫响应不完整，请重新读取结果')

    def call(self,name,arguments):
        if name in EXTERNAL_REFRESH_TOOLS and not self.account_data:
            raise ValueError('统计刷新与作品同步仅允许由账号数据采集任务触发')
        action_allowed = name in ('vcat_delete_punish_post','vcat_hide_punish_post') and self.account_data and getattr(self,'optimization_actions',False)
        if not action_allowed and name not in READ_TOOLS and not (name in EXTERNAL_REFRESH_TOOLS and self.account_data) and not (name=='vcat_create_draft' and self.writable) and not (name in ('vcat_create_publish_task','vcat_cancel_publish_task','vcat_set_publish_priority') and self.writable and getattr(self,'publishing',False)):
            raise ValueError('此连接未授权该操作，禁止发布或写入')
        if name in ('vcat_create_draft','vcat_create_publish_task','vcat_cancel_publish_task','vcat_set_publish_priority'):
            modules=dict(self.setting.get('writeModules') or {})
            if not modules.get('publish') and not self.changed:
                modules['publish']=True
                self.changed=True
                self.evaluate("window.CatBridge.getCall('McpServer.saveSetting',"+json.dumps({'writeModules':modules})+")")
        try:
            response=self.request('tools/call',{'name':name,'arguments':arguments})
        except Exception:
            if name=='vcat_create_draft':raise DraftOutcomeUnknown('草稿创建响应中断，先检查是否已生成，不能直接重复创建') from None
            if name=='vcat_create_publish_task':raise PublishOutcomeUnknown('发布提交响应中断，先查询小V猫任务，禁止直接重复发布') from None
            raise RuntimeError('小V猫读取失败，请检查连接后重试') from None
        if 'error' in response or response.get('result',{}).get('isError'):
            messages=[c.get('text','') for c in response.get('result',{}).get('content',[]) if c.get('type')=='text']
            message='；'.join(messages) or '小V猫拒绝本次参数，请核对后重试'
            if name=='vcat_create_draft':raise DraftRejected(message[:800])
            if name=='vcat_create_publish_task':raise PublishRejected(message[:800])
            raise RuntimeError(message[:800])
        values=[]
        for content in response.get('result',{}).get('content',[]):
            if content.get('type')=='text':values.append(json.loads(content['text']))
        if not values:raise RuntimeError('小V猫没有返回有效结果')
        result = values[0] if len(values)==1 else values
        return discard_home_visits(result) if name == 'vcat_get_account_stats' else result

    def online_account_posts(self, uid, *, page_interval_seconds=2.0, pacer=None, progress=None, should_stop=None, published_start=None, published_end=None):
        from .online_posts import read_online_posts
        return read_online_posts(self, uid, page_interval_seconds=page_interval_seconds, pacer=pacer, progress=progress, should_stop=should_stop, published_start=published_start, published_end=published_end)

    def _online_posts_page(self, uid, params):
        if not self.account_data:
            raise ValueError('在线作品读取仅允许由数据采集任务触发')
        return self.evaluate("""(async()=>{
          const uid=UID, params=PARAMS;
          const accounts=await window.CatBridge.getCall('AccountManager.getAllAccounts');
          const matches=accounts.filter(a=>a.uid===uid&&a.platform==='Channels');
          if(matches.length!==1)throw Error('账号没有唯一匹配');
          const result=await window.CatBridge.getCall('PostManager.getPostList',matches[0],params);
          if(!result||!Array.isArray(result.list))throw Error('在线作品响应无效');
          const epoch=value=>{
            if(value==null||value==='')return null;
            if(value instanceof Date)return Number.isFinite(value.getTime())?Math.floor(value.getTime()/1000):null;
            const numeric=Number(value);
            if(Number.isFinite(numeric)&&numeric>0)return Math.floor(numeric>1e12?numeric/1000:numeric);
            const ms=new Date(value).getTime();return Number.isFinite(ms)?Math.floor(ms/1000):null;
          };
          const observedAt=new Date().toISOString();
          return {total:result.total,hasMore:result.hasMore,nextState:result.nextState,
            list:result.list.map(p=>{
              if(!p||(p.uid!=null&&p.uid!==uid)||(p.platform!=null&&p.platform!=='Channels'))
                throw Error('在线作品账号或平台不匹配');
              const o=p.originData||{}, media=o.desc?.media?.[0]||{};
              const metric=(key,scale=1)=>{
                const v=o[key];
                return v==null||v===''||typeof v==='boolean'||!Number.isFinite(Number(v))?null:Number(v)*scale;
              };
              return {uid,postId:p.postId==null?null:String(p.postId),platform:p.platform,
                postUnix:epoch(p.postTime),isSticky:p.isSticky==null?null:p.isSticky===true||p.isSticky===1,observedAt,metricSource:'online_list',
                scheduleUnix:epoch(p.timing)||epoch(o.effectiveTime),publishStatus:p.publishStatus,
                sourceStatus:o.status,sourceCreateTime:o.createTime,sourceEffectiveTime:o.effectiveTime,
                exportId:p.exportId||o.exportId||'',title:p.title||'',desc:typeof p.desc==='string'?p.desc:'',
                postType:p.postType,coverPresent:!!p.cover,urlPresent:!!media.url,
                coverUrl:p.cover||media.coverUrl||media.thumbUrl||'',coverKey:p.coverKey||'',
                videoUrl:media.url||'',videoDuration:media.videoPlayLen??p.videoTime??null,
                view:metric('readCount'),like:metric('favCount'),love:metric('likeCount'),
                comment:metric('commentCount'),forward:metric('forwardCount'),
                fansAdd:metric('followCount'),fullView:metric('fullPlayRate',100),viewTime:metric('avgPlayTimeSec')};
            })};
        })()""".replace('UID', json.dumps(uid)).replace('PARAMS', json.dumps(params)))

    def account_posts(self, uid):
        """Read the same local model as the works UI, preserving absolute times.

        MCP formatted date strings can reflect an earlier timezone. Never repair
        them by adding hours. Dates are converted inside Xiao V Cat before CDP
        serialization (Date objects otherwise arrive as empty dictionaries).
        """
        if not uid or not isinstance(uid, str):
            raise ValueError('需要账号 UID')
        return self.evaluate("""(async()=>{const uid="""+json.dumps(uid)+""";
          const rows=[],seen=new Set();let total=null;
          const epoch=x=>x==null?null:Math.floor(new Date(x).getTime()/1000);
          for(let current=1;current<=200;current++){
            const r=await window.CatBridge.getCall('Models.Post.queryAll',{current,pageSize:100},{uid});
            if(!Array.isArray(r.list)||!r.pager)throw Error('作品分页无效');
            if(total!==null&&total!==r.pager.total)throw Error('作品数量在读取期间变化');
            total=r.pager.total;
            for(const p of r.list){
              if(p.uid!==uid||!p.postId||seen.has(String(p.postId)))throw Error('作品身份或分页重复');
              seen.add(String(p.postId));const o=p.originData||{};
              rows.push({uid,postId:String(p.postId),platform:p.platform,account:p.account,
                postUnix:epoch(p.postTime),observedAt:p.updatedAt?new Date(p.updatedAt).toISOString():null,scheduleUnix:Number(o.effectiveTime)>0?Number(o.effectiveTime):epoch(p.timing),publishStatus:p.publishStatus,
                sourceStatus:o.status,sourceCreateTime:o.createTime,sourceEffectiveTime:o.effectiveTime,
                exportId:o.exportId||'',title:p.title,desc:p.desc,postType:p.postType,
                coverPresent:!!p.cover,urlPresent:!!o.desc?.media?.[0]?.url,
                coverUrl:p.cover||o.desc?.media?.[0]?.coverUrl||'',coverKey:p.coverKey||'',
                videoUrl:o.desc?.media?.[0]?.url||'',videoDuration:o.desc?.media?.[0]?.videoPlayLen??p.videoTime??null,
                view:p.view,like:p.like,love:p.love,comment:p.comment,forward:p.forward,
                fansAdd:p.fansAdd,fullView:p.fullView,viewTime:p.viewTime});
            }
            if(!r.pager.hasMore){if(rows.length!==total)throw Error('作品分页不完整');return rows;}
          }throw Error('作品分页超过上限');})()""")

    def account_diagnosis(self, uid):
        """Cached diagnosis only. Never run diagnosis or automatic deletion."""
        return self.evaluate("""(async()=>{const uid="""+json.dumps(uid)+""";
          const a=(await window.CatBridge.getCall('AccountManager.getAllAccounts'))
            .find(a=>a.uid===uid&&a.platform==='Channels');
          if(!a)return null;
          const r=a.postStatusResult;
          return {uid,verified:!!r&&Number.isInteger(r.total)&&r.total===(r.feeds||[]).length,lastVerifyUnix:a.timestamp?Math.floor(new Date(a.timestamp).getTime()/1000):null,
            feeds:(r?.feeds||[]).map(f=>({uid,exportId:f.exportId,publishUnix:Number(f.publishUnixTimestamp)||null,
              publishTime:f.publishTime,punishState:f.punishState,deleted:!!f.deleteUnixTimestamp}))};})()""")

    def refresh_account_diagnosis(self, uid):
        """Refresh only abnormal feeds; never enable auto detection or delete/hide works."""
        if not self.account_data:
            raise ValueError('主动检测仅允许由账号数据采集任务触发')
        result = self.call('vcat_refresh_account_feeds', {'uid': uid})
        if not isinstance(result, dict) or result.get('success') is False or result.get('error'):
            raise RuntimeError('小V猫未完成本次异常作品检测，保留原有结果')
        diagnosis = self.account_diagnosis(uid)
        if not diagnosis or not diagnosis.get('verified'):
            raise RuntimeError('小V猫本次检测结果不完整，保留原有结果')
        return diagnosis

    def act_on_optimization(self, uid, export_id, action):
        if not self.account_data or not getattr(self,'optimization_actions',False) or action not in ('hide','delete'):
            raise ValueError('此连接未授权优化处理')
        if not uid or not export_id: raise ValueError('优化处理身份缺失')
        result = self.call('vcat_'+action+'_punish_post', {'uid':uid,'exportId':export_id})
        if isinstance(result,dict) and (result.get('success') is False or result.get('ok') is False or result.get('error')):
            raise RuntimeError('平台未确认优化处理成功')
        return result

    def optimization_detail(self, uid, export_id):
        """Read the already validated official appeal-detail GET, never submit an appeal.

        Session cookies stay in memory, are scoped to one Xiao V account, and
        never enter return values, evidence files, errors, or logs.
        """
        if not self.account_data:
            raise ValueError('优化详情读取仅允许由账号数据采集任务触发')
        uid, export_id = str(uid or '').strip(), str(export_id or '').strip()
        if not uid or not export_id:
            raise ValueError('优化详情需要账号 UID 与异常作品 exportId')
        expression = """(async()=>{
            const uid=UID;
            const accounts=await window.CatBridge.getCall('AccountManager.getAllAccounts');
            const matches=accounts.filter(a=>a.uid===uid&&a.platform==='Channels');
            if(matches.length!==1||!matches[0].partition)throw Error('Account unavailable');
            const cookies=await window.CatBridge.getCall('Platform.getPartitionCookie',matches[0].partition+'mobile');
            return (cookies||[]).filter(c=>['channels.weixin.qq.com','.channels.weixin.qq.com'].includes(c.domain)
                &&['_finder_auth','wxuin'].includes(c.name)).map(c=>({name:c.name,value:c.value}));
        })()""".replace('UID', json.dumps(uid))
        cookies = self.evaluate(expression)
        if not isinstance(cookies, list) or not any(c.get('name') == '_finder_auth' for c in cookies):
            raise RuntimeError('该账号的优化详情登录态不可用，请先在小V猫重新登录')
        from urllib.parse import urlencode
        url = 'https://channels.weixin.qq.com/pandora/api/appeal/get_finder_appeal_detail_by_export_id?'+urlencode({'export_id':export_id})
        request = urllib.request.Request(url, headers={
            'Cookie': '; '.join(c['name']+'='+c['value'] for c in cookies),
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
            'Referer': 'https://channels.weixin.qq.com/pandora/pages/appeal/index/',
            'Accept': 'application/json',
        }, method='GET')
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            with opener.open(request, timeout=30) as response:
                status = response.status
                body = json.load(response)
        except Exception:
            raise RuntimeError('官方优化详情读取失败；未保存登录凭据，也未提交申诉') from None
        finally:
            cookies = None
            request = None
        if not isinstance(body, dict) or body.get('errCode') != 0:
            raise RuntimeError('官方优化详情返回失败或登录态过期')
        data = body.get('data') or {}
        operations = data.get('operate_items') or []
        if not isinstance(operations, list) or not operations:
            raise RuntimeError('官方未返回该作品的作品分析记录')
        safe_items = [{k:op.get(k) for k in ('reason','tips','appeal_type','unique_id','feed_create_time','audit_result')} for op in operations if isinstance(op,dict)]
        first = safe_items[0] if safe_items else {}
        if not first.get('reason'):
            raise RuntimeError('官方优化详情缺少作品分析原文')
        return {'uid':uid,'exportId':export_id,'httpStatus':status,'errCode':0,
                'reason':first.get('reason'),'tips':first.get('tips'),
                'appealType':first.get('appeal_type'),'uniqueId':first.get('unique_id'),
                'feedCreateTime':first.get('feed_create_time') or data.get('feed_create_time'),
                'auditResult':data.get('punish_state') or first.get('audit_result'),
                'coverPresent':bool(data.get('feed_img') or any(op.get('cover_url') for op in operations)),
                'videoPresent':bool(data.get('video_url') or any(op.get('video_url') for op in operations)),
                'operateItems':safe_items}

    def accounts(self, *, resolve_groups=False):
        accounts=[]
        for page in range(1,101):
            result=self.call('vcat_list_accounts',{'page':page,'pageSize':100})
            accounts.extend(result['list'])
            if len(accounts)>=result['total']:break
        if resolve_groups:
            self._resolve_account_groups(accounts)
        return accounts

    def _resolve_account_groups(self, accounts):
        # MCP omits the name for group 0. Read only membership identifiers from
        # the local account manager; credentials remain inside Xiao V Cat.
        missing = [a for a in accounts if not str(a.get('groupName') or '').strip()]
        if not missing:
            return
        memberships = self.evaluate("""(async()=>{
            const accounts=await window.CatBridge.getCall('AccountManager.getAllAccounts');
            return accounts.map(a=>({uid:a.uid,platform:a.platform,groupId:a.groupId??a.group_id??null}));
        })()""")
        error = '小V猫账号分组返回不完整，请重新获取'
        if not isinstance(memberships, list):
            raise RuntimeError(error)
        by_account = {}
        for item in memberships:
            if not isinstance(item, dict):
                raise RuntimeError(error)
            key = (item.get('platform'), item.get('uid'))
            group_id = item.get('groupId')
            # Never treat an absent/unknown membership as the default group.
            group_id = str(group_id) if group_id is not None else None
            by_account.setdefault(key, set()).add(group_id)
        pending = []
        for account in missing:
            ids = by_account.get((account.get('platform'), account.get('uid')), set())
            if len(ids) != 1 or None in ids:
                raise RuntimeError(error)
            pending.append((account, next(iter(ids))))
        names = {'0': '默认分组'}
        if any(group_id != '0' for _, group_id in pending):
            groups = self.call('vcat_list_groups', {})
            if not isinstance(groups, dict) or not isinstance(groups.get('list'), list):
                raise RuntimeError(error)
            if groups.get('total') != len(groups['list']):
                raise RuntimeError(error)
            for group in groups['list']:
                if not isinstance(group, dict):
                    raise RuntimeError(error)
                group_id = str(group.get('id'))
                name = str(group.get('name') or '').strip()
                if group_id != '0' and name:
                    if group_id in names and names[group_id] != name:
                        raise RuntimeError(error)
                    names[group_id] = name
        for account, group_id in pending:
            if group_id not in names:
                raise RuntimeError(error)
            account['groupName'] = names[group_id]

    def find_draft(self,title):
        found=[]
        count=0
        for page in range(1,101):
            result=self.call('vcat_list_drafts',{'page':page,'pageSize':100})
            count+=len(result['list'])
            found.extend(d for d in result['list'] if d.get('title')==title)
            if count>=result['total']:break
        if len(found)>1:raise RuntimeError('发现多个同名测试草稿，请人工核对，暂不重复生成')
        return found[0] if found else None

    def open_draft(self,draft_id):
        draft_id=int(draft_id)
        self.call('vcat_list_drafts',{'draftId':draft_id})
        result=self.evaluate("(()=>{const e=document.querySelector('[role=tab]');let f=e?.[Object.keys(e).find(k=>k.startsWith('__reactFiber$'))];for(;f;f=f.return){const v=f.memoizedProps?.value;if(typeof v?.goTab==='function'){v.goTab({activePath:'/publish/post',params:{draftId:"+str(draft_id)+"}});return true;}for(let d=f.dependencies?.firstContext;d;d=d.next){if(typeof d.memoizedValue?.goTab==='function'){d.memoizedValue.goTab({activePath:'/publish/post',params:{draftId:"+str(draft_id)+"}});return true;}}}return false;})()")
        if not result:raise RuntimeError('当前小V猫版本无法自动打开，请在本地草稿箱按编号找到该草稿')
        return {'opened':True,'draft_id':draft_id}

    def close(self):
        try:
            if self.changed and self.cdp:
                current=self.bridge('McpServer.getSetting')
                modules=dict(current.get('writeModules') or {})
                modules['publish']=bool(self.setting.get('writeModules',{}).get('publish'))
                self.evaluate("window.CatBridge.getCall('McpServer.saveSetting',"+json.dumps({'writeModules':modules})+")")
        finally:
            if self.cdp:self.cdp.close();self.cdp=None
            if self.locked:WRITE_LOCK.release();self.locked=False
