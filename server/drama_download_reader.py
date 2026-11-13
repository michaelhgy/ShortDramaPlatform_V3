# -*- coding: utf-8 -*-
"""Resumable V3 steps for reading a WeChat task and collecting links."""
from __future__ import annotations

import json
import hashlib
import os
import re
import queue
import time
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from server.drama_download_state import episode_number, title_episode, probe_video, receipt_matches, reconcile


TOOLS = Path(__file__).resolve().parents[1] / "tools" / "short_drama_downloader_lab"
READER = TOOLS / "wechat_task_reader.py"
COLLECTOR = TOOLS / "阶段1_收集链接.py"
_LOCK = threading.RLock()
_THREAD: threading.Thread | None = None
_ACTIVE_PROCESS: subprocess.Popen | None = None
_CANCEL_EVENT = threading.Event()
_STATE: dict[str, Any] = {"status": "idle", "phase": "idle", "logs": []}


def _state_path() -> Path:
    configured = os.environ.get("V3_DRAMA_READ_TASK_STATE", "").strip()
    if configured:
        return Path(configured)
    try:
        from server.v2_file_service import DATA_ROOT
        if DATA_ROOT is not None:
            return DATA_ROOT / "drama-download" / "state.json"
    except Exception:
        pass
    return TOOLS.parent.parent / "drama-download-state.json"


def _table_path() -> Path:
    path = _state_path().parent / "采集表.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_path() -> Path:
    path = _state_path().parent / "分享链接.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_link_records(table: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not table.exists():
        return records
    for raw in table.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [part.strip() for part in raw.split("\t")]
        if len(parts) < 3 or not parts[2]:
            continue
        episode_match = re.search(r"(\d+)", parts[1])
        records.append({
            "drama_name": parts[0],
            "episode": int(episode_match.group(1)) if episode_match else 0,
            "episode_label": parts[1],
            "share_url": parts[2],
        })
    return records


