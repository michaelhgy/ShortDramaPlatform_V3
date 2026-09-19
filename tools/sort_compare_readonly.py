"""只读对比：任务中心「状态分层排序」 vs 生产中心「未完成+发布时间排序」。

给用户做决策用的**临时分析脚本**（等级 1/3：读真实数据库），
只读打开数据库，不写任何数据。用完可删。

口径说明（来自 server/v2_file_service.py 的规范状态机）：
- 视频 = 该成片任务最近一次导出尝试 status='completed'（才会显示「视频·已导出」）
- 草稿 = production_video_tasks.status='draft_ready'（草稿已写出）
- 素材 = production_files 里 file_type='original_material' AND status='available'
- 异常 = 最近一次导出尝试 failed/timeout，或成片任务 generation_failed/generation_timeout
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")

BASE_SQL = """
SELECT t.id, t.account_name, t.drama_name, t.planned_publish_at, t.created_at, t.release_status,
  (SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id
     AND v.status NOT IN ('cancelled','cancellation_requested','invalidated')) AS video_total,
  (SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id AND v.status='draft_ready') AS draft_ready,
  (SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id
     AND (v.status IN ('generation_failed','generation_timeout')
          OR (SELECT a.status FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id
              WHERE j.subject_type='final' AND j.subject_id=v.id
              ORDER BY a.attempt_no DESC LIMIT 1) IN ('failed','timeout'))) AS bad,
  (SELECT COUNT(*) FROM production_files f WHERE f.task_id=t.id
     AND f.file_type='original_material' AND f.status='available') AS materials
FROM production_tasks t
WHERE COALESCE(t.cleanup_status,'active')='active'
  AND (EXISTS (SELECT 1 FROM production_video_tasks v WHERE v.task_id=t.id)
    OR EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=t.id))
ORDER BY CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at
"""


def exported_count(conn: sqlite3.Connection, task_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM production_video_tasks v "
        "WHERE v.task_id=? AND v.status NOT IN ('cancelled','cancellation_requested','invalidated') "
        "AND (SELECT a.status FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id "
        "     WHERE j.subject_type='final' AND j.subject_id=v.id "
        "     ORDER BY a.attempt_no DESC LIMIT 1)='completed'",
        (task_id,),
    ).fetchone()
    return int(row[0] or 0)


def counts(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, int]:
    return {
        "material": int(row["materials"] or 0),
        "draft": int(row["draft_ready"] or 0),
        "video": exported_count(conn, str(row["id"])),
        "bad": int(row["bad"] or 0),
    }


def line(conn: sqlite3.Connection, index: int, row: sqlite3.Row) -> str:
    stat = counts(conn, row)
    return (
        f"{index:>3}. {row['account_name']} × 《{row['drama_name']}》"
        f" | 计划发布 {(row['planned_publish_at'] or '未设置').replace('T', ' ')}"
        f" | 视频 {stat['video']} / 草稿 {stat['draft']} / 素材 {stat['material']} / 异常 {stat['bad']}"
    )


def main() -> None:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(BASE_SQL).fetchall()
        print(f"合计 {len(rows)} 个账号×剧集生产任务（未清理、且有真实生产记录）\n")

        print("=" * 104)
        print("【口径 A = 现在任务中心卡片列表】状态分层（执行中→超时→失败→排队→已完成）→ 优先级 → 素材序号")
        print("=" * 104)
        for index, row in enumerate(rows[:30], start=1):
            print(line(conn, index, row))

        print()
        print("=" * 104)
        print("【口径 B = 生产中心左侧列表】未登记发布优先 → 计划发布时间早优先")
        print("=" * 104)
        ordered = sorted(
            rows,
            key=lambda row: (
                0 if str(row["release_status"] or "unregistered") != "registered" else 1,
                row["planned_publish_at"] or "9999-12-31",
                row["created_at"],
            ),
        )
        for index, row in enumerate(ordered[:30], start=1):
            print(line(conn, index, row))

        now_order = {str(row["id"]): index for index, row in enumerate(rows, start=1)}
        prod_order = {str(row["id"]): index for index, row in enumerate(ordered, start=1)}
        moved = sorted(
            ((now_order[key], prod_order[key], key) for key in now_order if now_order[key] != prod_order[key]),
            key=lambda item: -abs(item[0] - item[1]),
        )
        if moved:
            print()
            print("=" * 104)
            print("【两种排序不一致的任务】（现在第几条 → 生产中心口径第几条）")
            print("=" * 104)
            by_id = {str(row["id"]): row for row in rows}
            for now_index, prod_index, key in moved:
                row = by_id[key]
                stat = counts(conn, row)
                print(
                    f"现在第 {now_index:>2} → 生产中心第 {prod_index:>2}"
                    f" | {row['account_name']} × 《{row['drama_name']}》"
                    f" | 计划发布 {(row['planned_publish_at'] or '未设置').replace('T', ' ')}"
                    f" | 视频 {stat['video']} / 草稿 {stat['draft']} / 素材 {stat['material']}"
                )
        else:
            print("\n两种排序结果完全一致（当前数据下没有差异）。")

        # 顺带核对：任务中心卡片列表的状态分层到底有没有真的生效
        print()
        print("=" * 104)
        print("【关键事实核对】")
        print("=" * 104)
        print(f"· 计划发布时间在未来的任务数：{sum(1 for r in rows if str(r['planned_publish_at'] or '') > '2026-09-19T23:59')}")
        print(f"· 已登记发布的任务数：{sum(1 for r in rows if str(r['release_status'] or '') == 'registered')}")
        print(f"· 素材为 0 的任务数：{sum(1 for r in rows if int(r['materials'] or 0) == 0)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
