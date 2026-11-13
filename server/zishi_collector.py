"""Zishi's four independent channels. Monthly totals are credited once;
explicitly dated daily observations are supporting evidence, never added twice.
"""
from datetime import date, timedelta
from decimal import Decimal
import json
import re
import threading
from urllib.parse import urlsplit, urlencode
from urllib.request import Request
from server import guyan_collector as feishu
from server import revenue_query_settings as settings

FEISHU_HOST = "q7w8vltyes.feishu.cn"
YIC_HOSTS = {"c3andggd.yichafen.com", "s6w549ed.yichafen.com"}


def validate_source(url, host):
    parts = urlsplit(url)
    pattern = r"/share/base/query/shrcn[A-Za-z0-9]+" if host == FEISHU_HOST else r"/qz/[A-Za-z0-9]+/?"
    if (parts.scheme != "https" or parts.hostname != host or parts.port not in (None, 443)
            or parts.username is not None or parts.password is not None or parts.query or parts.fragment
            or not re.fullmatch(pattern, parts.path)):
        raise ValueError("子诗链接不属于该业务已适配的查询来源")
    return parts


def money(value):
    value = feishu._value(value)
    if isinstance(value, bool) or value is None:
        raise ValueError("子诗收益金额缺失或格式变化，未记零")
    text = str(value).strip()
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise ValueError("子诗收益金额无法识别，未记零")
    amount = Decimal(text.replace(",", ""))
    if not amount.is_finite() or amount < 0:
        raise ValueError("子诗收益金额不合法")
    return amount


def label_period(label, today):
    """Read explicit source labels, never infer yesterday from the link's name."""
    label = re.sub(r"\s+", "", label)
    # 11.4广告收益 / 昨日11.3广告收益 / 至11.4当月收益
    md = re.search(r"(?:(\d{4})[年./-])?(\d{1,2})[月./-](\d{1,2})(?:日|号)?", label)
    if md:
        year = int(md[1]) if md[1] else today.year - (int(md[2]) > today.month)
        day = date(year, int(md[2]), int(md[3]))
        if day >= today:
            raise ValueError("子诗来源日期为今天或未来，等待已结算结果")
        kind = "month" if any(word in label for word in ("累计", "当月", "本月")) else "day"
        return kind, day.isoformat()[:7], day.isoformat()
    month = re.search(r"(?:(\d{4})年)?(\d{1,2})月", label)
    if month and any(word in label for word in ("累计", "总收益", "当月", "本月")):
        year = int(month[1]) if month[1] else today.year - (int(month[2]) > today.month)
        first = date(year, int(month[2]), 1)
        return "month", first.isoformat()[:7], ""
    raise ValueError("子诗结果缺少明确的收益日期或月份，不能按链接标题猜测")


def observation(label, amount, today):
    kind, period, source_date = label_period(label, today)
    return {"kind": kind, "period": period, "source_date": source_date,
            "label": label, "amount": format(money(amount), "f")}


def resolve_fields(payload):
    data = feishu._data(payload)
    if isinstance(data.get("data"), str):
        data = json.loads(data["data"])
    if not isinstance(data.get("fieldMap"), dict) or any(data.get(x) for x in ("banned", "isExceedMaxRecord", "isExceedBaseLimitMaxRows")):
        raise ValueError("子诗飞书查询结构或访问权限变化")
    fields = data["fieldMap"]
    visible = {x.get("fieldId") for x in (data.get("queryFormViewProperty", {}).get("queryFormConfig", {}).get("resultFieldInfos") or []) if x.get("permission") == 1}
    accounts = [k for k, v in fields.items() if v.get("type") == 1 and v.get("name", "").strip().lower() == "视频号id"]
    amounts = [k for k, v in fields.items() if k in visible and v.get("type") == 2 and "收益" in v.get("name", "")]
    if len(accounts) != 1 or len(amounts) != 1:
        raise ValueError("子诗账号或收益字段缺失、不唯一，需要核对链接")
    info = (data.get("queryFormViewProperty", {}).get("fieldInfos") or {}).get(accounts[0], {})
    if info.get("required") is not True or info.get("visible") is not True:
        raise ValueError("子诗账号查询条件变化，未发送账号查询")
    return {"account": accounts[0], "amount": amounts[0], "label": fields[amounts[0]]["name"]}


def parse_records(rows, fields, channel, today):
    values = []
    for row in rows:
        if not isinstance(row, dict) or fields["account"] not in row:
            raise ValueError("子诗结果缺少账号字段")
        if str(feishu._value(row[fields["account"]]) or "").strip() == channel:
            if fields["amount"] not in row:
                raise ValueError("子诗结果缺少收益，未记零")
            values.append(money(row[fields["amount"]]))
    if not values:
        return None
    if len(values) > 1 and label_period(fields["label"], date.fromisoformat(today))[0] == "month":
        raise ValueError("子诗月累计返回多条同账号记录，无法确认是否重复汇总，未相加")
    # Expert daily rows can be per-drama; sum only the one visible income column.
    return observation(fields["label"], sum(values, Decimal("0")), date.fromisoformat(today))


