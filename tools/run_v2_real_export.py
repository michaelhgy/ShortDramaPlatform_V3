"""Start one intentionally selected real V2 Jianying export attempt.

Example:
  python tools/run_v2_real_export.py --template-job-id <已就绪模板任务ID>
  python tools/run_v2_real_export.py --task-id <V2任务ID> --kind final --draft-name "草稿名" --draft-path "C:\\...\\草稿" --manual-check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import v2_file_service as service
from server.executor_management import ExecutorManager
from server.v2_exporter.core import ExportRepository
from server.v2_exporter.runner import V2ExportRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="启动一个真实 V2 剪映导出测试")
    parser.add_argument("--template-job-id", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--kind", choices=("template", "final"))
    parser.add_argument("--draft-name", default="")
    parser.add_argument("--draft-path", default="")
    parser.add_argument("--subject-id", default="")
    parser.add_argument("--manual-check", action="store_true")
    args = parser.parse_args()
    if args.template_job_id:
        conn = service.connection()
        try:
            row = conn.execute("SELECT id, task_id, draft_name, draft_path, status FROM template_jobs WHERE id=?", (args.template_job_id,)).fetchone()
        finally:
            conn.close()
        if not row or str(row["status"]) != "draft_ready":
            raise SystemExit("模板任务不存在或尚未处于 draft_ready 状态")
        payload = {"production_task_id": str(row["task_id"]), "subject_type": "template", "subject_id": str(row["id"]),
                   "draft_name": str(row["draft_name"]), "draft_path": str(row["draft_path"]), "manual_check_required": False}
    else:
        if not all((args.task_id, args.kind, args.draft_name, args.draft_path)):
            raise SystemExit("请提供 --template-job-id，或完整提供 --task-id --kind --draft-name --draft-path")
        payload = {"production_task_id": args.task_id, "subject_type": args.kind, "subject_id": args.subject_id,
                   "draft_name": args.draft_name, "draft_path": args.draft_path, "manual_check_required": args.manual_check}
    job = service.create_export_job(payload)
    # A CLI process must own its real attempt until completion.  The HTTP
    # service uses a background thread; doing that here would stop the daemon
    # thread as soon as this command exits.
    conn = service.connection()
    try:
        if bool(ExecutorManager(conn).state("video_exporter")["is_paused"]):
            raise SystemExit("视频导出器已因连续失败暂停，请先人工重新启动")
        settings = service.get_v2_settings()
        attempt = ExportRepository(conn).queue_new_attempt(str(job["job"]["id"]), deadline_minutes=int(settings["video_export_timeout_min"]), debug_enabled=bool(settings["video_export_debug"]))
        result = V2ExportRunner(conn, settings=settings).run(str(attempt["id"]))
    finally:
        conn.close()
    print(json.dumps({"job": job, "attempt": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
