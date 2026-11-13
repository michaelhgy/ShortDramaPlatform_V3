"""Export a compact, source-labelled dashboard design package for Gemini AI Studio."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "界面设计输入"
SOURCE = "simulation_ui"
LATEST = "2026-10-29"
RANGE_START = "2026-10-23"


def rows(conn: sqlite3.Connection, sql: str, params=()):
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(sql, params)]


def total(items, key):
    return round(sum(float(item.get(key) or 0) for item in items), 2)


def export_json() -> dict:
    conn = sqlite3.connect(DB)
    accounts = rows(conn, """
        SELECT account_id, uid, account_name, group_name, platform, login_status,
               fans_total, snapshot_date, source_kind, data_state, freshness_state
        FROM v3_video_accounts
        WHERE source_kind=?
        ORDER BY account_id
        LIMIT 8
    """, (SOURCE,))
    account_ids = [item["account_id"] for item in accounts]
    marks = ",".join("?" for _ in account_ids)
    daily = rows(conn, f"""
        SELECT account_id, stat_date, view, fans_total, fans_add, fans_net,
               fans_reduce, like_count, favorite_count, comment_count, forward_count,
               source_kind, data_state, freshness_state
        FROM v3_video_account_daily
        WHERE source_kind=? AND account_id IN ({marks}) AND stat_date BETWEEN ? AND ?
        ORDER BY stat_date, account_id
    """, (SOURCE, *account_ids, RANGE_START, LATEST))
    all_daily = rows(conn, """
        SELECT stat_date, view, fans_add, fans_net, like_count, favorite_count,
               comment_count, forward_count
        FROM v3_video_account_daily
        WHERE source_kind=?
    """, (SOURCE,))
    posts = rows(conn, f"""
        SELECT post_id, account_id, account_name, title, description, post_time,
               post_type, publish_status, view, like_count, comment_count,
               forward_count, love_count, fans_add, full_view, view_time,
               snapshot_date, source_kind, data_state, freshness_state
        FROM v3_video_posts
        WHERE source_kind=? AND account_id IN ({marks})
        ORDER BY view DESC
        LIMIT 20
    """, (SOURCE, *account_ids))
    post_ids = [item["post_id"] for item in posts]
    post_marks = ",".join("?" for _ in post_ids) or "''"
    post_daily = rows(conn, f"""
        SELECT post_id, account_id, stat_date, view, like_count, comment_count,
               forward_count, favorite_count, fans_add, metric_grain,
               source_kind, data_state, freshness_state
        FROM v3_video_post_daily
        WHERE source_kind=? AND post_id IN ({post_marks}) AND stat_date BETWEEN ? AND ?
        ORDER BY stat_date, post_id
    """, (SOURCE, *post_ids, RANGE_START, LATEST))
    diagnostics = rows(conn, f"""
        SELECT account_id, account_name, verified, abnormal, video_status,
               heat_status, abnormal_post_count, last_verify_time, snapshot_date,
               source_kind, data_state, freshness_state
        FROM v3_video_account_diagnostics
        WHERE source_kind=? AND account_id IN ({marks})
    """, (SOURCE, *account_ids))
    punishments = rows(conn, f"""
        SELECT uid, post_id_or_export_id, title, publish_time, punish_state,
               snapshot_date, source_kind, data_state, freshness_state
        FROM v3_video_post_punishments
        WHERE source_kind=? AND uid IN ({','.join('?' for _ in account_ids)})
        LIMIT 12
    """, (SOURCE, *[item["uid"] for item in accounts]))
    sources = rows(conn, """
        SELECT theater_id, adapter_key, query_mode, date_precision,
               supports_detail, requires_account_id, requires_date,
               adapter_status, last_checked_at, notes
        FROM v3_revenue_sources
        WHERE adapter_key LIKE 'simulation_%'
        ORDER BY adapter_key
    """)
    revenue_periods = rows(conn, """
        SELECT account_id, theater_id, period_label, period_start, period_end,
               period_type, date_precision, amount, currency, data_state,
               freshness_state, settlement_state, include_in_analysis,
               source_kind, collected_at
        FROM v3_revenue_account_periods
        WHERE source_kind=? AND (
            (period_type='day' AND period_start BETWEEN ? AND ?) OR
            (period_type='month_cumulative' AND period_label IN ('2026-09','2026-10'))
        )
        ORDER BY period_start, theater_id, account_id
    """, (SOURCE, RANGE_START, LATEST))
    current_month_revenue = rows(conn, """
        SELECT theater_id, account_id, period_type, period_start, period_label,
               amount, include_in_analysis, settlement_state, date_precision
        FROM v3_revenue_account_periods
        WHERE source_kind=? AND include_in_analysis=1 AND (
            (period_type='day' AND period_start LIKE '2026-10%') OR
            (period_type='month_cumulative' AND period_label='2026-10')
        )
    """, (SOURCE,))
    revenue_details = rows(conn, """
        SELECT account_id, theater_id, detail_date, source_video_id,
               source_drama_name, video_views, drama_views, gross_revenue,
               source_rank, source_kind, data_state, freshness_state
        FROM v3_revenue_details
        WHERE source_kind=?
        ORDER BY detail_date DESC, account_id
        LIMIT 40
    """, (SOURCE,))

    daily_by_date = defaultdict(list)
    for item in daily:
        daily_by_date[item["stat_date"]].append(item)
    trend = []
    for current in range(7):
        day = (date.fromisoformat(RANGE_START) + timedelta(days=current)).isoformat()
        day_rows = daily_by_date[day]
        trend.append({
            "date": day,
            "account_count": len(day_rows),
            "views": total(day_rows, "view"),
            "fans_add": total(day_rows, "fans_add"),
            "fans_net": total(day_rows, "fans_net"),
            "interaction": round(sum(total(day_rows, key) for key in ("like_count", "favorite_count", "comment_count", "forward_count")), 2),
            "source_kind": SOURCE,
        })
    latest_rows = daily_by_date[LATEST]
    latest_previous = daily_by_date[(date.fromisoformat(LATEST) - timedelta(days=1)).isoformat()]
    by_account = defaultdict(list)
    for item in daily:
        by_account[item["account_id"]].append(item)
    account_cards = []
    for account in accounts:
        current = by_account[account["account_id"]]
        latest = next((item for item in current if item["stat_date"] == LATEST), current[-1] if current else {})
        account_cards.append({
            "account_id": account["account_id"], "uid": account["uid"],
            "account_name": account["account_name"], "group_name": account["group_name"],
            "latest": latest, "range_views": total(current, "view"),
            "range_fans_add": total(current, "fans_add"), "range_fans_net": total(current, "fans_net"),
            "range_interaction": round(sum(total(current, key) for key in ("like_count", "favorite_count", "comment_count", "forward_count")), 2),
            "record_days": len(current), "expected_days": 7,
            "record_status": "complete" if len(current) == 7 else "partial",
        })
    revenue_by_theater = defaultdict(float)
    for item in revenue_periods:
        if item["include_in_analysis"] and item["period_type"] == "day":
            revenue_by_theater[item["theater_id"]] += float(item["amount"] or 0)
    current_revenue_by_theater = defaultdict(float)
    for item in current_month_revenue:
        current_revenue_by_theater[item["theater_id"]] += float(item["amount"] or 0)
    yesterday_revenue = sum(float(item["amount"] or 0) for item in current_month_revenue if item["period_type"] == "day" and item["period_start"] == LATEST)
    payload = {
        "package": {"name": "短剧推广运营驾驶舱 AI Studio 输入包", "version": 1, "generated_at": "2026-10-30", "data_is_demo": True, "source_kind": SOURCE, "latest_date": LATEST, "range": {"start": RANGE_START, "end": LATEST}},
        "business_context": {"account_model": "账号会频繁新增和退出，但首页不以账号生命周期为主线；生命周期只作为状态字段和筛选维度。", "traffic_source": "小V猫从视频号官方后台获取后保存到V3的快照。", "revenue_source": "各剧场独立查询；不同剧场返回粒度不同。", "settlement_rule": "已结算月份不进入当前可计收益。", "missing_rule": "缺失、查询失败、明确为0必须分开显示。"},
        "dashboard_summary": {"latest_day": {"views": total(latest_rows, "view"), "fans_add": total(latest_rows, "fans_add"), "fans_net": total(latest_rows, "fans_net"), "interaction": round(sum(total(latest_rows, key) for key in ("like_count", "favorite_count", "comment_count", "forward_count")), 2), "record_accounts": len(latest_rows), "revenue": round(yesterday_revenue, 2)}, "previous_day": {"views": total(latest_previous, "view")}, "range_views": total(daily, "view"), "month_views": total([item for item in all_daily if str(item["stat_date"]).startswith("2026-10")], "view"), "historical_views": total(all_daily, "view"), "range_fans_add": total(daily, "fans_add"), "range_interaction": round(sum(total(daily, key) for key in ("like_count", "favorite_count", "comment_count", "forward_count")), 2), "revenue_by_theater": dict(revenue_by_theater), "current_month_revenue_by_theater": dict(current_revenue_by_theater), "current_month_revenue": round(sum(current_revenue_by_theater.values()), 2)},
        "account_cards": account_cards,
        "account_daily_trend": trend,
        "posts": [{**item, "placement_account": item.pop("account_name"), "title": None, "description": None} for item in posts],
        "post_daily": post_daily,
        "diagnostics": diagnostics,
        "punishments": punishments,
        "revenue_sources": sources,
        "revenue_periods": revenue_periods,
        "revenue_details": revenue_details,
        "demo_scenarios": [
            {"scenario": "record_zero", "meaning": "账号有明确日记录且指标为0，界面显示为0。"},
            {"scenario": "missing_record", "meaning": "账号当天没有返回日记录，界面显示缺失，不显示为0。"},
            {"scenario": "monthly_cumulative_revenue", "meaning": "剧场只返回月累计金额，不能伪造每日收益曲线。"},
            {"scenario": "detail_revenue", "meaning": "剧场返回日期、视频、剧名、播放和金额，可进入收益明细。"},
            {"scenario": "post_without_title", "meaning": "作品数据没有标题字段，界面只显示投放账号和作品记录ID。"},
        ],
        "field_dictionary": {
            "account_daily": {"view": "账号日播放", "fans_total": "当日粉丝存量", "fans_add": "当日新增粉丝", "fans_net": "当日净增粉", "fans_reduce": "当日掉粉", "like_count": "点赞", "favorite_count": "收藏", "comment_count": "评论", "forward_count": "转发"},
            "post": {"post_id": "平台作品记录ID，用于区分记录", "placement_account": "小V猫返回的投放账号，例如某某短剧", "title": "当前真实返回为空，不在界面中伪造作品标题", "view": "作品快照播放", "full_view": "完播率", "view_time": "观看时长", "fans_add": "作品带来的新增粉丝", "publish_status": "发布状态"},
            "revenue": {"amount": "剧场返回金额", "period_type": "day 或 month_cumulative", "date_precision": "day 或 month", "supports_detail": "是否有作品/剧名等明细", "include_in_analysis": "是否进入当前分析", "settlement_state": "未结算或已结算"},
            "data_state": {"record": "有返回记录", "zero": "有记录且数值为0", "missing": "没有返回记录", "failed": "查询失败"},
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "运营驾驶舱演示数据.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    return payload


def write_requirements(payload: dict) -> None:
    text = f'''# 短剧推广运营驾驶舱｜Gemini AI Studio 界面需求输入

## 1. 生成目标

请生成一个短剧推广运营系统的高质量数据驾驶舱界面。参考附件中的布局层级和信息密度：浅色背景、圆角卡片、图表为主、明细为辅、顶部有日期和筛选、底部有排行榜。不要复制营销系统的文案和字段，不要使用左侧导航；系统已有顶部导航。

这是运营人员每天查看的首页，优先级为：

1. 昨日整体表现：流量、涨粉、互动、异常和数据覆盖。
2. 收益：昨日收益、本月未结算流水、环比、剧场来源和数据粒度。
3. 账号与作品：每个投放账号最高播放记录、全账号播放 Top 10、高播放低互动、长期没有表现的账号。

## 2. 数据约束

- 所有演示数据来自 `运营驾驶舱演示数据.json`，其中 `data_is_demo=true`，必须在界面上显示“演示数据”。
- 视频号流量只能使用 `account_daily` 和 `post` 数据；来源显示为“小V猫 / 视频号官方后台快照”。
- 收益只能使用 `revenue_periods`、`revenue_details` 和 `revenue_sources`；来源显示为“剧场独立查询”。
- 不要把账号播放和作品播放相加。
- 不要把月累计收益画成每日收益。
- `missing`、`failed`、`zero`、`record` 显示成不同状态。
- 小V猫作品数据当前没有可靠的作品标题；不要生成“第几集｜文案”或任何标题。作品记录用 `post_id` 标识，账号字段用 `placement_account`，展示为“投放账号”。
- 已结算月份的 `include_in_analysis=0` 不计入当前收益。
- 账号可能频繁新增和退出，但首页不围绕账号生命周期设计；只在账号状态、筛选和详情中显示记录天数。

## 3. 首页布局

采用一张完整驾驶舱画布，页面从上到下排列：

### 顶部区域

- 标题：短剧推广运营驾驶舱
- 副标题：昨日运营表现
- 日期选择：昨日、近7日、近30日
- 数据截至日期
- 小V猫快照更新时间
- 收益数据更新时间
- 读取已保存数据按钮

### 第一行：昨日核心指标

显示真实汇总值：

- 昨日总播放
- 昨日播放环比
- 昨日新增粉丝
- 昨日净增粉
- 昨日互动总量
- 历史总播放
- 本月账号播放总计
- 本月未结算流水

互动总量由点赞、收藏、评论、转发组成，但卡片下方要显示四项拆分，不能只显示一个无法解释的数字。历史总播放和本月账号播放都只来自账号日数据；收益金额不和播放量合并。

### 第二行：整体趋势和收益

左侧大图：账号整体表现趋势。支持切换播放、新增粉丝、净增粉、互动量；横轴为日期。

右侧卡片：收益概况。显示本月可计总额、昨日收益、环比和剧场来源。按日收益只画日数据；月累计收益显示为独立来源卡。

### 第三行：账号结构和数据状态

左侧：账号流量分布图，按账号播放占比展示，并能点击进入账号详情。

右侧：数据覆盖状态，显示有记录账号、明确为0账号、缺失账号、失败账号、收益待查询账号。用状态标签区分，不要把缺失账号显示为0。

### 第四行：投放账号与作品记录表现

左侧：每个投放账号最高播放记录。每个账号一条，显示投放账号、作品记录 ID、播放、完播率、互动和数据天数。

右侧：全账号播放 Top 10。显示排名、投放账号、作品记录 ID、播放、完播率、互动率。

再增加一个小型“高播放低互动”提示区，用来发现播放高但内容质量指标偏弱的作品。

### 底部：分析入口

- 查看完整账号分析
- 查看完整作品分析
- 查看收益分析
- 查看数据采集状态

## 4. 二级页面

首页点击卡片进入二级页面或右侧详情抽屉：

- 账号详情：账号趋势、粉丝、互动、作品列表、最高作品、异常状态、数据覆盖。
- 作品详情：每日播放、点赞、收藏、评论、转发、完播率、观看时长、处罚状态。
- 收益详情：剧场、查询周期、账号、金额、日期精度、明细字段和原始返回状态。
- 数据状态详情：采集批次、最后获取时间、record/zero/missing/failed、失败原因。

## 5. 视觉要求

- 参考附件的浅色紫白风格和网格布局。
- 使用白色卡片、淡紫/淡蓝背景、深紫标题、紫色和青绿色图表。
- 图表面积应大于普通文字和表格面积。
- 首页不使用深色大横幅。
- 首页不放长段说明文字；字段解释放到 tooltip 或详情页。
- 表格放在页面下方或二级页面，不让表格成为第一视觉中心。
- 需要有 hover、点击下钻、日期切换和指标切换。
- 页面看起来像专业运营驾驶舱，避免通用后台表格风格。

## 6. 交互结果

用户应该能按以下路径使用：

首页看到昨日播放下降 → 点击趋势中的日期 → 看到当日账号排名 → 点击账号 → 看到账号近7日变化 → 点击作品 → 看到作品每日表现和互动质量。

首页看到收益变化 → 点击剧场 → 看到该剧场的数据精度和返回字段 → 对支持明细的剧场查看账号/日期/作品明细。

## 7. 数据包说明

本需求配套数据文件：`运营驾驶舱演示数据.json`。

- 演示账号：{{len(payload['account_cards'])}} 个
- 账号日记录：{{len(payload['account_daily_trend'])}} 个趋势日，账号明细位于 `account_cards`
- 作品：{{len(payload['posts'])}} 条
- 作品日记录：{{len(payload['post_daily'])}} 条
- 收益周期：{{len(payload['revenue_periods'])}} 条
- 收益明细样例：{{len(payload['revenue_details'])}} 条

请直接使用 JSON 中的数值生成界面，不要自行创造与字段含义冲突的指标。
'''
    # Resolve the few counts before writing; braces above are intentional template placeholders.
    text = text.replace("{{len(payload['account_cards'])}}", str(len(payload['account_cards'])))
    text = text.replace("{{len(payload['account_daily_trend'])}}", str(len(payload['account_daily_trend'])))
    text = text.replace("{{len(payload['posts'])}}", str(len(payload['posts'])))
    text = text.replace("{{len(payload['post_daily'])}}", str(len(payload['post_daily'])))
    text = text.replace("{{len(payload['revenue_periods'])}}", str(len(payload['revenue_periods'])))
    text = text.replace("{{len(payload['revenue_details'])}}", str(len(payload['revenue_details'])))
    (OUT / "运营驾驶舱-Gemini-AI-Studio-需求.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    payload = export_json()
    write_requirements(payload)
    print(f"wrote {OUT / '运营驾驶舱演示数据.json'}")
    print(f"wrote {OUT / '运营驾驶舱-Gemini-AI-Studio-需求.md'}")
