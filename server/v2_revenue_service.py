"""V3 theater revenue adapters, collection policies and compatibility read models."""
from __future__ import annotations

import re
import sqlite3
import uuid
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.request import build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from server import revenue_collection_state as state

SOURCE_URL = "https://vd.xingvan.com/duangg.html"
QINGNING_LPP_URL = "https://vd.xingvan.com/index.php?s=Home/Home/orderlookupquery"
DINGHAO_NATIVE_URL = "https://zyu.wozhangwan.com/api/api/order/getVideoAdIncome"
MONEY = Decimal("0.01")

from server.revenue_collectors import REVENUE_ADAPTERS
from server import revenue_collectors as collectors
from server import revenue_query_settings as query_settings

# New cumulative adapters may register a verified (channel_id, YYYY-MM) query.
# Existing touch/huasheng parsers do not accept a month; never fabricate support.
MONTHLY_FETCHERS = {}


def revenue_collector_inventory(conn: sqlite3.Connection) -> dict[str, object]:
    """Expose enabled and registered theaters without pretending unknown ones are supported."""
    rows = conn.execute("SELECT id,name,status FROM theaters ORDER BY name,id").fetchall()
    account_counts = {
        str(row["theater_id"]): int(row["count"])
        for row in conn.execute(
            """SELECT theater_id,COUNT(*) AS count FROM accounts
               WHERE status<>'注销' GROUP BY theater_id"""
        ).fetchall()
    }
    last_runs = {
        str(row["theater_id"]): dict(row)
        for row in conn.execute(
            """SELECT theater_id,MAX(collected_at) AS collected_at,
                      MAX(revenue_date) AS revenue_date
               FROM v2_revenue_collection_attempts GROUP BY theater_id"""
        ).fetchall()
    }
    items = []
    for row in rows:
        bound_ids = collectors.theater_ids(conn,str(row['id']))
        bound = [collectors.definition(key) for key in bound_ids if collectors.definition(key)]
        capability = bound[0] if bound else None
        last = last_runs.get(str(row["id"]), {})
        items.append({
            "id": row["id"], "name": row["name"], "status": row["status"],
            "account_count": account_counts.get(str(row["id"]), 0),
            "collector_ids": bound_ids, "collectors": bound,
            "adapter_key": capability.get("adapter_key", "") if capability else "",
            "adapter_status": capability.get("status", "unimplemented") if capability else "unimplemented",
            "query_mode": capability.get("query_mode", "") if capability else "",
            "date_precision": capability.get("date_precision", "unknown") if capability else "unknown",
            "supports_detail": bool(capability.get("supports_detail")) if capability else False,
            "supports_month_query": bool(capability.get("supports_month_query")) if capability else False,
            "runtime_verified": bool(capability.get("runtime_verified")) if capability else False,
            "detail_persistence_enabled": False,
            "first_collection": "descending_days_until_7_empty" if capability and capability["date_precision"] == "day" else ("current_and_previous_2_months" if capability and capability.get("supports_month_query") else "current_cumulative_only"),
            "notes": capability.get("notes", "尚未配置收益采集器") if capability else "尚未配置收益采集器",
            "last_collected_at": last.get("collected_at", ""),
            "last_revenue_date": last.get("revenue_date", ""),
        })
    backfills = [dict(r) for r in conn.execute("SELECT * FROM v3_revenue_backfills")] if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='v3_revenue_backfills'").fetchone() else []
    return {"items": items, "supported_theaters": [item["name"] for item in items if item["adapter_status"] == "ready"],
            "backfills": backfills, "definitions": collectors.definitions()}


class RevenueError(RuntimeError):
    pass


@dataclass(frozen=True)
class QingningRow:
    rank: int
    video_id: str
    drama_name: str
    video_views: int
    drama_views: int
    gross_revenue: Decimal


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.rows: list[list[str]] = []; self._row: list[str] | None = None; self._cell: list[str] | None = None
    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr": self._row = []
        elif tag in {"td", "th"} and self._row is not None: self._cell = []
    def handle_data(self, data: str) -> None:
        if self._cell is not None: self._cell.append(data)
    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip()); self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row: self.rows.append(self._row)
            self._row = None


def _amount(value: str) -> Decimal:
    text = str(value or "").strip()
    # Only remove known display formatting; an empty cell or an error message
    # containing digits is not a numeric zero (or a positive revenue).
    match = re.fullmatch(r"[¥￥]?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*元?", text)
    if not match:
        raise RevenueError(f"青柠收益或播放数值缺失或无法识别：{value}")
    return _strict_source_amount(match.group(1).replace(",", ""), "青柠")


def _decode(raw: bytes, charset: str | None) -> str:
    for encoding in (charset, "utf-8", "gb18030"):
        if not encoding: continue
        try: text = raw.decode(encoding)
        except (LookupError, UnicodeDecodeError): continue
        if any(marker in text for marker in ("剧目", "收益", "暂时", "记录")): return text
    return raw.decode("utf-8", errors="replace")


def _source_opener():
    return query_settings.SafeOpener() if query_settings.ACTIVE.get() else build_opener(HTTPCookieProcessor(CookieJar()))


def _source_open(request, timeout=40):
    return query_settings.SafeOpener().open(request, timeout=timeout) if query_settings.ACTIVE.get() else urlopen(request, timeout=timeout)


def _fetch_page(channel_id: str, revenue_date: str, page: int) -> tuple[list[QingningRow], int, int | None, Decimal | None]:
    body = urlencode({"startgdate": revenue_date, "endgdate": revenue_date, "spfindid": channel_id, "spvideoid": "", "p": page}).encode("ascii")
    request = Request(query_settings.source_url("qingning", SOURCE_URL), data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "ShortDramaOpsV2/1.0"})
    with _source_open(request, timeout=40) as response:
        text = _decode(response.read(), response.headers.get_content_charset())
    parser = _TableParser(); parser.feed(text)
    record_match = re.search(r"共\s*(\d+)\s*条记录", text)
    rows = [cells for cells in parser.rows if len(cells) >= 7 and cells[0].strip().isdigit()]
    details = [QingningRow(int(cells[0]), cells[2], cells[3], int(_amount(cells[4])), int(_amount(cells[5])), _amount(cells[6])) for cells in rows]
    totals = [cells for cells in parser.rows if any(cell.strip() == "总计" for cell in cells)]
    stated_total = _amount(totals[-1][-1]) if totals and totals[-1] else None
    stated_records = int(record_match.group(1)) if record_match else None
    pages = max([int(value) for value in re.findall(r"[?&]p=(\d+)", text)] or [1])
    if record_match: records = stated_records
    elif re.search(r"暂时\s*还没有数据", text): records = 0
    elif rows and pages == 1: records = len(rows)
    else: raise RevenueError("青柠返回页面无法识别为正常数据或正常空数据")
    if records and not rows: raise RevenueError("青柠页面显示有记录，但未识别到收益明细")
    return details, pages, stated_records, stated_total


