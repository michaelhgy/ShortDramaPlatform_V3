"""Export 2-3 raw examples for every V3 analytics data type.

The export intentionally preserves normalized columns and decoded payload_json.
It is an evidence handoff, not a dashboard specification.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "界面设计输入"


def sample(conn: sqlite3.Connection, table: str, where: str = "", params=(), limit: int = 3):
    sql = f"SELECT * FROM {table} {where} LIMIT {limit}"
    result = []
    for row in conn.execute(sql, params):
        item = dict(row)
        raw = item.get("payload_json") or item.get("raw_result_json")
        if isinstance(raw, str) and raw:
            try:
                item["raw_payload"] = json.loads(raw)
            except json.JSONDecodeError:
                item["raw_payload"] = raw
        result.append(item)
    return result


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    video_tables = {
        "account_snapshot": ("v3_video_accounts", "WHERE source_kind='xiao_v_cache' ORDER BY fetched_at DESC"),
        "account_daily": ("v3_video_account_daily", "WHERE source_kind='xiao_v_cache' ORDER BY stat_date DESC, uid"),
        "post_snapshot": ("v3_video_posts", "WHERE source_kind='xiao_v_cache' ORDER BY fetched_at DESC"),
        "post_daily": ("v3_video_post_daily", "WHERE source_kind='xiao_v_cache' ORDER BY stat_date DESC, post_id"),
        "account_diagnostic": ("v3_video_account_diagnostics", "WHERE source_kind='xiao_v_cache' ORDER BY fetched_at DESC"),
        "post_punishment": ("v3_video_post_punishments", "WHERE source_kind='xiao_v_cache' ORDER BY fetched_at DESC"),
    }
    data_types = {}
    for name, (table, where) in video_tables.items():
        data_types[name] = {
            "table": table,
            "source": "xiao_v_cache",
            "source_note": "已保存的小V猫返回快照，页面读取不会再次访问官方后台。",
            "samples": sample(conn, table, where),
        }
    data_types["collection_run"] = {
        "table": "v3_analytics_collection_runs",
        "source": "V3 collection log",
        "source_note": "采集批次和整体状态，不代表平台业务字段。",
        "samples": sample(conn, "v3_analytics_collection_runs", "ORDER BY created_at DESC"),
    }
    data_types["collection_item"] = {
        "table": "v3_analytics_collection_items",
        "source": "xiao_v_cache",
        "source_note": "逐账号/逐数据类型的采集状态。",
        "samples": sample(conn, "v3_analytics_collection_items", "WHERE source_kind='xiao_v_cache' ORDER BY fetched_at DESC"),
    }
    data_types["revenue_source"] = {
        "table": "v3_revenue_sources",
        "source": "V3 source inventory",
        "source_note": "剧场查询来源登记。不是一次查询结果。",
        "samples": sample(conn, "v3_revenue_sources", "ORDER BY adapter_key"),
    }
    data_types["revenue_period_demo"] = {
        "table": "v3_revenue_account_periods",
        "source": "simulation_ui",
        "source_note": "当前数据库中用于界面演示的收益周期；真实剧场适配结果需要后续采集确认。",
        "samples": sample(conn, "v3_revenue_account_periods", "WHERE source_kind='simulation_ui' ORDER BY period_start DESC"),
    }
    data_types["revenue_detail_demo"] = {
        "table": "v3_revenue_details",
        "source": "simulation_ui",
        "source_note": "当前数据库中用于界面演示的收益明细样例；字段结构按青柠详细返回形态模拟。",
        "samples": sample(conn, "v3_revenue_details", "WHERE source_kind='simulation_ui' ORDER BY detail_date DESC"),
    }
    data_types["revenue_period_legacy"] = {
        "table": "v3_revenue_account_periods",
        "source": "legacy_v2",
        "source_note": "历史收益迁移样例，状态为旧口径/未核验，不可直接作为当前收益。",
        "samples": sample(conn, "v3_revenue_account_periods", "WHERE source_kind='legacy_v2' ORDER BY period_start DESC"),
    }
    data_types["revenue_detail_legacy"] = {
        "table": "v3_revenue_details",
        "source": "legacy_v2",
        "source_note": "历史收益明细迁移样例，状态为旧口径/未核验。",
        "samples": sample(conn, "v3_revenue_details", "WHERE source_kind='legacy_v2' ORDER BY detail_date DESC"),
    }
    payload = {
        "package": {
            "name": "V3 分析底座原始数据样例",
            "created_at": "2026-10-31",
            "purpose": "给GPT/Gemini理解实际数据类型和字段，不作为界面方案。",
            "sample_rule": "每个类型最多3条；视频数据优先使用xiao_v_cache实际保存快照；收益演示数据单独标注。",
        },
        "important_facts": [
            "视频作品返回中的title当前为空/null，不能生成作品标题、集数标题或剧名标题。",
            "视频作品中的account字段是投放账号，展示时应称为投放账号。",
            "post_id是平台作品记录ID，只适合作为记录标识。",
            "账号日数据和作品日数据是不同粒度，不能直接相加。",
            "缺失记录、明确为0、查询失败要保持不同状态。",
            "收益不同剧场的日期精度和明细能力不同，样例中演示收益已单独标注。",
        ],
        "data_types": data_types,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "V3分析底座-原始数据样例.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    print(target)


if __name__ == "__main__":
    main()