def _write_link_manifest(table: Path) -> tuple[Path, int]:
    records = _read_link_records(table)
    path = _manifest_path()
    manifest = {
        "schema_version": 1,
        "source": "v3-drama-download",
        "updated_at": _now(),
        "table_path": str(table),
        "manifest_path": str(path),
        "records": records,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path, len(records)


def link_manifest() -> dict[str, Any]:
    path = _manifest_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {"schema_version": 1, "source": "v3-drama-download", "updated_at": "", "table_path": str(_table_path()), "manifest_path": str(path), "records": []}
    return payload if isinstance(payload, dict) else {"schema_version": 1, "source": "v3-drama-download", "updated_at": "", "table_path": str(_table_path()), "manifest_path": str(path), "records": []}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save() -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_STATE, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _set(**values: Any) -> None:
    with _LOCK:
        _STATE.update(values)
        phase = _STATE.get("phase")
        if phase in {"read-task", "collect-links", "parse-download", "verify-download"} and "status" in values:
            stage = {"queued": "running", "running": "running", "succeeded": "done", "failed": "failed", "stopped": "pending"}.get(values["status"])
            if stage:
                _STATE.setdefault("stage_states", {})[phase] = stage
        if phase == "cleanup-task" and "status" in values:
            _STATE["cleanup_state"] = {"running":"running", "queued":"running", "failed":"failed", "succeeded":"done", "stopped":"pending"}.get(values["status"], _STATE.get("cleanup_state", "pending"))
        if _STATE.get("status") not in {"queued", "running"}:
            for key, value in _STATE.get("stage_states", {}).items():
                if value == "running":
                    _STATE["stage_states"][key] = "done" if key != phase and phase in {"verify-download", "cleanup-task", "completed"} else "pending"
        _STATE["updated_at"] = _now()
        _save()


def _append_log(message: str) -> None:
    message = message.strip()
    if not message:
        return
    with _LOCK:
        _STATE["logs"] = (list(_STATE.get("logs") or []) + [message])[-300:]
        stage_logs = dict(_STATE.get("stage_logs") or {})
        phase = str(_STATE.get("phase") or "idle")
        stage_logs[phase] = (list(stage_logs.get(phase) or []) + [message])[-300:]
        _STATE["stage_logs"] = stage_logs
        _STATE["updated_at"] = _now()
        _save()


def _cancelled() -> bool:
    return _CANCEL_EVENT.is_set()


def _mark_stopped() -> None:
    if _STATE.get("status") == "stopped":
        return
    _append_log("已停止当前脚本，已保留已经采集和下载的文件")
    _set(status="stopped", current_step="已停止当前任务", error="用户已停止任务", stop_requested=False, complete=bool(_STATE.get("complete")) if _STATE.get("phase") == "cleanup-task" else False)


def _resumable_phase(state: dict[str, Any]) -> str | None:
    if (state.get("status") in {"failed", "stopped"}
            and state.get("phase") in {"parse-download", "verify-download"}
            and not state.get("cleanup_pending")
            and (state.get("task") or {}).get("drama_name")
            and state.get("journal_path") and Path(state["journal_path"]).is_file()):
        return str(state["phase"])
    return None


def status() -> dict[str, Any]:
    with _LOCK:
        if _STATE.get("status") == "idle":
            try:
                _STATE.update(json.loads(_state_path().read_text(encoding="utf-8")))
                if _STATE.get("status") in {"queued", "running"} and not (_THREAD and _THREAD.is_alive()):
                    previous = str(_STATE.get("current_step") or "执行任务")
                    _append_log(f"上次运行已中断，停在：{previous}；已保留已采集链接和下载文件")
                    _set(status="failed", current_step="上次运行已中断，请重新开始任务", error="程序退出导致任务中断", stop_requested=False)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                pass
        result = dict(_STATE)
        result["resume_phase"] = _resumable_phase(result)
        # 旧失败记录可能仍留着下载前的缺集列表；按当前逐集结果返回，不改历史文件。
        if result.get("episodes") and int(result.get("expected_count") or 0) > 0:
            result["missing_video_episodes"] = [n for n in range(1, int(result["expected_count"])+1)
                if not result["episodes"].get(str(n), {}).get("verified")]
        result["stage_states"] = dict(_STATE.get("stage_states") or {})
        if result.get("cleanup_pending") and result.get("complete"):
            result["stage_states"] = {key:"done" for key in ("read-task","collect-links","parse-download","verify-download")}
            result["phase"] = "cleanup-task"
            result["cleanup_state"] = "running" if result.get("status") in {"queued","running"} else "pending" if result.get("status") == "stopped" else "failed"
            stage_logs = {key:list(rows) for key, rows in (_STATE.get("stage_logs") or {}).items()}
            old_cleanup = [row for row in stage_logs.get("verify-download", []) if row.startswith("清理停止：")]
            stage_logs["verify-download"] = [row for row in stage_logs.get("verify-download", []) if not row.startswith("清理停止：")]
            if old_cleanup:
                stage_logs["cleanup-task"] = old_cleanup + stage_logs.get("cleanup-task", [])
            result["stage_logs"] = stage_logs
            result["cleanup_error"] = result.get("cleanup_error") or (old_cleanup[-1].removeprefix("清理停止：") if old_cleanup else result.get("error"))
        return result


def _consume_progress(line: str) -> bool:
    if line.startswith("EPISODE_RESULT="):
        record = json.loads(line.split("=", 1)[1])
        number = episode_number(record.get("expected_episode") or record.get("episode"))
        if number:
            episodes = _STATE.setdefault("episodes", {})
            episodes.setdefault(str(number), {}).update(record)
            _summarize_episodes()
            _persist_task()
        return True
    if not line.startswith("PROGRESS="):
        return False
    try:
        event = json.loads(line[len("PROGRESS="):])
        message = str(event["message"]).strip()
    except (ValueError, KeyError, TypeError):
        return True
    if message and not _cancelled():
        if event.get("action") == "inventory":
            count = int(event.get("total") or 0)
            catalog_count = _expected_episode_count(str((_STATE.get("task") or {}).get("drama_name") or ""))
            _set(expected_count=count, total_source="phone", catalog_expected_count=catalog_count)
            if catalog_count and count != catalog_count:
                _append_log(f"手机选集显示{count}集，资料库为{catalog_count}集，需要核对总集数；尚不允许整剧完成")
                _set(total_conflict=True)
            else:
                _set(total_conflict=False)
            _persist_task()
        elif event.get("action") == "parsed":
            number = int(event.get("episode") or 0)
            row = _STATE.setdefault("episodes", {}).setdefault(str(number), {})
            returned = event.get("returned_episode")
            confirmed = returned == number or (returned is None and row.get("link_confirmed") is True)
            row.update(title=event.get("title", ""), returned_episode=returned,
                       parse_status="succeeded" if confirmed else "unconfirmed")
            if confirmed:
                row["confirmation_source"] = "parser" if returned else "phone"
            _summarize_episodes()
            _persist_task()
        elif event.get("action") == "cleanup_card_attempted":
            _set(cleanup_card_attempted=True)
        elif event.get("action") == "cleanup_card_removed":
            _set(cleanup_card_removed=True)
        elif event.get("action") == "collected":
            number = int(event["episode"])
            _sync_links()
            _STATE["episodes"][str(number)]["link_confirmed"] = True
            _persist_task()
        _set(current_step=message)
        if event.get("keep", True):
            _append_log(message)
    return True


def _run(command: list[str], on_line) -> tuple[int, list[str]]:
    global _ACTIVE_PROCESS
    process = subprocess.Popen(
        command, cwd=str(TOOLS), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    with _LOCK:
        _ACTIVE_PROCESS = process
    if _cancelled():
        process.terminate()
    output: list[str] = []
    lines: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line.rstrip())
        finally:
            lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    last_action = str(_STATE.get("current_step") or "正在执行脚本")
    last_update = last_heartbeat = time.monotonic()
    try:
        while True:
            try:
                clean = lines.get(timeout=1)
            except queue.Empty:
                now = time.monotonic()
                if _cancelled() and process.poll() is None:
                    process.terminate()
                if now - last_update > 300 and process.poll() is None:
                    process.kill()
                    raise TimeoutError(f"当前动作超过5分钟没有进展：{last_action}")
                if not _cancelled() and now - last_heartbeat >= 5:
                    elapsed = int(now - last_update)
                    _set(current_step=f"{last_action}（已等待{elapsed}秒，尚无新进展）")
                    last_heartbeat = now
                continue
            if clean is None:
                break
            output.append(clean)
            previous_step = _STATE.get("current_step")
            consumed = _consume_progress(clean)
            if not consumed:
                on_line(clean)
            if consumed or _STATE.get("current_step") != previous_step:
                last_action = str(_STATE.get("current_step") or last_action)
                last_update = last_heartbeat = time.monotonic()
        code = process.wait()
        return (130 if _cancelled() else code), output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if process.stdout is not None:
            process.stdout.close()
        with _LOCK:
            if _ACTIVE_PROCESS is process:
                _ACTIVE_PROCESS = None


def _read_worker(reset_logs: bool = True) -> None:
    if _cancelled():
        _mark_stopped()
        return
    values: dict[str, Any] = {"status": "running", "phase": "read-task", "current_step": "正在检查当前手机界面", "error": ""}
    values["stage_states"] = {key:"pending" for key in ("read-task","collect-links","parse-download","verify-download")}
    if reset_logs:
        values.update(logs=[], stage_logs={})
    _set(**values)

    def on_line(line: str) -> None:
        if line == "TASK_SOURCE=current":
            _set(current_step="已在当前聊天页识别任务")
            _append_log("当前界面已识别到任务，继续使用当前微信页面")
        elif line == "TASK_SOURCE=restart":
            _set(current_step="正在重启主微信并进入第一条置顶聊天")
            _append_log("当前界面未识别到任务，正在重启主微信并进入第一条置顶聊天")

    command = [sys.executable, "-u", "-X", "utf8", str(READER)]
    known_chat = str((_STATE.get("task") or {}).get("chat_name") or "")
    if known_chat and known_chat != "当前聊天":
        command += ["--expected-chat", known_chat]
    code, output = _run(command, on_line)
    if _cancelled():
        _mark_stopped()
        return
    records = [line[len("TASK_JSON="):] for line in output if line.startswith("TASK_JSON=")]
    record = json.loads(records[-1]) if records else {}
    if code == 0 and not record.get("error"):
        task = dict(record)
        if task.get("read_source") == "current_screen":
            _append_log(f"已从当前界面识别任务：{task.get('task_label', '')}")
        else:
            _append_log(f"已从第一条置顶聊天识别任务：{task.get('task_label', '')}")
        tasks = task.get("tasks") if isinstance(task.get("tasks"), list) else [task]
        _set(status="succeeded", phase="read-task", current_step=f"已读取 {len(tasks)} 个置顶任务", task=task, tasks=tasks, task_count=len(tasks), current_task_index=len(tasks)-1, error="")
    else:
        message = str(record.get("error") or "读取脚本失败")
        _append_log(f"读取失败：{message}")
        _set(status="failed", phase="read-task", current_step="读取置顶任务失败", error=message)


def _context() -> tuple[str, str, Path]:
    from server.v2_file_service import get_v2_settings
    drama = str((_STATE.get("task") or {}).get("drama_name") or "").strip()
    if not drama or drama in {".", ".."} or re.search(r'[<>:"/\\|?*\t\r\n]', drama):
        raise ValueError("任务剧名为空或含有不能用于目录的字符")
    theater = _theater_for_drama(drama)
    value = str(get_v2_settings().get("drama_download_root") or "").strip()
    if not value or not Path(value).is_absolute():
        raise ValueError("请先在 V3 设置有效的原片下载目录")
    root = Path(value).expanduser()
    if not root.is_dir():
        raise ValueError(f"下载根目录不可访问，请检查共享盘：{root}")
    return drama, theater, root


def _persist_task() -> None:
    path = _STATE.get("journal_path")
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: _STATE.get(key) for key in ("task", "theater_name", "download_root", "expected_count", "total_source", "total_conflict", "catalog_expected_count", "episodes")}
    payload.update(schema_version=2, updated_at=_now())
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def _summarize_episodes() -> None:
    rows = _STATE.get("episodes") or {}
    collected = sorted(int(n) for n, row in rows.items() if row.get("link"))
    parsed = sorted(int(n) for n, row in rows.items() if row.get("parse_status") == "succeeded" or (row.get("confirmation_source") in {"parser", "phone"} and row.get("status") == "ok"))
    downloaded = sorted(int(n) for n, row in rows.items() if row.get("status") == "ok" and row.get("file"))
    verified = sorted(int(n) for n, row in rows.items() if row.get("verified"))
    expected = int(_STATE.get("expected_count") or 0)
    _set(collected_count=len(collected), collected_episodes=collected, parsed_episodes=parsed,
         downloaded_episodes=downloaded, verified_episodes=verified, verified_count=len(verified),
         missing_link_episodes=[n for n in range(1, expected+1) if n not in collected and n not in verified],
         missing_video_episodes=[n for n in range(1, expected+1) if n not in verified],
         parse_records=rows)