def fetch_qingning_day_details(channel_id: str, revenue_date: str) -> tuple[Decimal | None, list[QingningRow]]:
    first, page_count, stated_records, stated_total = _fetch_page(channel_id, revenue_date, 1)
    if not first and stated_total is None: return None, []
    details = list(first)
    for page in range(2, page_count + 1):
        page_details, _, _, _ = _fetch_page(channel_id, revenue_date, page); details.extend(page_details)
    if stated_records is not None and len({item.video_id for item in details}) != stated_records:
        raise RevenueError("青柠来源记录数与视频明细不一致，未写入收益数据")
    calculated = sum((item.gross_revenue for item in details), Decimal("0")).quantize(MONEY, rounding=ROUND_HALF_UP)
    if stated_total is not None and abs(calculated - stated_total) > MONEY:
        raise RevenueError("青柠页面总计与收益明细不一致，未写入收益数据")
    return calculated, details


def fetch_qingning_day(channel_id: str, revenue_date: str) -> Decimal | None:
    return fetch_qingning_day_details(channel_id, revenue_date)[0]


def _post_json(url: str, payload: dict[str, str]) -> dict[str, object]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "ShortDramaOpsV2/1.0"})
    with _source_open(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def _strict_source_amount(value, label):
    # Source totals must be explicit numbers. Never turn a missing/garbled value
    # into zero, which would prematurely stop first-time backfill.
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise RevenueError(f'{label}缺少有效收益金额')
    text = str(value).strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', text):
        raise RevenueError(f'{label}收益金额无法识别')
    try:
        amount = Decimal(text)
        if not amount.is_finite() or amount < 0:
            raise RevenueError(f'{label}收益金额无效')
        return amount.quantize(MONEY, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise RevenueError(f'{label}收益金额无效') from exc


def fetch_dinghao_day(channel_id: str, revenue_date: str) -> tuple[str, Decimal | None, str]:
    """The supplied dual-tab page's native-channel advertising-income API."""
    try:
        data = _post_json(DINGHAO_NATIVE_URL, {
            "income_date_start": f"{revenue_date} 00:00:00",
            "income_date_end": f"{revenue_date} 23:59:59",
            "advertiser_id": channel_id, "channel_name": "", "drama_name": "",
        })
        if not isinstance(data, dict) or type(data.get("status_code")) is not int or data["status_code"] != 1:
            return "failed", None, str(data.get("msg") or "顶好端原生查询失败") if isinstance(data, dict) else "顶好端原生返回格式不正确"
        detail = data.get('data')
        if not isinstance(detail, dict):
            raise RevenueError('顶好端原生缺少收益结果')
        amount = _strict_source_amount(detail.get('amount'), '顶好端原生')
        if amount == 0:
            return 'no_data', None, '顶好端原生查询成功：该日期没有收益记录'
        return 'success', amount, ''
    except Exception as exc:
        return 'failed', None, str(exc)


def parse_qingning_lpp_result(data) -> tuple[str, Decimal | None, str]:
    if not isinstance(data, dict) or data.get('ok') is not True:
        message = data.get('message') if isinstance(data, dict) else None
        raise RevenueError(str(message or '青柠绿泡泡查询失败或返回格式不正确'))
    rows = data.get('rows')
    count, channels = data.get('count'), data.get('channel_count')
    if not isinstance(rows, list) or type(count) is not int or count != len(rows):
        raise RevenueError('青柠绿泡泡剧目记录数与返回列表不一致')
    if type(channels) is not int or channels != 1:
        raise RevenueError('青柠绿泡泡返回的账号数量与单账号查询不一致')
    total = _strict_source_amount(data.get('total'), '青柠绿泡泡总计')
    amounts = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get('drama_name') or '').strip():
            raise RevenueError('青柠绿泡泡缺少剧目字段')
        if type(row.get('video_count')) is not int or row['video_count'] < 0:
            raise RevenueError('青柠绿泡泡关联视频数量无法识别')
        amounts.append(_strict_source_amount(row.get('amount'), '青柠绿泡泡剧目'))
    if sum(amounts, Decimal('0.00')) != total:
        raise RevenueError('青柠绿泡泡总计与剧目收益不一致，未写入收益数据')
    if not rows:
        return 'no_data', None, '青柠绿泡泡正常返回：该日暂无结算数据'
    return 'success', total, ''


def fetch_qingning_lpp_day(channel_id: str, revenue_date: str) -> tuple[str, Decimal | None, str]:
    """Read-only daily lookup, not video registration/import/association APIs."""
    try:
        if not channel_id.strip() or re.search(r'[,，\s]', channel_id.strip()):
            raise RevenueError('青柠绿泡泡需提供单个视频号 ID')
        body = urlencode({'spfindid': channel_id.strip(), 'start_date': revenue_date,
                          'end_date': revenue_date}).encode('utf-8')
        request = Request(QINGNING_LPP_URL, data=body, headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': query_settings.source_url('qingning_lpp', 'https://vd.xingvan.com/lpp.html'),
            'User-Agent': 'ShortDramaOpsV3/1.0',
        })
        with _source_open(request, timeout=40) as response:
            data = json.loads(response.read().decode('utf-8'), parse_float=Decimal)
        return parse_qingning_lpp_result(data)
    except Exception as exc:
        return 'failed', None, str(exc)


