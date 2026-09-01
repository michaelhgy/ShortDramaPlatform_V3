"""Run one V2 finished-video composition task through the validated V1 engine."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from server import v2_file_service as service

# Keep V2's runtime self-contained, but use the same verified processing
# order as V1: detect source head/tail/overlays -> create a clean proxy ->
# create the native Jianying draft.  The lower-level direct draft writer is
# intentionally not the production entry point because it accepts raw video.
FINAL_SCRIPT = Path(__file__).resolve().parent / "scripts" / "run_jianying_composition_batch.py"
BGM_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

_PROCESS_LOCK = threading.Lock()
_ACTIVE_PROCESSES: dict[str, subprocess.Popen[str]] = {}
_RUN_TOKENS: dict[str, object] = {}


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """End the batch process and its media-analysis children on Windows."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    else:
        process.terminate()


def _set_video(video_id: str, status: str, **fields: str) -> None:
    conn = service.connection()
    try:
        values = {"status": status, "updated_at": service.now_text(), **fields}
        conn.execute(f"UPDATE production_video_tasks SET {', '.join(f'{k}=?' for k in values)} WHERE id=?", (*values.values(), video_id))
        conn.commit()
    finally:
        conn.close()


def cancel_finished_video(video_id: str) -> None:
    """Stop a running generation and invalidate its late status callbacks."""
    with _PROCESS_LOCK:
        process = _ACTIVE_PROCESSES.pop(video_id, None)
        _RUN_TOKENS.pop(video_id, None)
    if process and process.poll() is None:
        _terminate_process_tree(process)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _run_is_current(video_id: str, token: object) -> bool:
    with _PROCESS_LOCK:
        return _RUN_TOKENS.get(video_id) is token


def _numbered(root: Path, prefix: str) -> Path | None:
    # Use the same accepted-video set as the V2 resource service.  Otherwise
    # a newer numbered .mov insertion is invisible and an older .mp4 wins.
    candidates = sorted(
        (p for p in root.iterdir()
         if p.is_file() and p.name.startswith(prefix) and p.suffix.lower() in service.VIDEO_EXTENSIONS),
        key=lambda path: service.natural_key(path.name),
    )
    return candidates[-1] if candidates else None


def _processed_composition_command(*, source: Path, template_video: Path, pairing: Path,
                                   draft_root: Path, user_data_root: Path, real_photo_dir: Path,
                                   draft_prefix: str, account_id: str, midroll: Path, endroll: Path,
                                   bgm: Path, work_dir: Path, real_photo_files: list[Path] | None = None,
                                   local_vision_ai_mode: str = "compatibility") -> list[str]:
    """Build the V1-equivalent single-source processing command for V2."""
    return [
        sys.executable, str(FINAL_SCRIPT),
        "--source-file", str(source),
        "--template-video", str(template_video), "--pairing", str(pairing),
        "--draft-root", str(draft_root), "--user-data-root", str(user_data_root),
        "--real-photo-dir", str(real_photo_dir),
        "--real-photo-files", json.dumps([str(path) for path in (real_photo_files or [])], ensure_ascii=False),
        "--draft-prefix", draft_prefix, "--account-id", account_id,
        "--midroll", str(midroll), "--endroll", str(endroll),
        "--work-dir", str(work_dir), "--bgm", str(bgm),
        "--no-bgm-auto-replenish",
        "--local-vision-ai-mode", local_vision_ai_mode,
    ]


def _final_work_dir(*, task_root: Path, video_id: str) -> Path:
    """Keep all per-video temporary data under the production-task cache."""
    return task_root / "缓存" / "成片" / video_id