_clients = {}
_lock = threading.Lock()


def fetch_feishu(url, channel, today):
    with _lock:
        client = _clients.get(url)
        if client is None:
            client = feishu.GuestClient(url, validator=lambda u: validate_source(u, FEISHU_HOST),
                                        resolve_fields=resolve_fields, parse_rows=parse_records, allow_empty_records=True)
            _clients[url] = client
    try:
        return client.query(channel, today.isoformat())
    except Exception as exc:
        raise ValueError(str(exc).replace("古言", "子诗")) from exc


def parse_yichafen(html, channel, today):
    from server.v2_revenue_service import _TableParser
    parser = _TableParser()
    parser.feed(html if re.search(r"<tr\b", html, re.I) else "<tr>" + html + "</tr>")
    pairs = [(a.strip().rstrip(":："), b.strip()) for row in parser.rows for a, b in zip(row[::2], row[1::2])]
    accounts = [v for k, v in pairs if k.lower() == "视频号id"]
    amounts = [(k, v) for k, v in pairs if "收益" in k]
    if accounts != [channel] or len(amounts) != 1:
        raise ValueError("子诗结果账号不一致或收益字段不唯一，未写入收益")
    return observation(*amounts[0], today)


def fetch_yichafen(url, channel, today):
    parts = validate_source(url, urlsplit(url).hostname)
    if parts.hostname not in YIC_HOSTS:
        raise ValueError("子诗查询来源不正确")
    opener = settings.SafeOpener()
    headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
    def read(request):
        with opener.open(request, timeout=25) as response:
            return feishu._read(response).decode("utf-8")
    html = read(Request(url, headers=headers))
    inputs = re.findall(r'<input\b[^>]*>', html, re.I)
    if not any(re.search(r'name=[\"\']s_shipinhaoid[\"\']', x) for x in inputs):
        raise ValueError("子诗来源账号输入字段变化，未发送查询")
    sq = re.search(r"/public/verifycondition/sqcode/([A-Za-z0-9]+)/", html)
    if not sq:
        raise ValueError("子诗页面缺少查询标识")
    endpoint = f"https://{parts.hostname}/public/verifycondition/sqcode/{sq[1]}/from_device/mobile.html"
    result = json.loads(read(Request(endpoint, data=urlencode({"s_shipinhaoid": channel}).encode(),
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"})))
    if result.get("captchaRequired") or result.get("showPicVerify"):
        raise ValueError("子诗来源要求人工验证码，当前查询未完成，未记零收益")
    if result.get("status") != 1:
        if result.get("errNo") == 100:
            return None
        raise ValueError(str(result.get("info") or "子诗查询失败"))
    return parse_yichafen(read(Request(f"https://{parts.hostname}/public/queryresult/from_device/mobile.html", headers=headers)), channel, today)


def fetch_observation(url, channel, today):
    result = fetch_feishu(url, channel, today) if urlsplit(url).hostname == FEISHU_HOST else fetch_yichafen(url, channel, today)
    return dict(result, source_url=url) if result else None


def fetch_month(channel, collector_id, config, period, today):
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", channel):
        raise ValueError("请填写正确的视频号 ID")
    if period == today.isoformat()[:7]:
        url = config["source_url"]
        daily_url = config.get("daily_url", "")
    else:
        url = config.get("previous_month_url", "")
        daily_url = ""
        if not url:
            return "pending", None, "该月份没有专用查单链接，不虚构历史收益", []
    month = fetch_observation(url, channel, today)
    if not month:
        return "pending", None, "月累计入口未匹配到该ID；可能未更新或业务类型不符，保留待重试", []
    if month["kind"] != "month" or month["period"] != period:
        return "pending", None, f"来源实际为{month['label']}，与待采月份{period}不符，未写收益或改变基线", [month]
    evidence = [month]
    message = f"{month['label']}：{month['amount']}元"
    if daily_url:
        daily = fetch_observation(daily_url, channel, today)
        if not daily:
            return "pending", None, message + "；昨日入口未匹配到ID，无法交叉核对，保留重试", evidence
        evidence.append(daily)
        if daily["kind"] != "day":
            raise ValueError("昨日入口实际返回累计收益，请核对两个链接是否填反")
        message += f"；日入口实际日期{daily['source_date']}：{daily['amount']}元"
        if daily["period"] == month["period"]:
            if month["source_date"] and daily["source_date"] > month["source_date"]:
                return "pending", None, message + "；月累计更新落后于日入口，暂不入账", evidence
            if Decimal(daily["amount"]) > Decimal(month["amount"]):
                return "pending", None, message + "；单日超过月累计，两个入口不同步，暂不入账", evidence
            message += "；单日未超过月累计（不能据此断定累计已更新到昨日）"
        else:
            message += "；两个入口跨月，不比较金额"
        if daily["source_date"] < (today - timedelta(days=1)).isoformat():
            message += "；日入口有延迟，未将其当成昨天"
    message += "；月累计增量归采集日，日金额仅核对、不另加"
    return "success", Decimal(month["amount"]), message, evidence