def fetch_touch_latest(channel_id: str) -> tuple[str, Decimal | None, str]:
    try:
        page_url = query_settings.source_url("touch", collectors.definition("touch")["source_url"])
        headers = {"User-Agent": "Mozilla/5.0", "Referer": page_url}
        opener = _source_opener()
        with opener.open(Request(page_url, headers=headers), timeout=40) as response: html = response.read().decode("utf-8", errors="replace")
        match = re.search(r"sqcode[\"']?\s*[:=]\s*[\"']([^\"']+)", html) or re.search(r"/verifycondition/sqcode/([^/]+)/", html)
        if not match: raise RevenueError("触摸页面缺少 sqcode")
        endpoint = f"https://c3andggd.yichafen.com/public/verifycondition/sqcode/{match.group(1)}/from_device/mobile.html"
        with opener.open(Request(endpoint, data=urlencode({"s_shipinhaoid": channel_id}).encode(), headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}), timeout=40) as response: result = json.loads(response.read().decode("utf-8"))
        if result.get("captchaRequired"):
            return "failed", None, "触摸端原生/IAA来源要求人工验证码验证，请先人工核对，未写入收益"
        if result.get("status") != 1: return ("no_data", None, str(result.get("info") or "没有数据")) if result.get("errNo") == 100 else ("failed", None, str(result.get("info") or "触摸来源查询失败"))
        with opener.open(Request("https://c3andggd.yichafen.com/public/queryresult/from_device/mobile.html", headers=headers), timeout=40) as response:
            html = response.read().decode("utf-8", errors="replace")
        parser = _TableParser()
        parser.feed(html if re.search(r"<tr\b", html, re.I) else "<tr>"+html+"</tr>")
        amounts = [cells[index+1] for cells in parser.rows for index, label in enumerate(cells[:-1])
                   if label.strip().rstrip("：:") == "广告收益"]
        if len(amounts) != 1:
            raise RevenueError("触摸结果缺少唯一的广告收益字段，需要核对结果，未写入收益")
        return "success", _strict_source_amount(amounts[0].strip(), "触摸"), ""
    except Exception as exc: return "failed", None, str(exc)


def fetch_huasheng_latest(channel_id: str) -> tuple[str, Decimal | None, str]:
    """Public Huasheng source query; it returns an account-period total only."""
    try:
        page_url = query_settings.source_url("huasheng", query_settings.DEFAULT_HUASHENG)
        token = urlsplit(page_url).path.rsplit("/", 1)[-1]
        opener = _source_opener(); headers = {"User-Agent": "Mozilla/5.0", "Referer": page_url, "Content-Type": "application/json"}
        with opener.open(Request(page_url, headers=headers), timeout=40): pass
        root = page_url.split("/share/")[0] + "/space/api/bitable/form/external/"
        def request(endpoint: str, payload: dict[str, object]) -> dict[str, object]:
            with opener.open(Request(root + endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers), timeout=40) as response: data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict) or type(data.get("code")) is not int or data["code"] != 0:
                raise RevenueError(str(data.get("msg") or "花生来源查询失败") if isinstance(data, dict) else "花生来源返回格式错误")
            if not isinstance(data.get("data"), dict):
                raise RevenueError("花生来源结果缺失，未记为无收益记录")
            return data["data"]
        request("get_share", {"shareToken": token})
        condition = {"fieldId": "fld3P2QILX", "fieldType": 1, "operator": "contains", "value": [channel_id], "conditionId": f"con{uuid.uuid4().hex[:8]}"}
        data = request("list_records", {"filter": json.dumps({"conditions": [condition], "conjunction": "and"}, separators=(",", ":")), "offset": 0, "shareToken": token})
        total_records = data.get("total")
        if type(total_records) is not int or total_records < 0 or data.get("hasMore"):
            raise RevenueError("花生来源缺少完整记录数或仍有下一页，未记为无收益记录")
        rows = list((data.get("recordMap") or {}).values()) or list(data.get("records") or data.get("items") or [])
        if len(rows) != total_records:
            raise RevenueError("花生来源记录数与返回结果不一致，需要核对分页或字段；未写入收益")
        if not total_records:
            return "no_data", None, "花生正常返回：未找到该账号记录"
        if not rows:
            raise RevenueError("花生来源记录数与返回结果不一致，需要核对分页或字段；未写入收益")
        def field_text(raw):
            if isinstance(raw, dict): raw = raw.get("value", raw.get("text"))
            if isinstance(raw, list): return "".join(field_text(value) for value in raw)
            return "" if raw is None else str(raw).strip()
        total, matched = Decimal("0"), 0
        for row in rows:
            fields = row.get("fields") or row
            if "fld3P2QILX" not in fields or "fld4Za6Nvm" not in fields:
                raise RevenueError("花生来源字段已变化，需要重新适配；未写入收益")
            if field_text(fields["fld3P2QILX"]) != channel_id:
                continue
            total += _strict_source_amount(field_text(fields["fld4Za6Nvm"]), "花生")
            matched += 1
        if not matched:
            return "no_data", None, "花生未找到完全匹配的账号，未写入收益"
        return "success", total, ""
    except Exception as exc: return "failed", None, str(exc)


def _dates(start_date: str, end_date: str) -> list[str]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start: raise ValueError("结束日期不能早于开始日期")
    if (end - start).days >= 90: raise ValueError("一次补采最多 90 天，请分段进行")
    return [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]


def _save_qingning_details(conn, account, revenue_date, details, attempt_id, now):
    for detail in details:
        drama = conn.execute("SELECT id FROM dramas WHERE theater_id=? AND current_name=?", (account["theater_id"], detail.drama_name)).fetchone()
        conn.execute("""INSERT INTO v2_revenue_video_details
        (id, attempt_id, account_id, theater_id, revenue_date, source_video_id, source_drama_name, video_views, drama_views, gross_revenue, source_rank, matched_drama_id, match_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(revenue_date, account_id, source_video_id) DO UPDATE SET attempt_id=excluded.attempt_id, source_drama_name=excluded.source_drama_name, video_views=excluded.video_views, drama_views=excluded.drama_views, gross_revenue=excluded.gross_revenue, source_rank=excluded.source_rank, matched_drama_id=excluded.matched_drama_id, match_status=excluded.match_status, updated_at=excluded.updated_at""",
            (uuid.uuid4().hex, attempt_id, account["id"], account["theater_id"], revenue_date, detail.video_id, detail.drama_name, detail.video_views, detail.drama_views, format(detail.gross_revenue, 'f'), detail.rank, drama["id"] if drama else None, "matched" if drama else "unmatched", now, now))


def _accounts(conn, theater_names, account_ids):
    selected = None if theater_names is None else set(theater_names)
    if selected is not None:
        known = {r[0] for r in conn.execute('SELECT name FROM theaters')}
        if selected-known:
            raise ValueError('以下剧场不存在或尚未实现收益采集器：'+'、'.join(sorted(selected-known)))
    ids = None if account_ids is None else set(map(str, account_ids))
    rows = conn.execute("""SELECT a.id,a.nickname,a.channel_id,a.theater_id,t.name theater_name
        FROM accounts a JOIN theaters t ON t.id=a.theater_id
        WHERE a.status<>'注销' ORDER BY t.name,a.nickname""")
    return [dict(row,revenue_collector_id=collectors.account_id(conn,row['id'],row['theater_id']))
            for row in rows if (selected is None or row['theater_name'] in selected)
            and (ids is None or str(row['id']) in ids)]