def _sync_links() -> None:
    drama = str((_STATE.get("task") or {}).get("drama_name") or "")
    episodes = _STATE.setdefault("episodes", {})
    for row in _read_link_records(_table_path()):
        if row["drama_name"] != drama or not row["episode"]:
            continue
        key = str(row["episode"])
        old = episodes.get(key, {})
        if old.get("link") != row["share_url"]:
            episodes[key] = {"episode": row["episode"], "link": row["share_url"], "link_confirmed": False}
    _summarize_episodes()
    _persist_task()


def _prepare_task() -> None:
    drama, theater, root = _context()
    identity = hashlib.sha256(json.dumps([str(root).casefold(), theater, drama], ensure_ascii=False).encode()).hexdigest()[:24]
    journal = _state_path().parent / "tasks" / (identity + ".json")
    previous = json.loads(journal.read_text(encoding="utf-8")) if journal.exists() else {}
    _set(journal_path=str(journal), theater_name=theater, download_root=str(root),
         expected_count=int(previous.get("expected_count") or _expected_episode_count(drama)),
         total_source=previous.get("total_source", "catalog"), total_conflict=bool(previous.get("total_conflict")),
         episodes=previous.get("episodes") or {}, complete=False, manual_cleanup_required=False,
         manual_cleanup_message="", parsed_episodes=[], verified_count=0)
    _sync_links()
    # 历史成功记录只作为身份依据，仍需对实际文件检查；不相信旧的 complete 标记。
    history = _state_path().parent / "解析结果.jsonl"
    if history.exists():
        for raw in history.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(raw)
                n = episode_number(row.get("expected_episode") or row.get("episode"))
                target = Path(str(row.get("file") or ""))
                expected_folder = root / theater / drama
                current = _STATE["episodes"].get(str(n), {})
                if (row.get("status") == "ok" and row.get("drama") == drama and n > 0
                    and target.parent.resolve() == expected_folder.resolve()
                    and title_episode(str(row.get("title") or "")) == n
                    and current.get("link") == row.get("link") and not current.get("file")):
                    current.update(row, confirmation_source="parser", verified=False)
            except (ValueError, TypeError, OSError):
                continue
    _check_files(final=False)
    _persist_task()