def run_finished_video(video_id: str) -> None:
    outcome = "failed"
    conn = service.connection()
    try:
        row = conn.execute(
            "SELECT v.*, f.file_path, f.file_name, f.sequence_no, t.created_date, t.account_name, t.drama_name, t.root_path, t.material_path, t.final_path "
            "FROM production_video_tasks v JOIN production_files f ON f.id=v.source_material_id "
            "JOIN production_tasks t ON t.id=v.task_id WHERE v.id=?", (video_id,)
        ).fetchone()
        template = conn.execute(
            "SELECT * FROM template_jobs WHERE task_id=? AND status='draft_ready' ORDER BY version_no DESC LIMIT 1",
            (str(row["task_id"]) if row else "",),
        ).fetchone()
    finally:
        conn.close()
    if not row or str(row["status"]) not in {"pending_generation", "generation_queued", "generation_failed", "generation_timeout"}:
        return
    token = object()
    with _PROCESS_LOCK:
        _RUN_TOKENS[video_id] = token
    try:
        if not template or not Path(str(template["video_path"] or "")).is_file() or not Path(str(template["pairing_path"] or "")).is_file():
            raise RuntimeError("对应模板视频或同源配对参数尚未准备好")
        if not FINAL_SCRIPT.is_file():
            raise RuntimeError(f"成片生成引擎不存在：{FINAL_SCRIPT}")
        workspace, _ = service.require_configured_paths()
        promotion = workspace / "生成资源" / "引流视频"
        midroll = _numbered(promotion, "中插")
        endroll = _numbered(promotion, "尾插")
        if not midroll or not endroll:
            raise RuntimeError("V2 生成资源/引流视频 缺少可用的中插或尾插视频")
        real_photo_dir = workspace / "生成资源" / "真人图片"
        real_photo_files = service.ensure_final_photo_reservation(str(row["task_id"]))
        music_root = workspace / "生成资源" / "BGM"
        music = [path for path in music_root.iterdir() if path.is_file() and path.suffix.lower() in BGM_EXTENSIONS]
        if not music:
            raise RuntimeError("V2 生成资源/BGM 缺少可用音乐")
        _set_video(video_id, "generating", started_at=service.now_text())
        # The configured limit covers the complete generation attempt, not
        # only the final communicate() call.
        settings = service.get_v2_settings()
        timeout_seconds = int(settings.get("final_generation_timeout_min", 30)) * 60
        deadline = time.monotonic() + timeout_seconds
        work_dir = _final_work_dir(task_root=Path(str(row["root_path"])), video_id=video_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        draft_root = Path(str(service.get_v2_settings().get("jianying_draft_root") or "")).expanduser()
        if not draft_root.is_dir():
            raise RuntimeError("尚未配置剪映草稿目录")
        draft_prefix = f"{row['created_date']}-{row['account_name']}-{row['drama_name']}-成片"
        command = _processed_composition_command(
            source=Path(str(row["file_path"])), template_video=Path(str(template["video_path"])),
            pairing=Path(str(template["pairing_path"])), draft_root=draft_root,
            user_data_root=draft_root.parents[1], real_photo_dir=real_photo_dir, real_photo_files=real_photo_files,
            draft_prefix=draft_prefix, account_id=str(row["account_name"]), midroll=midroll,
            endroll=endroll, bgm=random.choice(music), work_dir=work_dir,
            local_vision_ai_mode=str(settings.get("local_vision_ai_mode") or "compatibility"),
        )
        env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"
        if not _run_is_current(video_id, token):
            return
        process = subprocess.Popen(command, cwd=str(work_dir.parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace", env=env,
                                   creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        with _PROCESS_LOCK:
            _ACTIVE_PROCESSES[video_id] = process
        try:
            remaining = max(0.1, deadline - time.monotonic())
            stdout, stderr = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
            raise subprocess.TimeoutExpired(command, timeout_seconds, output=stdout, stderr=stderr)
        finally:
            with _PROCESS_LOCK:
                if _ACTIVE_PROCESSES.get(video_id) is process:
                    _ACTIVE_PROCESSES.pop(video_id, None)
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        (work_dir / "成片生成日志.txt").parent.mkdir(parents=True, exist_ok=True)
        (work_dir / "成片生成日志.txt").write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "成片生成器退出失败").strip()[-2000:])
        summary_path = work_dir / "批量结果.json"
        if not summary_path.is_file():
            raise RuntimeError("成片生成器未写入批量结果")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        item = next((candidate for candidate in summary.get("results", []) if str(candidate.get("source") or "") == str(row["file_path"])), None)
        if not item or item.get("status") != "STRUCTURAL_PASS_VISUAL_PENDING":
            raise RuntimeError("成片生成器未返回通过的草稿")
        draft_name = str(item.get("draft_name") or "")
        draft_path = Path(str(item.get("draft_path") or ""))
        if not draft_name or not draft_path.is_dir():
            raise RuntimeError("成片生成器未返回有效草稿目录")
        if not _run_is_current(video_id, token):
            return
        _set_video(video_id, "draft_ready", draft_path=str(draft_path), output_path="", finished_at=service.now_text())
        service.ensure_export_job_for_finished_video(row, draft_name=draft_name, draft_path=draft_path)
        outcome = "completed"
    except subprocess.TimeoutExpired:
        if _run_is_current(video_id, token):
            _set_video(video_id, "generation_timeout", error_message="成片生成超时", finished_at=service.now_text())
        outcome = "timed_out"
    except Exception as exc:
        if _run_is_current(video_id, token):
            _set_video(video_id, "generation_failed", error_message=str(exc), finished_at=service.now_text())
    finally:
        stale_run = not _run_is_current(video_id, token)
        with _PROCESS_LOCK:
            if _RUN_TOKENS.get(video_id) is token:
                _RUN_TOKENS.pop(video_id, None)
        if stale_run:
            return
        conn = service.connection()
        try:
            from server.executor_management import ExecutorManager
            ExecutorManager(conn).report_result("final_generator", outcome=outcome)
        finally:
            conn.close()


def start_finished_video(video_id: str) -> dict[str, str]:
    conn = service.connection()
    try:
        row = conn.execute("SELECT status FROM production_video_tasks WHERE id=?", (video_id,)).fetchone()
        if not row:
            raise ValueError("成片生成任务不存在")
        if str(row["status"]) not in {"pending_generation", "generation_failed", "generation_timeout"}:
            raise ValueError("当前成片任务不支持启动或重试")
        conn.execute("UPDATE production_video_tasks SET status='generation_queued', error_message='', updated_at=? WHERE id=?", (service.now_text(), video_id)); conn.commit()
    finally: conn.close()
    import threading
    threading.Thread(target=run_finished_video, args=(video_id,), daemon=True, name=f"v2-final-{video_id[:8]}").start()
    return {"id": video_id, "status": "generation_queued"}
