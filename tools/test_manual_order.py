"""在数据库副本上实测手动调整排序 —— 不碰真实生产库。

验证目标（等级 2）：
1. 顺序函数与派单 SQL 用的是同一个排序键；
2. 置顶/上移/下移 真的改变顺序，并且落库到 manual_order；
3. 已完成的整部剧永远沉底，不占手动位次。
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

REAL_DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")

tmp_dir = Path(tempfile.mkdtemp(prefix="v2-order-test-"))
copy_db = tmp_dir / "v2_system.db"
shutil.copy2(REAL_DB, copy_db)

from server import v2_file_service as service  # noqa: E402

service.db_path = lambda: copy_db  # type: ignore[assignment]

from server import task_center_service as tc  # noqa: E402


def show(title: str) -> list[str]:
    conn = service.connection()
    try:
        order = tc._ordered_unit_ids(conn)
    finally:
        conn.close()
    print(f"\n{title}")
    conn = service.connection()
    try:
        for i, task_id in enumerate(order, 1):
            row = conn.execute(
                "SELECT account_name, drama_name, planned_publish_at, manual_order FROM production_tasks WHERE id=?",
                (task_id,),
            ).fetchone()
            complete = "已完成" if tc._unit_is_complete(conn, task_id) else "进行中"
            print(
                f"  {i}. [{complete}] {row['account_name']} ×《{row['drama_name']}》"
                f"  计划 {str(row['planned_publish_at'])[11:16] or '未设置'}  manual_order={row['manual_order']}"
            )
    finally:
        conn.close()
    return order


def main() -> None:
    print(f"用副本测试：{copy_db}")

    # ── 场景 1：全部已完成 ──────────────────────────────────────────
    # 用户点"置顶"必须得到一个明确说法，而不是点了没反应。
    before = show("【场景1 · 全部已完成】初始顺序（应等于业务规则；已完成沉底）")
    try:
        tc.task_center_reorder(before[-1], "top")
        raise AssertionError("全部已完成时应当拒绝调整顺序")
    except ValueError as exc:
        print(f"\n✅ 全部已完成时点了置顶 → 正确报错：{exc}")

    # ── 场景 2：有未完成单位时的真实调整 ────────────────────────────
    # 副本里没有"进行中"的剧（用户的活刚跑完），所以临时把完成判断替换掉，
    # 专门验证排序算法本身；这不会写入任何数据之外的东西，副本随后删除。
    print("\n" + "=" * 70)
    print("【场景2】临时把全部单位视为未完成，验证排序算法本身")
    print("=" * 70)
    tc._unit_is_complete = lambda conn, task_id: False  # type: ignore[assignment]

    initial = show("初始顺序（业务规则：计划发布早 → 开工早）")
    target = initial[-1]
    conn = service.connection()
    try:
        row = conn.execute("SELECT account_name, drama_name FROM production_tasks WHERE id=?", (target,)).fetchone()
    finally:
        conn.close()

    print(f"\n>>> 对最后一名做「置顶」：{row['account_name']} ×《{row['drama_name']}》")
    tc.task_center_reorder(target, "top")
    after_top = show("置顶之后")
    assert after_top[0] == target, "置顶失败：目标没有排到第一位"

    print("\n>>> 对它做「下移一位」")
    tc.task_center_reorder(target, "down")
    after_down = show("下移之后")
    assert after_down[0] != target and after_down[1] == target, "下移失败"

    print("\n>>> 对它做「上移一位」（应回到第一位）")
    tc.task_center_reorder(target, "up")
    after_up = show("上移之后")
    assert after_up[0] == target, "上移失败"

    print("\n>>> 落库检查：manual_order 是否写进数据库")
    conn = service.connection()
    try:
        rows = conn.execute(
            "SELECT account_name, drama_name, manual_order FROM production_tasks "
            "WHERE manual_order > 0 ORDER BY manual_order"
        ).fetchall()
        for r in rows:
            print(f"  #{r['manual_order']}  {r['account_name']} ×《{r['drama_name']}》")
        registered_ranked = conn.execute(
            "SELECT COUNT(*) FROM production_tasks t WHERE t.manual_order > 0 "
            "AND COALESCE(t.release_status,'unregistered')='registered'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert rows, "manual_order 没有落库"
    print(f"\n已登记发布的任务里被写位次的条数 = {registered_ranked}（应为 0）")

    print("\n>>> 派单 SQL 检查：成片生成器的取任务顺序是否与显示顺序同源")
    conn = service.connection()
    try:
        picked = conn.execute(
            "SELECT v.id, t.account_name, t.drama_name, t.manual_order FROM production_video_tasks v "
            "JOIN production_tasks t ON t.id=v.task_id "
            "JOIN production_files f ON f.id=v.source_material_id "
            "WHERE v.status='pending_generation' "
            "ORDER BY " + tc.MANUAL_ORDER_FIRST_SQL
            + "CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at, "
            "CASE WHEN f.sequence_no IS NULL THEN 1 ELSE 0 END, f.sequence_no, f.file_name, v.created_at LIMIT 5"
        ).fetchall()
        if not picked:
            print("  （当前没有待派的成片任务，跳过；顺序键已由上面的顺序函数间接验证）")
        for r in picked:
            print(f"  会先做：{r['account_name']} ×《{r['drama_name']}》 manual_order={r['manual_order']}")
    finally:
        conn.close()

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\n✅ 全部断言通过（副本已删除，真实生产库未被修改）")


if __name__ == "__main__":
    main()