def _check_files(*, final: bool) -> None:
    drama, theater, root = _context()
    folder = root / theater / drama
    files = sorted(folder.glob("*.mp4")) if folder.is_dir() else []
    episodes = _STATE.setdefault("episodes", {})
    for index, file in enumerate(files, 1):
        if _cancelled():
            raise InterruptedError("已停止检查")
        n = title_episode(file.stem)
        row = episodes.get(str(n), {})
        # 无身份依据的文件不能靠文件名冒充对应集。
        known = row.get("file") and Path(row["file"]).resolve() == file.resolve()
        if not known or row.get("confirmation_source") not in {"parser", "phone"}:
            continue
        if not receipt_matches(row, file, str(row.get("link") or "")) or final:
            _set(current_step=f"正在校验第{n}集视频（{index}/{len(files)}）")
            _append_log(str(_STATE["current_step"]))
            try:
                details = probe_video(file, cancelled=_cancelled)
                row.update(details, verified=True, status="ok")
                row.pop("error", None)
                row.pop("failure_kind", None)
                _append_log(f"第{n}集视频轨道和时长检查通过")
            except InterruptedError:
                raise
            except (RuntimeError, ValueError, OSError, TimeoutError) as exc:
                row.update(verified=False, failure_kind="verify", error=str(exc))
                _append_log(f"第{n}集校验失败：{exc}，保留原文件")
    _summarize_episodes()
    result = reconcile(int(_STATE.get("expected_count") or 0), episodes, files)
    if _STATE.get("total_conflict"):
        result["complete"] = False
    _set(**result)
    _persist_task()