def _months(day):
    value = date.fromisoformat(day)
    index = value.year * 12 + value.month - 1
    return [f"{(index-offset)//12:04d}-{(index-offset)%12+1:02d}" for offset in range(3)]


def _cumulative_periods(spec, today, anchor_date=None):
    if spec.get('adapter_key') in collectors.ZISHI_TYPES:
        config = spec.get('_query_settings', {})
        return _months(today)[:2 if config.get('previous_month_url') else 1]
    if spec.get('supports_month_query'):
        return list(dict.fromkeys(_months(today) + (_months(anchor_date) if anchor_date else [])))
    return [today[:7] if spec.get('cumulative_period') == 'month' else spec.get('cumulative_period', 'unknown')]


def _cumulative_is_historical(spec, period, today):
    # Only sources with a real historical-month entrance can reuse a closed
    # month's successful query. A current cumulative link is queried by run day.
    return bool((spec.get('supports_month_query') or spec.get('adapter_key') in collectors.ZISHI_TYPES)
                and period != today[:7])


def _cumulative_completed(conn, account, adapter, period, today, historical=False, *, collected_at=None, spec=None):
    query = """SELECT collected_at,collection_status FROM v2_revenue_collection_attempts WHERE account_id=?
        AND theater_id=? AND adapter_key=? AND period_end=?
        AND data_kind='account_cumulative' AND collection_status IN ('success','no_data')
        AND id NOT IN (SELECT attempt_id FROM v3_revenue_pending_queries)"""
    params = [account['id'],account['theater_id'],adapter,period]
    if historical:
        # A current-month snapshot is not its final closed-month value.
        query += ' AND substr(revenue_date,1,7)>?'
        params.append(period)
    else:
        query += ' AND revenue_date=?'
        params.append(today)
    row = conn.execute(query + ' ORDER BY collected_at DESC,rowid DESC LIMIT 1', params).fetchone()
    if not row:
        return False
    # A closed historical period can reuse its successful post-month query.
    # Current cumulative totals must be refreshed even after a successful run.
    moment = collected_at or state.clock()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=state.SHANGHAI)
    return (historical and row['collection_status'] == 'success') or not state.retry_due(row, moment, spec)


def _routine_rechecks(conn, account, spec, dates, moment):
    """Catch delayed dates in the legacy single-yesterday routine entry."""
    if dates[-1] != (moment.date()-timedelta(days=1)).isoformat():
        return []
    recent_start = (moment.date()-timedelta(days=state.recheck_days(spec))).isoformat()
    adapter = spec['adapter_key']
    known = conn.execute("""SELECT DISTINCT revenue_date FROM v2_revenue_collection_attempts
        WHERE account_id=? AND theater_id=? AND adapter_key=? AND revenue_date>=? AND revenue_date<?""",
        (account['id'],account['theater_id'],adapter,recent_start,dates[0]))
    return [r[0] for r in known if not state.completed(conn,account,adapter,r[0],collected_at=moment,spec=spec)]


def _is_empty(adapter, status, amount):
    # Qingning native and green-bubble identify normal empty responses.
    # It ends historical searching, but is never written as an invented zero.
    spec = collectors.definition(adapter) or {}
    explicit_empty = adapter == 'qingning' or spec.get('empty_result_is_boundary', False)
    return (status == 'success' and amount is not None and Decimal(str(amount)) == 0) or (explicit_empty and status == 'no_data')


def _fetch(account, adapter, day, spec, period):
    config = spec.get('_query_settings')
    if config and not config['enabled']:
        return 'failed', None, '采集器已在查单管理中停用，未向来源发起请求', []
    token = query_settings.ACTIVE.set(config)
    try:
        return _fetch_impl(account, adapter, day, spec, period)
    finally:
        query_settings.ACTIVE.reset(token)


def _fetch_impl(account, adapter, day, spec, period):
    channel = str(account['channel_id'] or '').strip()
    if not channel:
        return 'failed', None, '账号未填写视频号 ID', []
    if adapter in collectors.KUJIANG_TYPES:
        from server.kujiang_collector import fetch_day
        status, amount, message = fetch_day(channel, day, adapter)
        return status, amount, message, []
    if adapter in collectors.ZISHI_TYPES:
        from server.zishi_collector import fetch_month
        return fetch_month(channel, adapter, spec['_query_settings'], period, date.fromisoformat(day))
    if adapter == 'guyan_native':
        from server.guyan_collector import fetch_latest
        status, amount, message = fetch_latest(channel, spec['_query_settings'])
        return status, amount, message, []
    if adapter == 'pingyue':
        from server.pingyue_collector import fetch_day
        status, amount, message = fetch_day(channel, day, spec['_query_settings'])
        return status, amount, message, []
    if adapter == 'qingning':
        amount, details = fetch_qingning_day_details(channel, day)
        return ('no_data', None, '青柠正常返回：该日没有收益记录', []) if amount is None else ('success', amount, '', details)
    if spec.get('supports_month_query'):
        fetcher = MONTHLY_FETCHERS.get(adapter)
        if fetcher is None:
            raise RevenueError('该剧场尚未注册按月查询实现')
        status, amount, message = fetcher(channel, period)
    elif adapter == 'qingning_lpp':
        status, amount, message = fetch_qingning_lpp_day(channel, day)
    elif adapter == 'dinghao':
        status, amount, message = fetch_dinghao_day(channel, day)
    elif adapter == 'touch':
        status, amount, message = fetch_touch_latest(channel)
    elif adapter == 'huasheng':
        status, amount, message = fetch_huasheng_latest(channel)
    else:
        raise RevenueError('该剧场尚未注册查询实现')
    return status, amount, message, []


def collect_qingning(conn, start_date, end_date, account_ids=None, progress_callback=None, *,
                     skip_completed=False, save_details=False, initial_backfill=False,
                     max_initial_days=90, empty_streak_stop=7, collected_at=None, collection_run_id=None,
                              should_stop=None, report_cached=False):
    ids = [a['id'] for a in _accounts(conn,None,account_ids) if a['revenue_collector_id']=='qingning']
    return collect_supported_theaters(conn,start_date,end_date,None,ids,progress_callback,
        skip_completed=skip_completed,save_qingning_details=save_details,initial_backfill=initial_backfill,
        max_initial_days=max_initial_days,empty_streak_stop=empty_streak_stop,collected_at=collected_at,collection_run_id=collection_run_id,
        should_stop=should_stop,report_cached=report_cached)


