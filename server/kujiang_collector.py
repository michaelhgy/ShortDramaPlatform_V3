"""Read-only Kujiang queries; each business type is a separate bound collector.

Source dates are accounting dates. The website warns some daily entries contain
interval income; never spread those amounts across guessed earning dates.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import urlsplit
from urllib.request import Request

from server import revenue_collectors as collectors
from server import revenue_query_settings as settings

DEFAULT_URL = "http://api.data.djff.asia/query/find.html"
PAGE_SIZE = 100
MAX_PAGES = 100
MAX_RESPONSE = 4 * 1024 * 1024


def api_base(source_url):
    parts = urlsplit(source_url)
    if (parts.scheme not in ("http", "https") or parts.hostname != "api.data.djff.asia"
            or parts.port not in (None, 80 if parts.scheme == "http" else 443)
            or parts.username is not None or parts.password is not None):
        raise ValueError("酷匠查单链接不属于已适配来源")
    return f"{parts.scheme}://{parts.netloc}/data"


def validate_page(page, source_url):
    match = re.search(r"\b(?:let|const|var)\s+apiUrl\s*=\s*['\"]([^'\"]+)['\"]", page)
    return bool(match and match.group(1).rstrip("/") == api_base(source_url)
                and "/external/find" in page and "videoAccountId" in page
                and "pageNum" in page and "pageSize" in page)


def _count(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"酷匠{label}不完整，未记为零收益")
    return value


def _money(value):
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("酷匠金额缺失或无效，未记为零收益")
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
            raise ValueError("酷匠金额无效或精度超出分，未保存")
        return amount.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError("酷匠金额无效，未保存") from exc


def parse_page(payload, channel, day, theater, page_num, page_size=PAGE_SIZE):
    if not isinstance(payload, dict) or type(payload.get("code")) is not int or payload["code"] != 200:
        message = payload.get("msg", "返回格式异常") if isinstance(payload, dict) else "返回格式异常"
        raise ValueError(f"酷匠查询失败：{str(message)[:200]}")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("records"), list) or not isinstance(data.get("summary"), dict):
        raise ValueError("酷匠查询结果缺少记录或汇总，未记为零收益")
    total = _count(data.get("total"), "记录总数")
    pages = _count(data.get("totalPages"), "总页数")
    if (type(data.get("pageNum")) is not int or data["pageNum"] != page_num
            or type(data.get("pageSize")) is not int or data["pageSize"] != page_size
            or pages != (total + page_size - 1) // page_size):
        raise ValueError("酷匠分页信息不一致，未保存部分金额")
    rows = data["records"]
    expected = min(page_size, max(0, total - (page_num - 1) * page_size))
    if len(rows) != expected or (total and page_num > pages):
        raise ValueError("酷匠分页记录不完整，未保存部分金额")
    summary = data["summary"]
    if (summary.get("theaterName") != theater or summary.get("recordDate") != f"{day} ~ {day}"
            or summary.get("videoAccountId") not in (None, channel)):
        raise ValueError("酷匠汇总类型、日期或账号不匹配，未保存")
    summary_amount = None if summary.get("income") is None else _money(summary["income"])
    if total and summary_amount is None:
        raise ValueError("酷匠汇总金额缺失，未保存")
    if not total and summary_amount not in (None, Decimal("0")):
        raise ValueError("酷匠空记录与汇总金额不一致，未保存")
    subtotal = Decimal("0.00")
    for row in rows:
        if (not isinstance(row, dict) or row.get("videoAccountId") != channel
                or row.get("theaterName") != theater or row.get("recordDate") != day):
            raise ValueError("酷匠记录类型、日期或账号不匹配，未保存")
        subtotal += _money(row.get("income"))
    # Preserve every record, including equal-value rows: no source record ID is
    # exposed, so identical rows cannot safely be deduplicated as individual items.
    signature = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
    return total, pages, summary_amount, subtotal, signature


def fetch_day(channel, day, collector_id):
    if collector_id not in collectors.KUJIANG_TYPES:
        raise ValueError("不是已适配的酷匠采集器")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", channel):
        raise ValueError("请填写正确的视频号 ID")
    date.fromisoformat(day)
    source = settings.source_url(collector_id, DEFAULT_URL)
    endpoint = api_base(source) + "/external/find"
    theater = collectors.KUJIANG_TYPES[collector_id][0]
    opener = settings.SafeOpener()
    total_amount = Decimal("0.00")
    first = None
    signatures = set()
    for page_num in range(1, MAX_PAGES + 1):
        body = {"tn": theater, "vid": channel, "sd": day, "ed": day,
                "pageNum": page_num, "pageSize": PAGE_SIZE}
        request = Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json", "User-Agent": "ShortDramaOpsV3/1.0"})
        with opener.open(request, timeout=40) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError("酷匠查询响应过大，未保存部分金额")
        payload = json.loads(raw.decode("utf-8"), parse_float=Decimal)
        total, pages, summary, subtotal, signature = parse_page(payload, channel, day, theater, page_num)
        if first is None:
            first = total, pages, summary
            if pages > MAX_PAGES:
                raise ValueError("酷匠记录超过本次查询上限，未保存部分金额")
        elif first != (total, pages, summary):
            raise ValueError("酷匠翻页期间数据变化，未保存部分金额，请重试")
        if not total:
            return "no_data", None, "酷匠正常返回：该日期没有收益记录"
        if signature in signatures:
            raise ValueError("酷匠重复返回同一页，未保存重复金额")
        signatures.add(signature)
        total_amount += subtotal
        if page_num == pages:
            if total_amount != summary:
                raise ValueError("酷匠明细与汇总金额不一致，未保存")
            return "success", total_amount, "按来源记录日期入账；来源提示部分单日金额可能包含区间收益，未拆分或均摊"
    raise ValueError("酷匠分页未完成，未保存部分金额")