def _collect_worker(payload: dict[str, Any]) -> None:
    if _cancelled():
        _mark_stopped()
        return
    if not _STATE.get("journal_path"):
        _prepare_task()
    task = dict(_STATE.get("task") or {})
    drama = str(task.get("drama_name") or "")
    table = _table_path()
    command = [sys.executable, "-u", "-X", "utf8", str(COLLECTOR), "--drama", drama, "--table", str(table)]
    repair = sorted({int(n) for n in payload.get("repair_episodes", []) if int(n) > 0})
    if repair:
        command += ["--no-nav", "--repair", ",".join(map(str, repair))]
    else:
        card = task.get("card_position") or {}
        if not card.get("x") or not card.get("y"):
            raise ValueError("任务没有已确认的卡片位置，请重新读取置顶任务")
        command += ["--task-x", str(int(card["x"])), "--task-y", str(int(card["y"]))]
    valid = _STATE.get("verified_episodes") or []
    if valid:
        command += ["--skip-episodes", ",".join(map(str, valid))]
    if int(payload.get("count") or 0) > 0:
        command += ["--count", str(int(payload["count"]))]
    _set(status="running", phase="collect-links", complete=False, current_step="正在采集当前任务的分享链接", error="", table_path=str(table))
    code, output = _run(command, lambda line: None)
    if _cancelled():
        _mark_stopped()
        return
    _sync_links()
    manifest, count = _write_link_manifest(table)
    rows = [row for row in _read_link_records(table) if row["drama_name"] == drama]
    _set(link_manifest_path=str(manifest), link_record_count=count, link_episode_map=rows)
    missing = list(_STATE.get("missing_link_episodes") or [])
    if code == 0:
        _append_log(f"本剧已保存{len(rows)}条链接，已验证视频{_STATE.get('verified_count', 0)}集")
        _set(status="succeeded", phase="collect-links", current_step="本轮分享链接采集结束", error="")
    else:
        message = str(_STATE.get("current_step") or "采集脚本未完成")
        _set(status="failed", phase="collect-links", current_step=message, error=message, complete=False)


def _theater_for_drama(drama: str) -> str:
    from server.v2_file_service import connection
    with connection() as conn:
        rows = conn.execute("""SELECT d.id, t.name FROM dramas d JOIN theaters t ON t.id=d.theater_id
            WHERE d.current_name=?""", (drama,)).fetchall()
    if len(rows) != 1 or not str(rows[0]["name"] or "").strip():
        raise ValueError(f"《{drama}》未唯一关联剧场，请先在 V3 资料中心确认剧目与剧场")
    theater = str(rows[0]["name"]).strip()
    if theater in {".", ".."} or re.search(r'[<>:"/\\|?*\t\r\n]', theater):
        raise ValueError("剧场名称含有不能用于目录的字符")
    return theater


def _expected_episode_count(drama: str) -> int:
    try:
        from server.v2_file_service import connection
        with connection() as conn:
            row = conn.execute("""SELECT e.content FROM v3_catalog_links l
                JOIN v3_catalog_entries e USING(source, external_id)
                JOIN dramas d ON d.id=l.drama_id
                WHERE d.current_name=? ORDER BY json_extract(e.content, '$.mediaCount') DESC LIMIT 1""", (drama,)).fetchone()
        return int(json.loads(row["content"]).get("mediaCount") or 0) if row else 0
    except Exception:
        return 0


def _manifest_episodes(drama: str) -> set[int]:
    return {
        int(record["episode"])
        for record in _read_link_records(_table_path())
        if record.get("drama_name") == drama and int(record.get("episode") or 0) > 0
    }


def _download_worker(payload: dict[str, Any] | None = None) -> None:
    if _cancelled():
        _mark_stopped()
        return
    drama, theater, root = _context()
    _sync_links()
    episodes = _STATE.get("episodes") or {}
    selected = (payload or {}).get("episodes")
    expected = int(_STATE.get("expected_count") or 0)
    wanted = sorted(int(n) for n, row in episodes.items() if row.get("link") and (not expected or int(n) <= expected) and
        not row.get("verified") and (selected is None or int(n) in selected))
    count = int((payload or {}).get("count") or 0)
    if count > 0:
        wanted = wanted[:count]
    _set(status="running", phase="parse-download", current_step=f"本轮只处理{len(wanted)}集，跳过已校验视频", error="", planned_download_episodes=wanted)
    _append_log(str(_STATE["current_step"]))
    if not wanted:
        _set(status="succeeded", phase="parse-download", current_step="已有视频无需重复下载", parse_failed_episodes=[], repair_episodes=[], failed_episodes=[])
        return
    _persist_task()
    result_path = _state_path().parent / "解析结果.jsonl"
    command = [sys.executable, "-u", "-X", "utf8", str(TOOLS / "批量解析下载.py"),
        "--table", str(_table_path()), "--drama", drama, "--theater", theater,
        "--output-root", str(root), "--result-path", str(result_path),
        "--log-path", str(_state_path().parent / "下载记录.log"),
        "--resume-records", str(_STATE["journal_path"]), "--episodes", ",".join(map(str, wanted))]
    _set(result_path=str(result_path))
    code, _ = _run(command, lambda line: None)
    if _cancelled():
        _mark_stopped()
        return
    episodes = _STATE.get("episodes") or {}
    failed = [n for n in wanted if not episodes.get(str(n), {}).get("verified")]
    repairs = [n for n in failed if episodes.get(str(n), {}).get("failure_kind") in {"link_mismatch", "episode_unknown"}]
    _set(parse_failed_episodes=repairs, repair_episodes=repairs, failed_episodes=failed)
    if code == 0 and not failed:
        _set(status="succeeded", phase="parse-download", current_step="本轮后台解析下载完成", error="")
    else:
        message = "、".join(map(str, failed)) or "未知"
        _set(status="failed", phase="parse-download", current_step=f"第{message}集尚未完成，已保留其他成功视频", error="部分集数未完成", complete=False)


