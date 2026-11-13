"""Guyan native's public Feishu query, with its own anonymous guest session.

No browser cookies, platform login, personal Feishu login or stored credentials
are used. Only the public page GET may follow its observed guest-login redirects;
requests containing account IDs never follow redirects.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from http.cookiejar import CookieJar
import json
import re
import threading
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

from server import revenue_query_settings as settings

DEFAULT_URL = "https://scnrzu35lckk.feishu.cn/share/base/query/shrcnmW22x9VpoIX5qKMILzfFne"
MAX_RESPONSE = 4 * 1024 * 1024
MAX_PAGES = 100
FIELD_NAMES = {"account": ("账号ID", 1), "period": ("日期", 1), "amount": ("汇总收益", 2)}


def _source(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "scnrzu35lckk.feishu.cn"
            or parts.port not in (None, 443) or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment
            or not re.fullmatch(r"/share/base/query/shrcn[A-Za-z0-9]+", parts.path)):
        raise ValueError("古言端原生查单链接不属于已适配来源")
    return parts


class GuestRedirect(HTTPRedirectHandler):
    def __init__(self, source, validator=None):
        super().__init__()
        self.source = (validator or _source)(source)

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        allowed = (parts.hostname == self.source.hostname and parts.path == self.source.path) or (
            parts.hostname in ("accounts.feishu.cn", "login.feishu.cn")
            and parts.path in ("/accounts/page/login", "/accounts/trap"))
        if (req.get_method() != "GET" or req.data is not None or parts.scheme != "https"
                or parts.port not in (None,443) or parts.username is not None or parts.password is not None or not allowed):
            raise ValueError("古言来源跳转超出公共匿名访问流程，请核对查单链接")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read(response):
    raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("古言来源响应过大，未保存部分收益")
    return raw


def _data(payload):
    if not isinstance(payload, dict) or type(payload.get("code")) is not int or payload["code"] != 0:
        code = payload.get("code") if isinstance(payload,dict) else None
        if code in (5, 401, 403):
            raise ValueError("古言来源匿名会话未就绪或已失效，请稍后重试；未写收益、未改累计基线")
        raise ValueError("古言来源查询失败或返回格式变化，未写入收益")
    if not isinstance(payload.get("data"),dict):
        raise ValueError("古言来源结果不完整，未记为零收益")
    return payload["data"]


def field_ids(payload):
    data = _data(payload)
    if isinstance(data.get("data"),str):
        data = json.loads(data["data"], parse_float=Decimal)
    if (not isinstance(data,dict) or not isinstance(data.get("fieldMap"),dict)
            or "古言" not in str(data.get("name", "")) or "端原生" not in str(data.get("name", ""))
            or data.get("banned") or data.get("isExceedMaxRecord") or data.get("isExceedBaseLimitMaxRows")):
        raise ValueError("古言端原生来源名称或字段结构不匹配，需要重新核对链接")
    result = {}
    for role,(name,kind) in FIELD_NAMES.items():
        matches = [key for key,value in data["fieldMap"].items()
                   if isinstance(value,dict) and value.get("name")==name and type(value.get("type")) is int and value["type"]==kind]
        if len(matches)!=1:
            raise ValueError(f"古言来源的{name}字段缺失或不唯一，需要重新适配")
        result[role] = matches[0]
    prop = data.get("queryFormViewProperty") or {}
    info = (prop.get("fieldInfos") or {}).get(result["account"],{})
    if info.get("visible") is not True or info.get("required") is not True:
        raise ValueError("古言账号查询条件已变化，未发送账号查询")
    return result


def _value(raw):
    if isinstance(raw,dict):
        if "value" in raw:return _value(raw["value"])
        if "text" in raw:return _value(raw["text"])
        raise ValueError("古言来源单元格结构已变化")
    if isinstance(raw,list):return "".join(str(_value(item)) for item in raw)
    return raw


def _range(raw):
    text = str(_value(raw) or "").strip()
    match = re.fullmatch(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*[-~至—–]\s*(\d{4})年(\d{1,2})月(\d{1,2})日",text)
    if match:
        parts = list(map(int,match.groups())); start,end = date(*parts[:3]),date(*parts[3:])
    else:
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:\s*[-~至—–]\s*(\d{4}-\d{2}-\d{2}))?",text)
        if not match:raise ValueError("古言来源日期区间无法核对，未推算日收益")
        start,end = date.fromisoformat(match[1]),date.fromisoformat(match[2] or match[1])
    if end<start or start.strftime("%Y-%m")!=end.strftime("%Y-%m"):
        raise ValueError("古言来源区间倒置或跨月份，请人工核对收益期间")
    return start,end


def _amount(raw):
    value = _value(raw)
    if isinstance(value,bool) or value is None or not isinstance(value,(str,int,float,Decimal)):
        raise ValueError("古言汇总收益缺失或无效，未记零")
    try:
        amount=Decimal(str(value))
        if not amount.is_finite() or amount<0 or amount!=amount.quantize(Decimal("0.01")):
            raise ValueError("古言汇总收益无效，未写入收益")
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation as exc:raise ValueError("古言汇总收益无效，未写入收益") from exc


def parse_records(rows, fields, channel, period="unknown"):
    matched=[]
    for row in rows:
        if not isinstance(row,dict) or fields["account"] not in row:
            raise ValueError("古言结果缺少账号字段，未写入收益")
        if str(_value(row[fields["account"]]) or "").strip()!=channel:
            continue  # The original form uses contains; only an exact case-sensitive ID counts.
        if fields["period"] not in row or fields["amount"] not in row:
            raise ValueError("古言结果缺少收益或日期，未记为零")
        start,end=_range(row[fields["period"]])
        if period!="unknown" and start.strftime("%Y-%m")!=period:
            raise ValueError("古言来源月份与查单管理的收益期间不一致，请核对新期间")
        matched.append((start,end,_amount(row[fields["amount"]])))
    if not matched:return "no_data",None,"古言正常返回：没有完全匹配的账号记录"
    matched.sort()
    for previous,current in zip(matched,matched[1:]):
        if current[0].strftime("%Y-%m")!=previous[0].strftime("%Y-%m") or current[0]<=previous[1]:
            raise ValueError("古言同一账号存在重叠区间、重复汇总或多个收益月份，未叠加金额，请人工核对")
    total=sum((item[2] for item in matched),Decimal("0.00"))
    return "success",total,(f"来源区间 {matched[0][0].isoformat()} 至 {matched[-1][1].isoformat()}，汇总 {total:.2f} 元；"
                            "首次归采集日期，后续只记累计增量，不拆分日收益。工作日12点左右更新，节假日不更新。")


class GuestClient:
    def __init__(self,source,validator=None,resolve_fields=None,parse_rows=None,allow_empty_records=False):
        self.allow_empty_records=allow_empty_records
        self.validator=validator or _source
        self.resolve_fields=resolve_fields or field_ids
        self.parse_rows=parse_rows or parse_records
        self.source=source;self.parts=self.validator(source);self.jar=CookieJar();self.ready=False;self.lock=threading.Lock()
        self.opener=settings.SafeOpener()
        self.opener.opener=build_opener(HTTPCookieProcessor(self.jar),settings.NoRedirect())

    def prepare(self):
        if self.ready:return
        opener=build_opener(HTTPCookieProcessor(self.jar),GuestRedirect(self.source,self.validator))
        with opener.open(Request(self.source,headers={"User-Agent":"Mozilla/5.0"}),timeout=25) as response:
            final=urlsplit(response.geturl());_read(response)
        if final.hostname!=self.parts.hostname or final.path!=self.parts.path:
            raise ValueError("古言公共查询未能建立匿名会话，需人工核对来源访问状态")
        guest=next((c.value for c in self.jar if c.name=="is_anonymous_session"),None)
        if guest!="1":raise ValueError("古言来源未返回匿名查询会话，未使用个人飞书登录")
        self.ready=True

    def request(self,endpoint,payload):
        csrf=next((c.value for c in self.jar if c.name=="_csrf_token"),"")
        # get_share issues the form-specific CSRF cookie after guest login.
        # swp_csrf_token belongs to passport and must not be used for this API.
        if not csrf and endpoint!="get_share":raise ValueError("古言匿名会话缺少请求校验信息，请稍后重试")
        root=f"https://{self.parts.netloc}/space/api/bitable/form/external/"
        headers={"User-Agent":"Mozilla/5.0","Referer":self.source,"Content-Type":"application/json"}
        if csrf:headers["X-CSRFToken"]=csrf
        req=Request(root+endpoint,data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),headers=headers)
        with self.opener.open(req,timeout=25) as response:raw=_read(response)
        return json.loads(raw.decode("utf-8"),parse_float=Decimal)

    def query(self,channel,period):
        with self.lock:
            try:
                self.prepare()
                token=self.parts.path.rsplit("/",1)[-1]
                fields=self.resolve_fields(self.request("get_share",{"shareToken":token}))
                condition={"fieldId":fields["account"],"fieldType":1,"operator":"contains","value":[channel],"conditionId":"con"+uuid.uuid4().hex[:8]}
                payload={"shareToken":token,"filter":json.dumps({"conditions":[condition],"conjunction":"and"},separators=(",",":"))}
                records={}; expected=None; offsets=set()
                for _ in range(MAX_PAGES):
                    data=_data(self.request("list_records",payload))
                    total=data.get("total"); ids=data.get("recordIDs"); mapping=data.get("recordMap")
                    if self.allow_empty_records and total == 0 and data.get("hasMore") is False and ids is None and mapping is None:
                        ids, mapping = [], {}
                    if (type(total) is not int or total<0 or type(data.get("hasMore")) is not bool
                            or not isinstance(ids,list) or not isinstance(mapping,dict)
                            or any(not isinstance(key,str) for key in ids) or len(set(ids))!=len(ids) or set(ids)!=set(mapping)):
                        raise ValueError("古言分页数据不完整，未保存部分收益")
                    if expected is not None and total!=expected:raise ValueError("古言翻页期间记录总数变化，请重新查询")
                    expected=total
                    if set(records).intersection(ids):raise ValueError("古言重复返回记录，未保存重复金额")
                    records.update(mapping)
                    if len(records)>total:raise ValueError("古言记录数超过来源汇总，未保存")
                    if not data["hasMore"]:
                        if len(records)!=total:raise ValueError("古言记录未全部返回，未保存部分收益")
                        return self.parse_rows(list(records.values()),fields,channel,period)
                    offset=data.get("nextOffset")
                    if type(offset) not in (int,str) or offset in offsets or not ids:
                        raise ValueError("古言分页游标缺失或重复，未保存部分收益")
                    offsets.add(offset);payload["offset"]=offset
                raise ValueError("古言分页超过查询上限，未保存部分收益")
            except Exception:
                self.ready=False;self.jar.clear()
                raise


_clients={}
_clients_lock=threading.Lock()


def fetch_latest(channel,config):
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}",channel):raise ValueError("请填写正确的视频号 ID")
    source=config.get("source_url",DEFAULT_URL);_source(source)
    period=config.get("source_period","unknown")
    with _clients_lock:
        client=_clients.get(source)
        if client is None:
            client=GuestClient(source);_clients[source]=client
    return client.query(channel,period)