def collect_supported_theaters(conn, start_date, end_date, theater_names=None, account_ids=None,
                              progress_callback=None, *, skip_completed=False,
                              save_qingning_details=False, initial_backfill=False,
                              max_initial_days=90, empty_streak_stop=7, collected_at=None, collection_run_id=None,
                              should_stop=None, report_cached=False):
    """One policy engine: day queries, resumable first history, cumulative deltas.

    collected_at is injectable for deterministic checks; production uses Shanghai time.
    Each source result, its cumulative baseline and both date read models commit together.
    """
    from server.collection_progress import checkpoint
    stopping = should_stop or (lambda: False)
    dates = _dates(start_date,end_date)
    moment = collected_at or state.clock()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=state.SHANGHAI)
    moment = moment.astimezone(state.SHANGHAI)
    now, today = moment.isoformat(timespec='seconds'), moment.date().isoformat()
    if end_date >= today:
        raise ValueError('按日收益最多采集到昨天')
    state.initialize(conn)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_revenue_account_periods'").fetchone():
        from server.analytics_data import initialize
        initialize(conn)
    request_id, items, histories = collection_run_id or uuid.uuid4().hex, [], []
    accounts = _accounts(conn,theater_names,account_ids)
    for account in accounts:
        checkpoint(stopping)
        spec = query_settings.effective_spec(conn, collectors.definition(account['revenue_collector_id']))
        if not spec or not spec["_query_settings"]["enabled"]:
            item = {'account_id':account['id'],'account_name':account['nickname'],
                    'theater_name':account['theater_name'],'date':end_date,'status':'failed',
                    'amount':None,'message':('采集器已在查单管理中停用，未发起查询' if spec else '账号收益采集器待配置，请在账号管理中选择'),'collected_at':now}
            items.append(item)
            if progress_callback:
                progress_callback(item)
            continue
        adapter, daily = spec['adapter_key'], spec['date_precision'] == 'day'
        plan = state.backfill_plan(conn,account,adapter,end_date) if daily and initial_backfill else None
        monthly_plan = state.backfill_plan(conn,account,adapter,today) if not daily and spec.get('supports_month_query') else None
        # A pending history always retains its original anchor; new days still run first.
        planned = [(d, '') for d in dates] if daily else [(today,p) for p in _cumulative_periods(spec,today,monthly_plan['anchor_date'] if monthly_plan else None)]
        if daily and initial_backfill and not plan:
            planned = [(d, '') for d in sorted(dates + _routine_rechecks(conn,account,spec,dates,moment))]
        if plan:
            anchor = date.fromisoformat(plan['anchor_date'])
            fresh = [(d,'') for d in dates if d > plan['anchor_date']]
            # Read count is bounded per invocation; cached history does not consume the budget.
            oldest = conn.execute("""SELECT MIN(revenue_date) FROM v2_revenue_collection_attempts
                WHERE account_id=? AND theater_id=? AND adapter_key=? AND revenue_date<=?""",
                (account['id'],account['theater_id'],adapter,plan['anchor_date'])).fetchone()[0]
            cached_span = max(0,(anchor-date.fromisoformat(oldest)).days+1) if oldest else 0
            planned = fresh + [((anchor-timedelta(days=i)).isoformat(),'') for i in range(cached_span+max(1,max_initial_days))]
        conn.commit()  # Persist the backfill cursor before cross-connection progress writes.
        empty_streak, history_reads, unresolved, boundary = 0, 0, False, ''
        for day, period in planned:
            checkpoint(stopping)
            in_history = plan is not None and day <= plan['anchor_date']
            cached = state.completed(conn,account,adapter,day,collected_at=moment,spec=spec) if daily and (skip_completed or plan) else None
            if cached:
                if report_cached and progress_callback:
                    progress_callback({'status':'skipped','account_id':account['id'],'date':day})
                if in_history:
                    empty_streak = empty_streak+1 if _is_empty(adapter,cached['collection_status'],cached['amount']) else 0
                    if empty_streak >= max(1,empty_streak_stop):
                        boundary = day
                        break
                continue
            if not daily and skip_completed and _cumulative_completed(conn,account,adapter,period,today,
                    historical=_cumulative_is_historical(spec,period,today), collected_at=moment, spec=spec):
                continue
            if in_history and history_reads >= max(1,max_initial_days):
                break
            if in_history:
                history_reads += 1
            if progress_callback:
                progress_callback({'status':'running','date':day,'account_id':account['id'],'theater_name':account['theater_name'],'account_name':account['nickname']})
            attempt_id = uuid.uuid4().hex
            amount, credited, details, metadata = None, None, [], {}
            if not conn.in_transaction:
                conn.execute('BEGIN')
            def record_attempt():
                conn.execute("""INSERT INTO v2_revenue_collection_attempts
                    (id,request_id,account_id,theater_id,adapter_key,revenue_date,collection_status,
                     amount,error_message,collected_at,data_kind,period_type,period_end)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (attempt_id,request_id,account['id'],account['theater_id'],adapter,day,'no_data' if status == 'pending' else status,
                     format(amount,'f') if isinstance(amount,Decimal) and amount.is_finite() else None,
                     message,now,'account_daily_total' if daily else 'account_cumulative',
                     'date_range' if daily else ('monthly_cumulative' if re.fullmatch(r'\d{4}-\d{2}', period) else 'cumulative_unknown'),day if daily else period))

            conn.execute('SAVEPOINT revenue_unit')
            try:
                status, amount, message, details = _fetch(account,adapter,day,spec,period)
                if status == 'no_data' and re.search(r'尚未更新|未出账|尚未出账|正在结算|尚未结算|稍后再查', message or ''):
                    status = 'pending'
                if status not in ('success','no_data','failed','pending'):
                    status = 'failed'
                if status == 'success':
                    if amount is None:
                        raise RevenueError('来源成功但缺少金额，未入账')
                    amount = Decimal(str(amount))
                    if not amount.is_finite() or amount < 0:
                        raise RevenueError('来源金额无效，未入账')
                    amount = amount.quantize(MONEY,rounding=ROUND_HALF_UP)
                    credited = amount
                    metadata = {'method':'direct_daily','raw_amount':format(amount,'f')}
                    if not daily:
                        delta, credited = state.cumulative_delta(conn,account,adapter,period,day,amount,attempt_id,now,spec.get("_baseline_periods", ()))
                        metadata = {'method':'cumulative_delta','source_period':period,
                                    'raw_amount':format(amount,'f'),'new_amount':format(delta,'f'),
                                    'attribution':'collection_date'}
                if adapter in collectors.ZISHI_TYPES:
                    prior = conn.execute("""SELECT raw_result_json FROM v3_revenue_account_periods
                        WHERE account_id=? AND theater_id=? AND period_label=? AND period_type='day'
                        AND source_kind='theater_collector'""", (account['id'],account['theater_id'],day)).fetchone()
                    prior_metadata = json.loads(prior[0]) if prior else {}
                    earlier = prior_metadata.get('source_observations', []) if prior_metadata.get('adapter_key') == adapter else []
                    observations = {(x.get('source_url'), x['kind'], x['period']): x for x in [*earlier, *details]}
                    metadata['source_observations'] = list(observations.values())
                    metadata['daily_use'] = 'cross_check_only'
                metadata.update({"query_config_revision": spec["_query_settings"]["revision"], "query_source_url": spec["_query_settings"]["source_url"]})
                # Insert evidence before dependent rows, also with foreign-key enforcement enabled.
                record_attempt()
                if status == 'pending':
                    conn.execute('INSERT INTO v3_revenue_pending_queries(attempt_id) VALUES(?)', (attempt_id,))
                if status == 'success':
                    state.write_day(conn,account,adapter,day,credited,attempt_id,request_id,now,metadata)
                    if adapter == 'qingning' and save_qingning_details:
                        _save_qingning_details(conn,account,day,details,attempt_id,now)
                conn.execute('RELEASE SAVEPOINT revenue_unit')
            except Exception as exc:
                conn.execute('ROLLBACK TO SAVEPOINT revenue_unit')
                conn.execute('RELEASE SAVEPOINT revenue_unit')
                from server.pingyue_collector import VerificationRequired
                if isinstance(exc, VerificationRequired):
                    conn.commit()
                    item = {'account_id': account['id'], 'account_name': account['nickname'],
                            'theater_name': account['theater_name'], 'date': day, 'status': 'verification_required',
                            'amount': None, 'message': str(exc), 'verification_id': exc.challenge_id, 'collected_at': now}
                    items.append(item)
                    if progress_callback:
                        progress_callback(item)
                    unresolved = True
                    break
                status, message, credited = 'failed', str(exc), None
                record_attempt()
            conn.commit()
            item = {'id':attempt_id,'account_id':account['id'],'account_name':account['nickname'],
                    'theater_name':account['theater_name'],'date':day,'status':status,
                    'amount':format(credited if daily else delta,'f') if credited is not None else None,
                    'raw_amount':format(amount,'f') if isinstance(amount,Decimal) and amount.is_finite() else None,
                    'source_period':period,'message':message,'collected_at':now}
            items.append(item)
            item['empty_streak'] = empty_streak+1 if in_history and _is_empty(adapter,status,amount) else 0
            if progress_callback:
                progress_callback(item)
            if not str(account['channel_id'] or '').strip():
                break
            if in_history:
                unresolved = unresolved or status in ('failed','pending')
                empty_streak = empty_streak+1 if _is_empty(adapter,status,amount) else 0
                if empty_streak >= max(1,empty_streak_stop):
                    boundary = day
                    break
        if monthly_plan:
            complete = all(_cumulative_completed(conn,account,adapter,period,today,
                           historical=_cumulative_is_historical(spec,period,today), collected_at=moment, spec=spec)
                           for period in _cumulative_periods(spec,today,monthly_plan['anchor_date']))
            conn.execute("""UPDATE v3_revenue_backfills SET complete=?
                WHERE account_id=? AND theater_id=? AND adapter_key=?""",
                (int(complete),account['id'],account['theater_id'],adapter))
            conn.commit()
            histories.append({'account_id':account['id'],'complete':complete,
                              'message':'首次月份补采完成' if complete else '首次月份补采未完成，下次继续原月份'})
        if plan:
            complete = bool(boundary and not unresolved)
            conn.execute("""UPDATE v3_revenue_backfills SET boundary_date=?,complete=?
                WHERE account_id=? AND theater_id=? AND adapter_key=?""",
                (boundary,int(complete),account['id'],account['theater_id'],adapter))
            conn.commit()
            histories.append({'account_id':account['id'],'complete':complete,'boundary_date':boundary,
                              'message':'首次补采完成' if complete else '首次补采未完成，下次继续缓存位置与失败日期'})
    return {'request_id':request_id,'start_date':start_date,'end_date':end_date,
            'total_accounts':len(accounts),'items':items,'backfills':histories}


def estimate_collection_units(conn,start_date,end_date,theater_names=None,account_ids=None,*,
                              skip_completed=False,initial_backfill=False,max_initial_days=90,
                              collected_at=None):
    """Upper bound during first history; final progress uses actual completed units."""
    dates = _dates(start_date,end_date)
    moment = collected_at or state.clock()
    today = moment.date().isoformat() if moment.tzinfo is None else moment.astimezone(state.SHANGHAI).date().isoformat()
    if end_date >= today:
        raise ValueError('按日收益最多采集到昨天')
    state.initialize(conn)
    total = 0
    for account in _accounts(conn,theater_names,account_ids):
        spec = query_settings.effective_spec(conn, collectors.definition(account['revenue_collector_id']))
        if not spec or not spec["_query_settings"]["enabled"]:
            total += 1
            continue
        adapter = spec['adapter_key']
        if spec['date_precision'] == 'day':
            existing = conn.execute("""SELECT complete,anchor_date FROM v3_revenue_backfills
                WHERE account_id=? AND theater_id=? AND adapter_key=?""",
                (account['id'],account['theater_id'],adapter)).fetchone()
            if initial_backfill and (not existing or not existing['complete']):
                total += max(1,max_initial_days)
                total += sum(1 for d in dates if existing and d > existing['anchor_date'] and
                             not (skip_completed and state.completed(conn,account,adapter,d,collected_at=moment,spec=spec)))
            else:
                account_dates = dates + (_routine_rechecks(conn,account,spec,dates,moment) if initial_backfill else [])
                total += sum(1 for d in account_dates if not (skip_completed and state.completed(conn,account,adapter,d,collected_at=moment,spec=spec)))
        else:
            pending = conn.execute("SELECT anchor_date FROM v3_revenue_backfills WHERE account_id=? AND theater_id=? AND adapter_key=? AND complete=0",
                                   (account['id'],account['theater_id'],adapter)).fetchone()
            total += sum(1 for period in _cumulative_periods(spec,today,pending['anchor_date'] if pending else None) if not (skip_completed and
                _cumulative_completed(conn,account,adapter,period,today,
                    historical=_cumulative_is_historical(spec,period,today), collected_at=moment, spec=spec)))
    return total


def revenue_source_data(conn: sqlite3.Connection) -> dict[str, object]:
    rows = conn.execute("""SELECT r.id, r.revenue_date, r.account_id, a.nickname account_nickname, r.theater_id, t.name theater_name, r.amount, r.quality, r.updated_at
        FROM v2_daily_revenues r JOIN accounts a ON a.id=r.account_id JOIN theaters t ON t.id=r.theater_id ORDER BY r.revenue_date""").fetchall()
    accounts = conn.execute("""SELECT a.id, a.nickname, a.status, a.theater_id, t.name theater_name
        FROM accounts a JOIN theaters t ON t.id=a.theater_id
        """).fetchall()
    theaters = conn.execute("SELECT id, name, status FROM theaters").fetchall()
    return {"rows": [dict(row) for row in rows], "accounts": [dict(row) for row in accounts], "theaters": [dict(row) for row in theaters]}


def revenue_daily_account_summary(conn: sqlite3.Connection, revenue_date: str) -> dict[str, object]:
    """Small read model for scheduling: one real collection result per account/day."""
    try:
        day = date.fromisoformat(revenue_date).isoformat()
    except ValueError as exc:
        raise ValueError("收益日期格式不正确") from exc
    has_pending = conn.execute("SELECT 1 FROM sqlite_master WHERE name='v3_revenue_pending_queries'").fetchone()
    final_filter = ' AND x.id NOT IN (SELECT attempt_id FROM v3_revenue_pending_queries)' if has_pending else ''
    status_sql = "CASE WHEN x.id IN (SELECT attempt_id FROM v3_revenue_pending_queries) THEN 'pending' ELSE x.collection_status END" if has_pending else 'x.collection_status'
    rows = conn.execute(
        f"""SELECT a.id AS account_id, r.amount,
                  COALESCE(
                    -- A normal empty response is a completed collection.
                    -- Keep it even if a later retry failed: the date was
                    -- still read successfully and must not become missing.
                    (SELECT x.collection_status FROM v2_revenue_collection_attempts x
                     WHERE x.account_id=a.id AND x.revenue_date=?
                       AND x.collection_status IN ('success', 'no_data') {final_filter}
                     ORDER BY x.collected_at DESC, x.rowid DESC LIMIT 1),
                    (SELECT {status_sql} FROM v2_revenue_collection_attempts x
                     WHERE x.account_id=a.id AND x.revenue_date=?
                     ORDER BY x.collected_at DESC, x.rowid DESC LIMIT 1),
                    CASE WHEN r.id IS NULL THEN 'uncollected' ELSE 'success' END
                  ) AS collection_status
           FROM accounts a
           LEFT JOIN v2_daily_revenues r ON r.account_id=a.id AND r.revenue_date=?
           WHERE a.status<>'注销' OR r.id IS NOT NULL OR EXISTS (SELECT 1 FROM v2_revenue_collection_attempts x WHERE x.account_id=a.id AND x.revenue_date=?)
           ORDER BY a.id""",
        (day, day, day, day),
    ).fetchall()
    return {"revenue_date": day, "items": [dict(row) for row in rows]}


def revenue_video_details(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    account_id: str = "",
    limit: int = 12000,
) -> dict[str, object]:
    """Return only the requested Qingning video-detail window.

    The stored table is the canonical daily fact table.  This read model keeps
    its grain intact (one date/account/video row) so the UI can aggregate a
    selected period without loading the entire historical archive.
    """
    try:
        start = date.fromisoformat(start_date).isoformat()
        end = date.fromisoformat(end_date).isoformat()
    except ValueError as exc:
        raise ValueError("收益明细日期格式不正确") from exc
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    if (date.fromisoformat(end) - date.fromisoformat(start)).days > 90:
        raise ValueError("单次最多读取 90 天视频明细，请缩小日期范围")
    capped_limit = max(1, min(int(limit), 20000))
    where = ["v.revenue_date>=?", "v.revenue_date<=?", "t.name LIKE '%青柠%'"]
    params: list[object] = [start, end]
    if account_id:
        where.append("v.account_id=?")
        params.append(account_id)
    # Request one additional row so the caller can show an honest truncation
    # state rather than silently treating a partial result as complete.
    params.append(capped_limit + 1)
    rows = conn.execute(
        f"""SELECT v.id, v.revenue_date, v.account_id, a.nickname account_name,
                   v.theater_id, t.name theater_name, v.source_video_id,
                   v.source_drama_name, v.video_views, v.drama_views,
                   v.gross_revenue, v.source_rank, v.matched_drama_id,
                   COALESCE(d.current_name, '') matched_drama_name,
                   v.match_status, v.updated_at,
                   (SELECT MIN(observed.revenue_date) FROM v2_revenue_video_details observed
                     WHERE observed.account_id=v.account_id AND observed.source_video_id=v.source_video_id) first_observed_date,
                   link.production_task_id linked_task_id, link.production_video_task_id linked_video_task_id,
                   link.source_material_id linked_material_id, link.note linked_note,
                   COALESCE(linked_material.original_name, linked_material.file_name, '') linked_material_name,
                   linked_task.actual_release_time linked_actual_release_time,
                   linked_task.release_province linked_release_province, linked_task.release_city linked_release_city,
                   linked_task.release_district linked_release_district, linked_task.release_detail_address linked_release_detail_address
            FROM v2_revenue_video_details v
            JOIN accounts a ON a.id=v.account_id
            JOIN theaters t ON t.id=v.theater_id
            LEFT JOIN dramas d ON d.id=v.matched_drama_id
            LEFT JOIN v2_revenue_video_links link ON link.account_id=v.account_id AND link.source_video_id=v.source_video_id
            LEFT JOIN production_tasks linked_task ON linked_task.id=link.production_task_id
            LEFT JOIN production_files linked_material ON linked_material.id=link.source_material_id
            WHERE {' AND '.join(where)}
            ORDER BY v.revenue_date DESC, v.gross_revenue DESC, v.source_rank ASC
            LIMIT ?""",
        params,
    ).fetchall()
    rows = [dict(row) for row in rows]
    truncated = len(rows) > capped_limit
    # A saved material link is optional.  For address reporting we can still
    # infer the registered production task from first observation + account +
    # drama; the exact material remains a separate human confirmation.
    task_rows = conn.execute("""SELECT id, account_name, drama_name, planned_publish_at,
        actual_release_time, release_province, release_city, release_district,
        release_detail_address FROM production_tasks""").fetchall()
    inferred: dict[tuple[str, str, str], sqlite3.Row] = {}
    for task in task_rows:
        for task_date in (str(task["planned_publish_at"] or "")[:10], str(task["actual_release_time"] or "")[:10]):
            if task_date:
                key = (str(task["account_name"]), str(task["drama_name"]), task_date)
                current = inferred.get(key)
                if current is None or (task["actual_release_time"] and not current["actual_release_time"]):
                    inferred[key] = task
    for row in rows:
        if row["linked_task_id"]:
            continue
        key = (str(row["account_name"]), str(row["matched_drama_name"] or row["source_drama_name"]), str(row["first_observed_date"] or "")[:10])
        task = inferred.get(key)
        if task:
            row["inferred_task_id"] = task["id"]
            row["inferred_actual_release_time"] = task["actual_release_time"]
            row["inferred_release_province"] = task["release_province"]
            row["inferred_release_city"] = task["release_city"]
            row["inferred_release_district"] = task["release_district"]
            row["inferred_release_detail_address"] = task["release_detail_address"]
    return {
        "items": [dict(row) for row in rows[:capped_limit]],
        "start_date": start,
        "end_date": end,
        "truncated": truncated,
        "limit": capped_limit,
    }


def revenue_video_candidates(conn: sqlite3.Connection, account_id: str, video_id: str) -> dict[str, object]:
    """Find candidate source materials using first observation + account + drama.

    It is deliberately a recommendation, not a completed association.  The
    caller must select one candidate and explicitly confirm it.
    """
    if not account_id or not video_id:
        raise ValueError("缺少账号或平台视频 ID")
    detail = conn.execute("""SELECT v.account_id, a.nickname account_name, v.source_video_id,
        v.source_drama_name, COALESCE(d.current_name, v.source_drama_name) drama_name,
        (SELECT MIN(observed.revenue_date) FROM v2_revenue_video_details observed
          WHERE observed.account_id=v.account_id AND observed.source_video_id=v.source_video_id) first_observed_date
        FROM v2_revenue_video_details v JOIN accounts a ON a.id=v.account_id
        LEFT JOIN dramas d ON d.id=v.matched_drama_id
        WHERE v.account_id=? AND v.source_video_id=? LIMIT 1""", (account_id, video_id)).fetchone()
    if not detail:
        raise ValueError("未找到该平台视频明细")
    # A task may have either planned or registered actual release on the same
    # date.  Both are candidates; the UI keeps the final choice human-owned.
    tasks = conn.execute("""SELECT id, account_name, drama_name, planned_publish_at, actual_release_time
        FROM production_tasks
        WHERE account_name=? AND drama_name=?
          AND (date(planned_publish_at)=? OR date(NULLIF(actual_release_time,''))=?)
        ORDER BY CASE WHEN date(NULLIF(actual_release_time,''))=? THEN 0 ELSE 1 END, planned_publish_at""",
        (detail["account_name"], detail["drama_name"], detail["first_observed_date"], detail["first_observed_date"], detail["first_observed_date"])).fetchall()
    candidates: list[dict[str, object]] = []
    for task in tasks:
        rows = conn.execute("""SELECT vt.id production_video_task_id, vt.source_material_id,
            pf.file_name, pf.original_name, pf.duration_seconds, pf.thumbnail_path, pf.file_path
            FROM production_video_tasks vt JOIN production_files pf ON pf.id=vt.source_material_id
            WHERE vt.task_id=? ORDER BY pf.sequence_no, pf.file_name""", (task["id"],)).fetchall()
        for row in rows:
            item = dict(row)
            item["production_task_id"] = task["id"]
            item["planned_publish_at"] = task["planned_publish_at"]
            item["actual_release_time"] = task["actual_release_time"]
            item["thumbnail_url"] = f"/api/v2/production-files/{row['source_material_id']}/thumbnail" if row["thumbnail_path"] else ""
            item["media_url"] = f"/api/v2/production-files/{row['source_material_id']}/media"
            candidates.append(item)
    return {"platform_video": dict(detail), "candidates": candidates}


def confirm_revenue_video_link(conn: sqlite3.Connection, payload: dict[str, object]) -> dict[str, object]:
    account_id = str(payload.get("account_id") or "").strip()
    video_id = str(payload.get("video_id") or "").strip()
    task_id = str(payload.get("production_task_id") or "").strip()
    video_task_id = str(payload.get("production_video_task_id") or "").strip()
    material_id = str(payload.get("source_material_id") or "").strip()
    note = str(payload.get("note") or "").strip()
    if not all((account_id, video_id, task_id, video_task_id, material_id)):
        raise ValueError("缺少人工确认关联所需的信息")
    valid = conn.execute("""SELECT 1 FROM production_video_tasks vt
        JOIN production_files pf ON pf.id=vt.source_material_id
        WHERE vt.id=? AND vt.task_id=? AND vt.source_material_id=?""", (video_task_id, task_id, material_id)).fetchone()
    if not valid:
        raise ValueError("所选素材不属于该候选生产任务")
    exists = conn.execute("SELECT 1 FROM v2_revenue_video_details WHERE account_id=? AND source_video_id=?", (account_id, video_id)).fetchone()
    if not exists:
        raise ValueError("未找到该平台视频明细")
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("""INSERT INTO v2_revenue_video_links
        (id, account_id, source_video_id, production_task_id, production_video_task_id, source_material_id, note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id, source_video_id) DO UPDATE SET production_task_id=excluded.production_task_id,
          production_video_task_id=excluded.production_video_task_id, source_material_id=excluded.source_material_id,
          note=excluded.note, updated_at=excluded.updated_at""",
        (uuid.uuid4().hex, account_id, video_id, task_id, video_task_id, material_id, note, now, now))
    conn.commit()
    return {"linked": True, "account_id": account_id, "video_id": video_id, "production_task_id": task_id, "source_material_id": material_id}


def collection_logs(conn: sqlite3.Connection, limit: int = 2000) -> dict[str, object]:
    rows = conn.execute("""SELECT x.id, a.nickname account_name, t.name theater_name, x.revenue_date, x.collection_status, x.amount, x.error_message, x.collected_at
        FROM v2_revenue_collection_attempts x JOIN accounts a ON a.id=x.account_id JOIN theaters t ON t.id=x.theater_id
        ORDER BY x.collected_at DESC, x.rowid DESC LIMIT ?""", (max(1, min(limit, 5000)),)).fetchall()
    pending = state.pending_attempts(conn)
    items = [dict(row) for row in rows]
    for item in items:
        if item['id'] in pending:
            item['collection_status'] = 'pending'
    return {"items": items}