def _verify_worker() -> None:
    if _cancelled():
        _mark_stopped()
        return
    _set(status="running", phase="verify-download", current_step="正在逐集对账并检查视频", error="")
    _check_files(final=True)
    if _cancelled():
        _mark_stopped()
        return
    if _STATE.get("complete"):
        _append_log(f"第1至第{_STATE['expected_count']}集逐集对账完成，视频轨道和时长检查通过")
        _set(status="succeeded", phase="verify-download", current_step="本剧视频已逐集检查完成", error="")
    else:
        missing = "、".join(map(str, _STATE.get("missing_video_episodes") or []))
        message = ("手机总集数与资料库不一致，保留任务等待核对" if _STATE.get("total_conflict")
            else "尚未确认总集数，不能判定整剧完成" if not _STATE.get("expected_count")
            else f"第{missing or '未确认'}集尚未通过检查，保留任务")
        _append_log(message)
        _set(status="failed", phase="verify-download", current_step=message, error=message, complete=False)


def _delete_worker() -> None:
    if not _STATE.get("complete") or _cancelled():
        raise RuntimeError("尚未完成逐集校验，未删除微信消息")
    task = _STATE.get("task") or {}
    was_pending = bool(_STATE.get("cleanup_pending"))
    _set(status="running", phase="cleanup-task", cleanup_state="running", cleanup_error="", error="",
         stage_states={**(_STATE.get("stage_states") or {}), "verify-download":"done"},
         current_step="视频校验已通过，正在清理本次微信卡片和剧名")
    if was_pending:
        _set(current_step="正在核对第一条置顶聊天和" + str(task.get("task_label") or "") + "，准备恢复清理")
        _append_log(str(_STATE["current_step"]))
        # 先重新核对置顶聊天标题和最后一条标签，可恢复“卡片已删、标签仍在”。
        command = [sys.executable, "-u", "-X", "utf8", str(READER), "--inspect-cleanup",
                   "--expected-label", str(task.get("task_label") or ""), "--expected-chat", str(task.get("chat_name") or "")]
        code, output = _run(command, lambda line: _append_log("清理核对：" + str(json.loads(line.split("=",1)[1]).get("error", ""))) if line.startswith("TASK_JSON=") else None)
        inspection = next((json.loads(line.split("=",1)[1]) for line in output if line.startswith("CLEANUP_INSPECTION=")), None)
        if _cancelled():
            _mark_stopped()
            return
        if code or not inspection or inspection.get("task_label") != task.get("task_label"):
            _set(status="failed", cleanup_state="failed", current_step="视频已完成，微信任务身份未确认", error="无法确认本次聊天和剧名，未删除其他消息", cleanup_error="请查看清理核对记录")
            return
        task = {**task, "chat_name":inspection["chat_name"]}
        visible = [{**row, "chat_name":inspection["chat_name"]} for row in (_STATE.get("tasks") or [])]
        _set(task=task, tasks=visible, cleanup_card_removed=inspection.get("label_only") is True)
        _append_log("已核对置顶聊天：" + inspection["chat_name"] + ("；本次卡片已不在，只恢复清理剧名" if inspection.get("label_only") else "；继续清理本次卡片和剧名"))
    command = [sys.executable, "-u", "-X", "utf8", str(READER), "--delete-current",
        "--expected-label", str(task.get("task_label") or ""), "--expected-chat", str(task.get("chat_name") or "")]
    if _STATE.get("cleanup_card_removed"):
        command.append("--resume-label-only")
    _set(cleanup_pending=True, current_step=("正在恢复删除剧名：" if _STATE.get("cleanup_card_removed") else "正在删除卡片和剧名：") + str(task.get("task_label") or ""))
    _append_log(str(_STATE["current_step"]))
    errors = []
    def consume(line):
        if line.startswith("TASK_JSON="):
            message = str(json.loads(line.split("=", 1)[1]).get("error", ""))
            errors.append(message)
            _append_log("清理停止：" + message)
    code, output = _run(command, consume)
    if _cancelled():
        _mark_stopped()
    elif code != 0 or "DELETE_RESULT=success" not in output:
        message = errors[-1] if errors else "微信任务清理结果未确认"
        _set(status="failed", cleanup_state="failed", cleanup_error=message,
             current_step="视频校验已通过，微信任务清理未完成，已停止队列", error=message)
    else:
        _append_log("已确认本次卡片和剧名均已清理，视频成果保留")
        visible = list(_STATE.get("tasks") or [])
        if visible and visible[-1].get("task_label") == task.get("task_label"):
            visible.pop()
        _set(status="succeeded", cleanup_state="done", cleanup_error="", current_step="已清理本次剧名和卡片", cleanup_confirmed=True, cleanup_pending=False, cleanup_card_removed=False,
             tasks=visible, task_count=len(visible), current_task_index=-1)


