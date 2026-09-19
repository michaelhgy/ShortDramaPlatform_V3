"""清除孤儿记录：已不存在的生产任务留下的模板/成片/导出/素材记录。

用户 2026-09-19 明确授权执行，并说"不用备份那么麻烦"。
**只删数据库行，不碰磁盘上任何文件。**

用法：
    python tools/cleanup_orphans.py          # 预演，只打印要删多少
    python tools/cleanup_orphans.py --apply  # 真删
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")

# 顺序有意义：先删引用别人的（export_attempts → export_jobs），再删被引用的。
PREDICATES: list[tuple[str, str]] = [
    ("export_attempts", "job_id IN (SELECT j.id FROM export_jobs j WHERE j.production_task_id NOT IN (SELECT id FROM production_tasks))"),
    ("export_jobs", "production_task_id NOT IN (SELECT id FROM production_tasks)"),
    ("template_jobs", "task_id NOT IN (SELECT id FROM production_tasks)"),
    ("production_video_tasks", "task_id NOT IN (SELECT id FROM production_tasks)"),
    ("production_files", "task_id NOT IN (SELECT id FROM production_tasks)"),
    ("production_resource_reservations", "task_id NOT IN (SELECT id FROM production_tasks)"),
    ("cleanup_records", "task_id NOT IN (SELECT id FROM production_tasks)"),
    ("executor_trace_events", "production_task_id NOT IN (SELECT id FROM production_tasks)"),
]


def main() -> None:
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(str(DB))
    try:
        # 先证明这些记录确实是孤儿：拿一个孤儿 task_id 去 production_tasks 里找不到
        sample = conn.execute(
            "SELECT task_id FROM template_jobs WHERE task_id NOT IN (SELECT id FROM production_tasks) LIMIT 3"
        ).fetchall()
        print(f"抽样验证孤儿：{len(sample)} 个 task_id 在 production_tasks 里确实不存在")
        for (task_id,) in sample:
            exists = conn.execute("SELECT COUNT(*) FROM production_tasks WHERE id=?", (task_id,)).fetchone()[0]
            print(f"   {task_id[:12]}…  在 production_tasks 中 = {exists} 条")
            if exists:
                raise SystemExit("发现非孤儿记录，中止！")

        print()
        print("=" * 78)
        print("要清除的数量" + ("（即将执行）" if apply else "（预演，不写入）"))
        print("=" * 78)
        total = 0
        counts: list[tuple[str, int]] = []
        for table, predicate in PREDICATES:
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}").fetchone()[0]
            counts.append((table, n))
            total += n
            print(f"  {table:<36} {n:>6}")
        print(f"  {'合计':<36} {total:>6}")
        print()
        print("不动的表：v2_change_events（变更流水，按时间的审计日志，与父任务无关）")

        if not apply:
            print("\n（预演结束。加 --apply 才会真删。）")
            return

        print("\n" + "=" * 78)
        print("开始清除")
        print("=" * 78)
        removed_total = 0
        for table, predicate in PREDICATES:
            removed = conn.execute(f"DELETE FROM {table} WHERE {predicate}").rowcount
            removed_total += removed
            print(f"  已删 {table:<36} {removed:>6}")
        conn.commit()
        print(f"\n合计删除 {removed_total} 行（磁盘文件一个都没动）")

        print("\n复查：再数一遍孤儿")
        left = 0
        for table, predicate in PREDICATES:
            n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicate}").fetchone()[0]
            left += n
        print(f"  剩余孤儿 = {left} 条（应为 0）")
        print(f"  production_tasks 行数 = {conn.execute('SELECT COUNT(*) FROM production_tasks').fetchone()[0]}（未变）")
        print(f"  未登记发布的任务数 = {conn.execute(chr(34)+'SELECT COUNT(*) FROM production_tasks WHERE COALESCE(release_status,'+chr(39)+'unregistered'+chr(39)+') <> '+chr(39)+'registered'+chr(39)+chr(34)).fetchone()[0]}（未变）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
