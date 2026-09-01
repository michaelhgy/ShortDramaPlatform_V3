"""V2-only Qingning revenue collection and read models.

This module deliberately owns its own schema and HTTP parsing.  It does not
import V1 or share V1 records, so V2 remains independently runnable.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.request import build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

SOURCE_URL = "https://vd.xingvan.com/duangg.html"
MONEY = Decimal("0.01")


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
    cleaned = re.sub(r"[^0-9.-]", "", value or "")
    if not cleaned: return Decimal("0")
    try: return Decimal(cleaned)
    except InvalidOperation as exc: raise RevenueError(f"无法解析收益数值：{value}") from exc


def _decode(raw: bytes, charset: str | None) -> str:
    for encoding in (charset, "utf-8", "gb18030"):
        if not encoding: continue
        try: text = raw.decode(encoding)
        except (LookupError, UnicodeDecodeError): continue
        if any(marker in text for marker in ("剧目", "收益", "暂时", "记录")): return text
    return raw.decode("utf-8", errors="replace")


def _fetch_page(channel_id: str, revenue_date: str, page: int) -> tuple[list[QingningRow], int, int | None, Decimal | None]:
    body = urlencode({"startgdate": revenue_date, "endgdate": revenue_date, "spfindid": channel_id, "spvideoid": "", "p": page}).encode("ascii")
    request = Request(SOURCE_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "ShortDramaOpsV2/1.0"})
    with urlopen(request, timeout=40) as response:
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
    with urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_dinghao_day(channel_id: str, revenue_date: str) -> tuple[str, Decimal | None, str]:
    try:
        data = _post_json("https://zyu.wozhangwan.com/api/api/order/getVideoAdIncome", {"income_date_start": revenue_date, "income_date_end": f"{revenue_date} 23:59:59", "advertiser_id": channel_id, "channel_name": "", "drama_name": ""})
        if data.get("status_code") != 1: return "failed", None, str(data.get("msg") or "顶好来源查询失败")
        raw = (data.get("data") or {}).get("amount") if isinstance(data.get("data"), dict) else None
        if raw is None: return "failed", None, "顶好来源缺少收益字段"
        amount = Decimal(str(raw).replace(",", "").strip())
        return ("indeterminate", None, "顶好返回 0.00，无法确认是真实零收益还是未匹配账号") if amount == 0 else ("success", amount, "")
    except Exception as exc: return "failed", None, str(exc)


def fetch_touch_latest(channel_id: str) -> tuple[str, Decimal | None, str]:
    try:
        page_url = "https://c3andggd.yichafen.com/qz/167SsX4Q2t"; headers = {"User-Agent": "Mozilla/5.0", "Referer": page_url}
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        with opener.open(Request(page_url, headers=headers), timeout=40) as response: html = response.read().decode("utf-8", errors="replace")
        match = re.search(r"sqcode[\"']?\s*[:=]\s*[\"']([^\"']+)", html) or re.search(r"/verifycondition/sqcode/([^/]+)/", html)
        if not match: raise RevenueError("触摸页面缺少 sqcode")
        endpoint = f"https://c3andggd.yichafen.com/public/verifycondition/sqcode/{match.group(1)}/from_device/mobile.html"
        with opener.open(Request(endpoint, data=urlencode({"s_shipinhaoid": channel_id}).encode(), headers={**headers, "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"}), timeout=40) as response: result = json.loads(response.read().decode("utf-8"))
        if result.get("status") != 1: return ("no_data", None, str(result.get("info") or "没有数据")) if result.get("errNo") == 100 else ("failed", None, str(result.get("info") or "触摸来源查询失败"))
        with opener.open(Request("https://c3andggd.yichafen.com/public/queryresult/from_device/mobile.html", headers=headers), timeout=40) as response: text = re.sub(r"<[^>]+>", " ", response.read().decode("utf-8", errors="replace"))
        amount = re.search(r"广告收益[^0-9]{0,50}([0-9]+(?:\.[0-9]+)?)", text)
        if not amount: raise RevenueError("触摸结果缺少广告收益字段")
        return "success", Decimal(amount.group(1)), ""
    except Exception as exc: return "failed", None, str(exc)


def fetch_huasheng_latest(channel_id: str) -> tuple[str, Decimal | None, str]:
    """Public Huasheng source query; it returns an account-period total only."""
    try:
        page_url, token = "https://scnrzu35lckk.feishu.cn/share/base/query/shrcnCXYADPz9wc4apC1pZ6Fvvb", "shrcnCXYADPz9wc4apC1pZ6Fvvb"
        opener = build_opener(HTTPCookieProcessor(CookieJar())); headers = {"User-Agent": "Mozilla/5.0", "Referer": page_url, "Content-Type": "application/json"}
        with opener.open(Request(page_url, headers=headers), timeout=40): pass
        root = page_url.split("/share/")[0] + "/space/api/bitable/form/external/"
        def request(endpoint: str, payload: dict[str, object]) -> dict[str, object]:
            with opener.open(Request(root + endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers), timeout=40) as response: data = json.loads(response.read().decode("utf-8"))
            if data.get("code") != 0: raise RevenueError(str(data.get("msg") or "花生来源查询失败"))
            return data.get("data") or {}
        request("get_share", {"shareToken": token})
        condition = {"fieldId": "fld3P2QILX", "fieldType": 1, "operator": "contains", "value": [channel_id], "conditionId": f"con{uuid.uuid4().hex[:8]}"}
        data = request("list_records", {"filter": json.dumps({"conditions": [condition], "conjunction": "and"}, separators=(",", ":")), "offset": 0, "shareToken": token})
        if not int(data.get("total") or 0): return "no_data", None, "花生正常返回：未找到该账号记录"
        rows = list((data.get("recordMap") or {}).values()) + list(data.get("records") or data.get("items") or [])
        total = Decimal("0")
        for row in rows:
            raw = (row.get("fields") or row).get("fld4Za6Nvm")
            if isinstance(raw, dict): raw = raw.get("value")
            if isinstance(raw, list) and raw and isinstance(raw[0], dict): raw = raw[0].get("text") or raw[0].get("value")
            if raw is None: raise RevenueError("花生来源缺少收益字段")
            total += Decimal(str(raw).replace(",", "").strip())
        return "success", total, ""
    except Exception as exc: return "failed", None, str(exc)


def _dates(start_date: str, end_date: str) -> list[str]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start: raise ValueError("结束日期不能早于开始日期")
    if (end - start).days > 90: raise ValueError("一次补采最多 90 天，请分段进行")
    return [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]


def collect_qingning(conn: sqlite3.Connection, start_date: str, end_date: str, account_ids: list[str] | None = None, progress_callback=None) -> dict[str, object]:
    request_id, now = uuid.uuid4().hex, datetime.now().isoformat(timespec="seconds")
    dates = _dates(start_date, end_date)
    accounts = conn.execute("""SELECT a.id, a.nickname, a.channel_id, a.theater_id FROM accounts a
        JOIN theaters t ON t.id=a.theater_id WHERE t.name LIKE '%青柠%' AND a.status!='停用' ORDER BY a.nickname""").fetchall()
    if account_ids:
        accounts = [account for account in accounts if str(account["id"]) in set(account_ids)]
    items: list[dict[str, object]] = []
    for account in accounts:
        channel_id = str(account["channel_id"] or "").strip()
        for revenue_date in dates:
            if progress_callback: progress_callback({"status": "running", "theater_name": "青柠剧场", "account_name": account["nickname"]})
            status, amount, message, details = "success", None, "", []
            if not channel_id:
                status, message = "failed", "账号未填写青柠视频号 ID"
            else:
                try: amount, details = fetch_qingning_day_details(channel_id, revenue_date)
                except Exception as exc: status, message = "failed", str(exc)
                else:
                    if amount is None: status, message = "no_data", "青柠正常返回：该日没有收益记录"
            attempt_id = uuid.uuid4().hex
            conn.execute("""INSERT INTO v2_revenue_collection_attempts
                (id, request_id, account_id, theater_id, adapter_key, revenue_date, collection_status, amount, error_message, collected_at, data_kind)
                VALUES (?, ?, ?, ?, 'qingning', ?, ?, ?, ?, ?, 'video_detail')""",
                (attempt_id, request_id, account["id"], account["theater_id"], revenue_date, status,
                 format(amount, 'f') if amount is not None else None, message, now))
            if status == "success" and amount is not None:
                conn.execute("""INSERT INTO v2_daily_revenues (id, account_id, theater_id, revenue_date, amount, quality, source_attempt_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'direct', ?, ?, ?)
                    ON CONFLICT(account_id, revenue_date) DO UPDATE SET amount=excluded.amount, quality='direct', source_attempt_id=excluded.source_attempt_id, updated_at=excluded.updated_at""",
                    (uuid.uuid4().hex, account["id"], account["theater_id"], revenue_date, format(amount, 'f'), attempt_id, now, now))
                for detail in details:
                    drama = conn.execute("SELECT id FROM dramas WHERE theater_id=? AND current_name=?", (account["theater_id"], detail.drama_name)).fetchone()
                    conn.execute("""INSERT INTO v2_revenue_video_details
                        (id, attempt_id, account_id, theater_id, revenue_date, source_video_id, source_drama_name, video_views, drama_views, gross_revenue, source_rank, matched_drama_id, match_status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(revenue_date, account_id, source_video_id) DO UPDATE SET attempt_id=excluded.attempt_id, source_drama_name=excluded.source_drama_name, video_views=excluded.video_views, drama_views=excluded.drama_views, gross_revenue=excluded.gross_revenue, source_rank=excluded.source_rank, matched_drama_id=excluded.matched_drama_id, match_status=excluded.match_status, updated_at=excluded.updated_at""",
                        (uuid.uuid4().hex, attempt_id, account["id"], account["theater_id"], revenue_date, detail.video_id, detail.drama_name, detail.video_views, detail.drama_views, format(detail.gross_revenue, 'f'), detail.rank, drama["id"] if drama else None, "matched" if drama else "unmatched", now, now))
            items.append({"id": attempt_id, "account_id": account["id"], "account_name": account["nickname"], "theater_name": "青柠剧场", "date": revenue_date, "status": status, "amount": format(amount, 'f') if amount is not None else None, "message": message, "collected_at": now})
            if progress_callback: progress_callback(items[-1])
    conn.commit()
    return {"request_id": request_id, "start_date": start_date, "end_date": end_date, "total_accounts": len(accounts), "items": items}


def collect_supported_theaters(conn: sqlite3.Connection, start_date: str, end_date: str, theater_names: list[str] | None = None, account_ids: list[str] | None = None, progress_callback=None) -> dict[str, object]:
    """Collect every V2-supported theater without importing V1 code or data."""
    supported = {"青柠剧场": "qingning", "顶好剧场": "dinghao", "触摸剧场": "touch", "花生剧场": "huasheng"}
    selected = set(theater_names or supported)
    qingning = collect_qingning(conn, start_date, end_date, account_ids, progress_callback) if "青柠剧场" in selected else {"items": [], "total_accounts": 0}
    now, request_id, items = datetime.now().isoformat(timespec="seconds"), uuid.uuid4().hex, list(qingning["items"])
    rows = conn.execute("""SELECT a.id, a.nickname, a.channel_id, a.theater_id, t.name theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id
        WHERE a.status!='停用' AND t.name IN ('顶好剧场','触摸剧场','花生剧场') ORDER BY a.nickname""").fetchall()
    for account in rows:
        if account["theater_name"] not in selected or (account_ids and str(account["id"]) not in set(account_ids)): continue
        kind = supported[str(account["theater_name"])]
        dates = _dates(start_date, end_date) if kind == "dinghao" else [end_date]
        for revenue_date in dates:
            if progress_callback: progress_callback({"status": "running", "theater_name": account["theater_name"], "account_name": account["nickname"]})
            if not str(account["channel_id"] or "").strip(): status, amount, message = "failed", None, "账号未填写视频号 ID"
            elif kind == "dinghao": status, amount, message = fetch_dinghao_day(str(account["channel_id"]), revenue_date)
            elif kind == "touch": status, amount, message = fetch_touch_latest(str(account["channel_id"]))
            else: status, amount, message = fetch_huasheng_latest(str(account["channel_id"]))
            if status == "indeterminate": status = "failed"  # V2 has no ambiguous-zero success state.
            attempt_id = uuid.uuid4().hex
            conn.execute("""INSERT INTO v2_revenue_collection_attempts (id, request_id, account_id, theater_id, adapter_key, revenue_date, collection_status, amount, error_message, collected_at, data_kind, period_type, period_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (attempt_id, request_id, account["id"], account["theater_id"], kind, revenue_date, status, format(amount, 'f') if amount is not None else None, message, now, "account_daily_total" if kind == "dinghao" else "account_cumulative", "date_range" if kind == "dinghao" else "monthly_cumulative", revenue_date if kind == "dinghao" else ""))
            if kind == "dinghao" and status == "success" and amount is not None:
                conn.execute("""INSERT INTO v2_daily_revenues (id, account_id, theater_id, revenue_date, amount, quality, source_attempt_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'direct', ?, ?, ?)
                    ON CONFLICT(account_id, revenue_date) DO UPDATE SET amount=excluded.amount, source_attempt_id=excluded.source_attempt_id, updated_at=excluded.updated_at""", (uuid.uuid4().hex, account["id"], account["theater_id"], revenue_date, format(amount, 'f'), attempt_id, now, now))
            items.append({"id": attempt_id, "account_id": account["id"], "account_name": account["nickname"], "theater_name": account["theater_name"], "date": revenue_date, "status": status, "amount": format(amount, 'f') if amount is not None else None, "message": message, "collected_at": now})
            if progress_callback: progress_callback(items[-1])
    conn.commit()
    return {"request_id": request_id, "start_date": start_date, "end_date": end_date, "total_accounts": len(items), "items": items}


def estimate_collection_units(conn: sqlite3.Connection, start_date: str, end_date: str, theater_names: list[str] | None = None, account_ids: list[str] | None = None) -> int:
    """Return the exact number of account-date reads that this collection run will perform."""
    selected = set(theater_names or {"青柠剧场", "顶好剧场", "触摸剧场", "花生剧场"})
    account_filter = set(account_ids or [])
    rows = conn.execute("""SELECT a.id, t.name theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id
        WHERE a.status!='停用' AND t.name IN ('青柠剧场','顶好剧场','触摸剧场','花生剧场')""").fetchall()
    date_count = len(_dates(start_date, end_date))
    total = 0
    for row in rows:
        if row["theater_name"] not in selected or (account_filter and str(row["id"]) not in account_filter):
            continue
        total += date_count if row["theater_name"] in {"青柠剧场", "顶好剧场"} else 1
    return total


def revenue_source_data(conn: sqlite3.Connection) -> dict[str, object]:
    rows = conn.execute("""SELECT r.id, r.revenue_date, r.account_id, a.nickname account_nickname, r.theater_id, t.name theater_name, r.amount, r.quality, r.updated_at
        FROM v2_daily_revenues r JOIN accounts a ON a.id=r.account_id JOIN theaters t ON t.id=r.theater_id ORDER BY r.revenue_date""").fetchall()
    accounts = conn.execute("""SELECT a.id, a.nickname, a.status, a.theater_id, t.name theater_name
        FROM accounts a JOIN theaters t ON t.id=a.theater_id
        WHERE t.name IN ('青柠剧场','顶好剧场','触摸剧场','花生剧场')""").fetchall()
    theaters = conn.execute("SELECT id, name, status FROM theaters WHERE name IN ('青柠剧场','顶好剧场','触摸剧场','花生剧场')").fetchall()
    return {"rows": [dict(row) for row in rows], "accounts": [dict(row) for row in accounts], "theaters": [dict(row) for row in theaters]}


def revenue_daily_account_summary(conn: sqlite3.Connection, revenue_date: str) -> dict[str, object]:
    """Small read model for scheduling: one real collection result per account/day."""
    try:
        day = date.fromisoformat(revenue_date).isoformat()
    except ValueError as exc:
        raise ValueError("收益日期格式不正确") from exc
    rows = conn.execute(
        """SELECT a.id AS account_id, r.amount,
                  COALESCE(
                    -- A normal empty response is a completed collection.
                    -- Keep it even if a later retry failed: the date was
                    -- still read successfully and must not become missing.
                    (SELECT x.collection_status FROM v2_revenue_collection_attempts x
                     WHERE x.account_id=a.id AND x.revenue_date=?
                       AND x.collection_status IN ('success', 'no_data')
                     ORDER BY x.collected_at DESC, x.id DESC LIMIT 1),
                    (SELECT x.collection_status FROM v2_revenue_collection_attempts x
                     WHERE x.account_id=a.id AND x.revenue_date=?
                     ORDER BY x.collected_at DESC, x.id DESC LIMIT 1),
                    CASE WHEN r.id IS NULL THEN 'uncollected' ELSE 'success' END
                  ) AS collection_status
           FROM accounts a
           LEFT JOIN v2_daily_revenues r ON r.account_id=a.id AND r.revenue_date=?
           WHERE a.status!='停用'
           ORDER BY a.id""",
        (day, day, day),
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
        ORDER BY x.collected_at DESC, x.id DESC LIMIT ?""", (max(1, min(limit, 5000)),)).fetchall()
    return {"items": [dict(row) for row in rows]}