def _finish_worker() -> None:
    _set(status="succeeded", phase="completed", current_step="本剧视频和微信任务均已完成", error="", complete=True, manual_cleanup_required=False)


def _pipeline_worker(payload: dict[str, Any] | None = None) -> None:
    payload = dict(payload or {})
    resume_phase = payload.pop("_resume_phase", None)
    limit = int(payload.get("task_limit") or 0)
    processed = 0
    completed = []
    previous_label = None
    if _STATE.get("cleanup_pending"):
        _set(status="running", phase="verify-download", current_step="正在复核上次视频成果，再恢复微信清理")
        _prepare_task()
        _verify_worker()
        if not _STATE.get("complete") or _STATE.get("status") != "succeeded":
            return
        _delete_worker()
        if _STATE.get("status") != "succeeded":
            return
        processed = 1
        completed.append({"task_label":(_STATE.get("task") or {}).get("task_label"), "chat_name":(_STATE.get("task") or {}).get("chat_name"), "drama_name": (_STATE.get("task") or {}).get("drama_name"), "verified_count": _STATE.get("verified_count")})
        _set(completed_tasks=completed, completed_task_count=processed)
        _finish_worker()
    while not limit or processed < limit:
        if _cancelled():
            _mark_stopped()
            return
        resuming = bool(resume_phase and processed == 0)
        if resuming:
            # 后台续跑锁定原任务，不重启微信，不读取可能已经变化的置顶任务。
            drama, theater, root = _context()
            identity = hashlib.sha256(json.dumps([str(root).casefold(), theater, drama], ensure_ascii=False).encode()).hexdigest()[:24]
            expected_journal = _state_path().parent / "tasks" / (identity + ".json")
            if expected_journal.resolve() != Path(str(_STATE.get("journal_path") or "")).resolve():
                raise ValueError("下载目录或剧场已变化，请恢复原设置后继续本次任务")
            _set(status="succeeded", phase=resume_phase, error="")
        else:
            _read_worker(reset_logs=processed == 0)
        if _STATE.get("status") != "succeeded":
            if "没有 #剧名" in str(_STATE.get("error") or ""):
                _set(status="succeeded", phase="completed", current_step=f"没有待处理任务，本轮已完成{processed}部", complete=True, tasks=[], task_count=0, completed_tasks=completed, completed_task_count=processed, stage_states={key: "done" if processed else "pending" for key in ("read-task", "collect-links", "parse-download", "verify-download")})
            return
        task = _STATE.get("task") or {}
        label = (task.get("chat_name"), task.get("task_label"))
        if label == previous_label:
            raise RuntimeError("删除后仍读到同一任务，已停止队列，避免重复处理")
        _set(completed_tasks=completed, cleanup_confirmed=False, cleanup_state="pending", cleanup_error="",
             cleanup_card_attempted=False, cleanup_card_removed=False,
             stage_states=({**(_STATE.get("stage_states") or {}), "read-task":"done", "collect-links":"done"}
                           if resuming else {"read-task": "done"}))
        _set(status="running", phase=resume_phase if resuming else "read-task",
             current_step="正在复核本剧已有成果，准备从中断阶段继续" if resuming else "正在盘点本剧已完成的视频和链接")
        _prepare_task()
        _append_log(f"已盘点本剧成果：{_STATE.get('verified_count', 0)}集可复用")
        _set(status="succeeded", phase=resume_phase if resuming else "read-task")
        if resuming:
            _append_log("已复用置顶任务和分享链接，跳过手机读取与采集阶段")
            if _STATE.get("missing_link_episodes"):
                _set(status="failed", phase="collect-links", current_step="已有链接发生缺失，请继续采集缺失集数", error="续跑检查发现缺少链接，已保留成功视频")
                return
        else:
            _collect_worker(payload)
        if _cancelled():
            return
        if _STATE.get("status") != "succeeded":
            return
        if not _STATE.get("expected_count") or _STATE.get("total_conflict"):
            _verify_worker()
            return
        missing = list(_STATE.get("missing_link_episodes") or [])
        if missing:
            _collect_worker({**payload, "repair_episodes": missing})
            if _STATE.get("status") != "succeeded" or _STATE.get("missing_link_episodes"):
                raise RuntimeError("补采后仍有缺失链接，已停止，未重复从第一集采集")
        needs_download = any(row.get("link") and not row.get("verified")
                             for row in (_STATE.get("episodes") or {}).values())
        if not (resuming and resume_phase == "verify-download" and not needs_download):
            _download_worker(payload)
        # 即使本轮失败，也必须先按失败类型决定恢复，不能提前 return 挡住补采。
        repairs = list(_STATE.get("parse_failed_episodes") or [])
        if repairs and not _cancelled():
            _append_log("只补采集数不一致或未确认的链接：" + "、".join(map(str, repairs)))
            _collect_worker({"repair_episodes": repairs})
            if _STATE.get("status") == "succeeded":
                _download_worker({"episodes": repairs})
        if _cancelled():
            _mark_stopped()
            return
        if int(payload.get("count") or 0):
            planned = list(_STATE.get("planned_download_episodes") or [])
            _set(status="running", phase="verify-download", current_step="正在检查本次少量验证的视频")
            _check_files(final=True)
            success = all((_STATE.get("episodes") or {}).get(str(n), {}).get("verified") for n in planned)
            _set(status="succeeded" if success else "failed", phase="completed" if success else "verify-download",
                 current_step="本次指定数量检查结束，整剧任务保留" if success else "本次视频未全部通过检查，任务保留",
                 complete=False, stage_states={**(_STATE.get("stage_states") or {}), "verify-download": "done" if success else "failed"})
            return
        failed = sorted(int(n) for n, row in (_STATE.get("episodes") or {}).items()
            if 0 < int(n) <= int(_STATE.get("expected_count") or 0) and row.get("link") and not row.get("verified"))
        if failed or _STATE.get("status") != "succeeded":
            _set(status="failed", complete=False, current_step="第" + "、".join(map(str, failed)) + "集尚未完成，已保留本剧任务和成功视频", error="仍有未完成集数，已保留本剧任务和成功视频")
            return
        _verify_worker()
        if not _STATE.get("complete") or _STATE.get("status") != "succeeded":
            return
        _delete_worker()
        if _STATE.get("status") != "succeeded":
            return
        processed += 1
        completed.append({"task_label":task.get("task_label"), "chat_name":task.get("chat_name"), "drama_name": task.get("drama_name"), "verified_count": _STATE.get("verified_count"), "download_root": _STATE.get("download_root")})
        _set(completed_tasks=completed, completed_task_count=processed)
        previous_label = label
        _finish_worker()


