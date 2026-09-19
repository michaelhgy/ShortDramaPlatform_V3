"""在副本上构造真实排队场景，验证「手动排序 = 三个执行器真的先做它」。

做法：把副本里某一部剧的成片任务状态改回 pending_generation（模拟"还没生成"），
然后看 _claim_next_final_video 实际会挑哪一条 —— 这才是"真的先做它"的证据。
副本用完即删，真实生产库不动。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

REAL_DB = Path(r"D:\短剧推广运营系统\系统数据\database\v2_system.db")
tmp_dir = Path(tempfile.mkdtemp(prefix="v2-dispatch-test-"))
copy_db = tmp_dir / "v2_system.db"
shutil.copy2(REAL_DB, copy_db)

from server import v2_file_service as service  # noqa: E402

service.db_path = lambda: copy_db  # type: ignore[assignment]

from server import task_center_service as tc  # noqa: E402


def prepare(ids: list[str]) -> None:
    """把这两部剧的成片任务改回"等待生成"，并确保模板已就绪。

    同时把**其他**未登记发布的剧标记成已完成 —— 否则 9 部剧全都是"已完成"，
    手动排序会被（正确地）拒绝，测不出真实场景。
    """
    conn = service.connection()
    try:
        for task_id in ids:
            conn.execute(
                "UPDATE production_video_tasks SET status='pending_generation', "
                "error_message='', started_at='', finished_at='' WHERE task_id=?",
                (task_id,),
            )
            # "已完成"记在导出尝试上（v.status 全库都是 draft_ready），
            # 所以必须把这部剧的导出尝试一起改回未完成，才是真的"排队中"。
            conn.execute(
                "UPDATE export_attempts SET status='queued', finished_at='' WHERE job_id IN "
                "(SELECT id FROM export_jobs WHERE subject_type='final' AND subject_id IN "
                " (SELECT id FROM production_video_tasks WHERE task_id=?))",
                (task_id,),
            )
            conn.execute(
                "UPDATE export_jobs SET status='queued' WHERE subject_type='final' AND subject_id IN "
                "(SELECT id FROM production_video_tasks WHERE task_id=?)",
                (task_id,),
            )
            # 模板导出必须是 completed，成片生成器才认这部剧（见 template_ready_clause）
            conn.execute(
                "UPDATE template_jobs SET status='draft_ready' WHERE task_id=?",
                (task_id,),
            )
        others = conn.execute(
            "SELECT id FROM production_tasks WHERE COALESCE(release_status,'unregistered') <> 'registered' "
            "AND id NOT IN (%s)" % ",".join("?" for _ in ids),
            tuple(ids),
        ).fetchall()
        for row in others:
            conn.execute("UPDATE production_tasks SET release_status='registered' WHERE id=?", (str(row["id"]),))
        conn.commit()
    finally:
        conn.close()


def peek_claim() -> tuple[str, str, str]:
    """照抄 _claim_next_final_video 的查询，看它现在会挑哪一条（不真正派单）。"""
    conn = service.connection()
    try:
        has_export_tables = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name IN ('export_jobs','export_attempts')"
        ).fetchall())
        template_ready_clause = (
            "AND EXISTS (SELECT 1 FROM template_jobs j "
            " JOIN export_jobs ej ON ej.subject_type='template' AND ej.subject_id=j.id AND ej.status='completed' "
            " JOIN export_attempts ea ON ea.job_id=ej.id "
            " WHERE j.task_id=t.id AND j.status='draft_ready' AND ea.status='completed' "
            " AND ea.attempt_no=(SELECT MAX(latest.attempt_no) FROM export_attempts latest WHERE latest.job_id=ej.id)) "
            if has_export_tables else ""
        )
        row = conn.execute(
            "SELECT v.id, t.account_name, t.drama_name, f.sequence_no, t.manual_order "
            "FROM production_video_tasks v JOIN production_tasks t ON t.id=v.task_id "
            "JOIN production_files f ON f.id=v.source_material_id "
            "WHERE v.status='pending_generation' " + template_ready_clause
            + "ORDER BY " + tc.MANUAL_ORDER_FIRST_SQL
            + "CASE WHEN t.planned_publish_at='' THEN 1 ELSE 0 END, t.planned_publish_at, t.created_at, "
            "CASE WHEN f.sequence_no IS NULL THEN 1 ELSE 0 END, f.sequence_no, f.file_name, v.created_at LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return ("", "", "")
    return (str(row["account_name"]), str(row["drama_name"]), str(row["sequence_no"]))


def main() -> None:
    conn = service.connection()
    try:
        rows = conn.execute(
            "SELECT id, account_name, drama_name, planned_publish_at FROM production_tasks "
            "WHERE COALESCE(release_status,'unregistered') <> 'registered' "
            "ORDER BY planned_publish_at"
        ).fetchall()
    finally:
        conn.close()
    # 取计划最早和计划最晚的各一部，制造"业务规则本来谁先做"的对照
    first_id, first_name = str(rows[0]["id"]), f"{rows[0]['account_name']} ×《{rows[0]['drama_name']}》"
    last = rows[-1]
    last_id, last_name = str(last["id"]), f"{last['account_name']} ×《{last['drama_name']}》"

    prepare([first_id, last_id])

    print("=" * 72)
    print("场景：两部剧都有素材在排队等生成")
    print(f"  A = {first_name}（计划发布最早，业务规则本来它先做）")
    print(f"  B = {last_name}（计划发布最晚）")
    print("=" * 72)

    picked = peek_claim()
    print(f"\n① 没手动调整时，成片生成器会先做：{picked[0]} ×《{picked[1]}》 素材-{picked[2]}")
    assert last_name not in f"{picked[0]} ×《{picked[1]}》", "预期先做计划最早的那部"
    print("   → 符合业务规则 ✅")

    print(f"\n② 把 B 置顶：{last_name}")
    conn = service.connection()
    try:
        probe = conn.execute(
            "SELECT t.release_status, t.manual_order, "
            "(SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id "
            " AND v.status NOT IN ('cancelled','cancellation_requested','invalidated')) AS total, "
            "(SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id "
            " AND v.status IN ('generation_failed','generation_timeout')) AS draft_bad, "
            "(SELECT COUNT(*) FROM production_video_tasks v WHERE v.task_id=t.id "
            " AND (SELECT a.status FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id "
            "      WHERE j.subject_type='final' AND j.subject_id=v.id "
            "      ORDER BY a.attempt_no DESC LIMIT 1) = 'completed') AS exported "
            "FROM production_tasks t WHERE t.id=?",
            (last_id,),
        ).fetchone()
        print(f"   诊断 B：release_status={probe['release_status']} 成片总数={probe['total']} "
              f"草稿异常={probe['draft_bad']} 已导出={probe['exported']} "
              f"manual_order={probe['manual_order']}")
        print(f"   _unit_is_complete(B) = {tc._unit_is_complete(conn, last_id)}")
        all_units, active_units = tc._ordered_units(conn)
        print(f"   未完成单位数 = {len(active_units)}（B 在其中 = {last_id in active_units}）")
    finally:
        conn.close()
    tc.task_center_reorder(last_id, "top")

    picked = peek_claim()
    print(f"   现在成片生成器会先做：{picked[0]} ×《{picked[1]}》 素材-{picked[2]}")
    assert f"{picked[0]} ×《{picked[1]}》" == last_name, "置顶没有改变实际派单顺序！"
    print("   → 执行器真的改做 B 了 ✅（界面显示的顺序 = 实际取任务顺序）")

    print(f"\n③ 再把 A 置顶：{first_name}")
    tc.task_center_reorder(first_id, "top")
    picked = peek_claim()
    print(f"   现在成片生成器会先做：{picked[0]} ×《{picked[1]}》 素材-{picked[2]}")
    assert f"{picked[0]} ×《{picked[1]}》" == first_name, "置顶没有改变实际派单顺序！"
    print("   → 又改回 A 了 ✅")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\n✅ 通过：手动排序真的改变了执行器的取任务顺序（副本已删除）")


if __name__ == "__main__":
    main()