def _start(phase: str, target, payload: dict[str, Any] | None = None, *, preserve_progress: bool = False) -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD and _THREAD.is_alive():
            raise ValueError("已有下载步骤正在执行")
        _CANCEL_EVENT.clear()
        existing_task = dict(_STATE.get("task") or {})
        cleanup_pending = bool(_STATE.get("cleanup_pending"))
        cleanup_card_removed = bool(_STATE.get("cleanup_card_removed"))
        visible_tasks = list(_STATE.get("tasks") or [])
        current_task_index = _STATE.get("current_task_index")
        if preserve_progress:
            _STATE.update(status="queued", phase=phase, current_step="准备从中断阶段继续", error="", stop_requested=False, updated_at=_now())
        else:
            _STATE.clear()
            _STATE.update({"status": "queued", "phase": phase, "current_step": "等待执行", "logs": [], "stage_logs": {}, "created_at": _now(), "updated_at": _now()})
        if existing_task:
            _STATE["task"] = existing_task
        _STATE["cleanup_pending"] = cleanup_pending
        _STATE["cleanup_card_removed"] = cleanup_card_removed
        if cleanup_pending:
            _STATE.update(tasks=visible_tasks, task_count=len(visible_tasks), current_task_index=current_task_index)
        _save()
        def guarded():
            try:
                target(payload or {})
            except Exception as exc:
                if _cancelled():
                    _mark_stopped()
                else:
                    message = str(exc) or type(exc).__name__
                    _append_log(f"当前步骤停止：{message}；已保留已完成成果")
                    _set(status="failed", current_step=message, error=message, complete=bool(_STATE.get("complete")) if _STATE.get("phase") == "cleanup-task" else False)
            finally:
                if _cancelled():
                    _mark_stopped()
                elif _STATE.get("status") in {"running", "queued"}:
                    _set(status="failed", current_step="执行已结束但没有确认完成，请查看当前阶段记录", error="当前步骤未确认完成", complete=False)
        _THREAD = threading.Thread(target=guarded, daemon=True)
        _THREAD.start()
        return dict(_STATE)


def stop_pipeline() -> dict[str, Any]:
    """Request cancellation and terminate the currently running child script."""
    global _ACTIVE_PROCESS
    with _LOCK:
        if not (_THREAD and _THREAD.is_alive()):
            raise ValueError("当前没有正在执行的下载任务")
        _CANCEL_EVENT.set()
        process = _ACTIVE_PROCESS
        _STATE["stop_requested"] = True
        _STATE["current_step"] = "正在停止当前脚本"
        _STATE["updated_at"] = _now()
        _save()
    _append_log("已收到停止请求，正在终止当前脚本")
    if process is not None and process.poll() is None:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.kill()
        else:
            process.terminate()
    return status()


def start_read_task() -> dict[str, Any]:
    return _start("read-task", lambda _payload: _read_worker())


def start_collect_links(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    status()
    task = dict(_STATE.get("task") or {})
    if not task.get("drama_name"):
        raise ValueError("请先读取置顶任务")
    return _start("collect-links", _collect_worker, payload)


def start_pipeline(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    status()
    resume_phase = _resumable_phase(_STATE)
    options = {**(payload or {}), "_resume_phase": resume_phase}
    return _start(resume_phase or "read-task", _pipeline_worker, options, preserve_progress=bool(resume_phase))
