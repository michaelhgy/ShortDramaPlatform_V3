"""Minimal V2 production-file service for the first migration step.

This service owns V2 paths and metadata. It never imports or mutates V1.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
import base64
import ctypes
import threading
import shutil
import subprocess
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
BGM_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
HOST = os.environ.get("V2_FILE_SERVICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("V2_FILE_SERVICE_PORT", "8782"))
STANDARD_SYSTEM_ROOT_NAME = "短剧推广运营系统"


def _bootstrap_settings_path() -> Path:
    """Local machine bootstrap only; business data is never stored here."""
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    base = Path(local).expanduser() if local else Path.home() / ".short-drama-platform-v2"
    return base / "ShortDramaPlatformV2" / "bootstrap-settings.json"


def normalize_data_drive(value: object) -> str:
    """Return a Windows drive in the persisted form, e.g. ``D:``."""
    drive = str(value or "").strip().rstrip("\\/")
    if not re.fullmatch(r"[A-Za-z]:", drive):
        raise ValueError("数据盘必须是当前电脑上的盘符，例如 D:")
    return drive.upper()


def system_root_from_drive(data_drive: object) -> Path:
    return Path(f"{normalize_data_drive(data_drive)}\\") / STANDARD_SYSTEM_ROOT_NAME


def _development_workspace_override() -> Path | None:
    override = os.environ.get("V2_WORKSPACE_ROOT", "").strip()  # development/test override
    return Path(override).expanduser() if override else None


def _configured_data_drive() -> str | None:
    """Read the machine bootstrap setting and migrate the short-lived root format."""
    try:
        bootstrap = _bootstrap_settings_path()
        payload = json.loads(bootstrap.read_text(encoding="utf-8"))
        value = payload.get("data_drive", "")
        if str(value).strip():
            return normalize_data_drive(value)

        # Compatibility with the regression build: it persisted the derived
        # root instead of the user's drive. Accept only the standard shape and
        # immediately restore the proper persisted representation.
        legacy_root = Path(str(payload.get("system_root_dir", "")).strip())
        legacy_drive = legacy_root.drive
        if legacy_drive and legacy_root == system_root_from_drive(legacy_drive):
            data_drive = normalize_data_drive(legacy_drive)
            bootstrap.parent.mkdir(parents=True, exist_ok=True)
            bootstrap.write_text(json.dumps({"data_drive": data_drive}, ensure_ascii=False), encoding="utf-8")
            return data_drive
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return None


def _configured_workspace() -> Path | None:
    override = _development_workspace_override()
    if override is not None:
        return override
    data_drive = _configured_data_drive()
    return system_root_from_drive(data_drive) if data_drive else None


WORKSPACE = _configured_workspace()
DATA_ROOT = WORKSPACE / "系统数据" if WORKSPACE is not None else None
ROOT_DIRECTORIES = ("生产文件", "内容资产", "生成资源", "剧集资料", "系统数据")
TEMPLATE_JOB_LOCK = threading.Lock()
SCAN_LOCK = threading.Lock()


def require_configured_paths() -> tuple[Path, Path]:
    if WORKSPACE is None or DATA_ROOT is None:
        raise RuntimeError("需要配置数据盘")
    return WORKSPACE.resolve(), DATA_ROOT.resolve()


def ensure_v2_root_layout() -> tuple[Path, Path]:
    workspace, data_root = require_configured_paths()
    for directory_name in ROOT_DIRECTORIES:
        (workspace / directory_name).mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    return workspace, data_root


def db_path() -> Path:
    _, data_root = ensure_v2_root_layout()
    return data_root / "database" / "v2_system.db"


def connection() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS production_tasks (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL UNIQUE,
            created_date TEXT NOT NULL,
            account_name TEXT NOT NULL,
            drama_name TEXT NOT NULL,
            root_path TEXT NOT NULL,
            material_path TEXT NOT NULL,
            template_path TEXT NOT NULL,
            final_path TEXT NOT NULL,
            planned_publish_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'materials_pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS production_files (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES production_tasks(id) ON DELETE CASCADE,
            file_type TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            md5 TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            sequence_no INTEGER,
            status TEXT NOT NULL DEFAULT 'available',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            duration_seconds REAL NOT NULL DEFAULT 0,
            thumbnail_path TEXT NOT NULL DEFAULT '',
            UNIQUE(task_id, file_path)
        );
        CREATE TABLE IF NOT EXISTS production_video_tasks (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES production_tasks(id) ON DELETE CASCADE,
            source_material_id TEXT NOT NULL REFERENCES production_files(id),
            status TEXT NOT NULL DEFAULT 'pending_generation',
            draft_path TEXT NOT NULL DEFAULT '',
            output_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(task_id, source_material_id)
        );
        CREATE TABLE IF NOT EXISTS template_jobs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES production_tasks(id) ON DELETE CASCADE,
            version_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            draft_name TEXT NOT NULL,
            draft_path TEXT NOT NULL DEFAULT '',
            video_path TEXT NOT NULL DEFAULT '',
            pairing_path TEXT NOT NULL DEFAULT '',
            report_path TEXT NOT NULL DEFAULT '',
            log_path TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            seed INTEGER NOT NULL,
            reserved_videos_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(task_id, version_no)
        );
        CREATE TABLE IF NOT EXISTS theaters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            default_commission_rate REAL NOT NULL DEFAULT 0,
            default_tax_rate REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '启用',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            nickname TEXT NOT NULL UNIQUE,
            channel_id TEXT NOT NULL DEFAULT '',
            theater_id TEXT NOT NULL REFERENCES theaters(id),
            sub_theater_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '正常',
            reporting_date TEXT NOT NULL DEFAULT '',
            registration_date TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sub_theaters (
            id TEXT PRIMARY KEY,
            theater_id TEXT NOT NULL REFERENCES theaters(id),
            name TEXT NOT NULL UNIQUE,
            commission_rate REAL NOT NULL,
            is_commission_overridden INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '启用',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dramas (
            id TEXT PRIMARY KEY,
            current_name TEXT NOT NULL UNIQUE,
            theater_id TEXT NOT NULL REFERENCES theaters(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS drama_aliases (
            id TEXT PRIMARY KEY,
            drama_id TEXT NOT NULL REFERENCES dramas(id) ON DELETE CASCADE,
            alias_name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS drama_profiles (
            id TEXT PRIMARY KEY,
            drama_id TEXT NOT NULL UNIQUE REFERENCES dramas(id) ON DELETE CASCADE,
            root_path TEXT NOT NULL,
            master_path TEXT NOT NULL,
            cover_path TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v2_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS export_jobs (
            id TEXT PRIMARY KEY,
            production_task_id TEXT NOT NULL REFERENCES production_tasks(id) ON DELETE CASCADE,
            subject_type TEXT NOT NULL CHECK(subject_type IN ('template', 'final')),
            subject_id TEXT NOT NULL,
            draft_name TEXT NOT NULL,
            draft_path TEXT NOT NULL,
            target_path TEXT NOT NULL,
            manual_check_required INTEGER NOT NULL DEFAULT 0 CHECK(manual_check_required IN (0, 1)),
            status TEXT NOT NULL CHECK(status IN ('ready', 'queued', 'active', 'completed', 'failed')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS export_attempts (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES export_jobs(id) ON DELETE CASCADE,
            attempt_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            deadline_at TEXT NOT NULL DEFAULT '',
            source_output_path TEXT NOT NULL DEFAULT '',
            source_baseline_json TEXT NOT NULL DEFAULT '{}',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            debug_enabled INTEGER NOT NULL DEFAULT 0 CHECK(debug_enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(job_id, attempt_no)
        );
        CREATE TABLE IF NOT EXISTS export_events (
            id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL REFERENCES export_attempts(id) ON DELETE CASCADE,
            sequence_no INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            phase TEXT NOT NULL,
            message TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(attempt_id, sequence_no)
        );
        CREATE TABLE IF NOT EXISTS executor_controls (
            executor_id TEXT PRIMARY KEY,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            is_paused INTEGER NOT NULL DEFAULT 0 CHECK(is_paused IN (0, 1)),
            updated_at TEXT NOT NULL
        );
        """
    )
    task_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_tasks)")}
    if "planned_publish_at" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN planned_publish_at TEXT NOT NULL DEFAULT ''")
    file_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_files)")}
    if "duration_seconds" not in file_columns:
        conn.execute("ALTER TABLE production_files ADD COLUMN duration_seconds REAL NOT NULL DEFAULT 0")
    if "thumbnail_path" not in file_columns:
        conn.execute("ALTER TABLE production_files ADD COLUMN thumbnail_path TEXT NOT NULL DEFAULT ''")
    stamp = now_text()
    conn.execute(
        "INSERT OR IGNORE INTO production_video_tasks "
        "(id, task_id, source_material_id, status, draft_path, output_path, created_at, updated_at) "
        "SELECT lower(hex(randomblob(16))), task_id, id, 'pending_generation', '', '', ?, ? "
        "FROM production_files WHERE file_type='original_material' AND status='available'",
        (stamp, stamp),
    )
    conn.commit()
    return conn


def safe_component(value: str, label: str) -> str:
    cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", value).strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"{label}不能为空")
    return cleaned


def parse_created_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("生产任务创建日期必须是 YYYY-MM-DD") from exc


def parse_planned_publish_at(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M").strftime("%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise ValueError("计划发布时间必须是有效的日期和时间") from exc


def task_created_date() -> str:
    """Return the date on which V2 first creates the production task.

    This is deliberately owned by the file service: a V1 plan's make or
    publish date is not the V2 production task creation date.
    """
    return date.today().isoformat()


def task_paths(created_date: str, account_name: str, drama_name: str) -> tuple[Path, Path, Path, Path]:
    workspace, _ = require_configured_paths()
    display_date = f"{int(created_date[5:7])}月{int(created_date[8:10])}日"
    root = workspace / "生产文件" / display_date / account_name / drama_name
    return root, root / "素材", root / "模板", root / "成片"


def now_text() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def natural_key(name: str) -> list[object]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", name)]


def content_hash(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_material(path: Path, cache_key: str) -> tuple[float, str]:
    """Read duration once and cache a small first-frame thumbnail when FFmpeg is available."""
    duration = 0.0
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False,
            )
            duration = max(0.0, float((result.stdout or "").strip() or 0))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            duration = 0.0
    thumbnail = DATA_ROOT / "cache" / "material-thumbnails" / f"{cache_key}.jpg"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and not thumbnail.is_file():
        try:
            thumbnail.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [ffmpeg, "-y", "-ss", "00:00:01", "-i", str(path), "-frames:v", "1", "-vf", "scale=180:-2", str(thumbnail)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            thumbnail.unlink(missing_ok=True)
    return duration, str(thumbnail) if thumbnail.is_file() else ""


def format_media_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    return f"{total // 60:02d}:{total % 60:02d}" if total else "—"


def canonical_sequence(path: Path, drama_name: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(drama_name)}-(\d+)", path.stem, flags=re.IGNORECASE)
    return int(match.group(1)) if match and int(match.group(1)) > 0 else None


def rename_without_overwrite(directory: Path, files: list[Path], drama_name: str) -> list[Path]:
    used = {n for path in files if (n := canonical_sequence(path, drama_name)) is not None}
    assignments: list[tuple[Path, Path]] = []
    next_number = max(used, default=0) + 1
    for path in files:
        number = canonical_sequence(path, drama_name)
        if number is None:
            while next_number in used:
                next_number += 1
            number, next_number = next_number, next_number + 1
            used.add(number)
        assignments.append((path, directory / f"{drama_name}-{number}{path.suffix.lower()}"))
    originals = {path.resolve() for path in files}
    if any(target.exists() and target.resolve() not in originals for _, target in assignments):
        raise ValueError("自动重命名会覆盖已有文件，已停止")
    staged: list[tuple[Path, Path, Path]] = []
    try:
        for source, target in assignments:
            if source.resolve() == target.resolve():
                continue
            temporary = directory / f".__v2_renaming__{uuid.uuid4().hex}{source.suffix.lower()}"
            source.rename(temporary)
            staged.append((source, temporary, target))
        for _, temporary, target in staged:
            temporary.rename(target)
    except OSError as exc:
        for original, temporary, target in reversed(staged):
            current = temporary if temporary.exists() else target
            if current.exists():
                current.rename(original)
        raise RuntimeError(f"自动重命名失败，已尝试回滚：{exc}") from exc
    return [target for _, target in assignments]


def task_response(task: sqlite3.Row) -> dict[str, object]:
    return {
        "id": str(task["id"]),
        "source_id": str(task["source_id"]),
        "created_date": str(task["created_date"]),
        "account_name": str(task["account_name"]),
        "drama_name": str(task["drama_name"]),
        "planned_publish_at": str(task["planned_publish_at"]),
        "paths": {
            "root": str(task["root_path"]), "materials": str(task["material_path"]),
            "template": str(task["template_path"]), "finals": str(task["final_path"]),
        },
    }


def list_theaters() -> dict[str, object]:
    conn = connection()
    try:
        rows = conn.execute(
            "SELECT t.*, "
            "(SELECT COUNT(*) FROM accounts a WHERE a.theater_id=t.id) AS accounts_count, "
            "(SELECT COUNT(*) FROM sub_theaters s WHERE s.theater_id=t.id) AS sub_theaters_count "
            ",(SELECT COUNT(*) FROM dramas d WHERE d.theater_id=t.id) AS dramas_count "
            "FROM theaters t "
            "ORDER BY CASE t.status WHEN '启用' THEN 0 ELSE 1 END, t.name COLLATE NOCASE"
        ).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


def list_accounts() -> dict[str, object]:
    conn = connection()
    try:
        rows = conn.execute(
            "SELECT a.*, t.name AS theater_name FROM accounts a "
            "JOIN theaters t ON t.id=a.theater_id "
            "ORDER BY CASE a.status "
            "WHEN '正常' THEN 0 WHEN '观察' THEN 1 WHEN '限流' THEN 2 "
            "WHEN '二限' THEN 3 WHEN '实名' THEN 4 WHEN '封禁' THEN 5 "
            "WHEN '停用' THEN 6 ELSE 99 END, a.created_at DESC"
        ).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


def list_sub_theaters() -> dict[str, object]:
    conn = connection()
    try:
        rows = conn.execute(
            "SELECT s.*, t.name AS theater_name, "
            "(SELECT COUNT(*) FROM accounts a WHERE a.sub_theater_name=s.name AND a.theater_id=s.theater_id) AS bound_accounts_count "
            "FROM sub_theaters s "
            "JOIN theaters t ON t.id=s.theater_id "
            "ORDER BY CASE s.status WHEN '启用' THEN 0 ELSE 1 END, s.name COLLATE NOCASE"
        ).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


def list_dramas() -> dict[str, object]:
    conn = connection()
    try:
        rows = conn.execute("SELECT d.*, t.name AS theater_name FROM dramas d JOIN theaters t ON t.id=d.theater_id ORDER BY d.current_name COLLATE NOCASE").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["history_names"] = [str(value[0]) for value in conn.execute("SELECT alias_name FROM drama_aliases WHERE drama_id=? ORDER BY created_at", (row["id"],)).fetchall()]
            items.append(item)
        return {"items": items}
    finally:
        conn.close()


def drama_name_used(conn: sqlite3.Connection, name: str, drama_id: str | None = None) -> bool:
    current = conn.execute("SELECT 1 FROM dramas WHERE current_name=? AND (? IS NULL OR id<>?)", (name, drama_id, drama_id)).fetchone()
    alias = conn.execute("SELECT 1 FROM drama_aliases WHERE alias_name=? AND (? IS NULL OR drama_id<>?)", (name, drama_id, drama_id)).fetchone()
    return bool(current or alias)


def create_drama(payload: dict[str, object]) -> dict[str, object]:
    name = safe_component(str(payload.get("current_name") or ""), "剧名")
    theater_id = str(payload.get("theater_id") or "")
    histories = [safe_component(str(value), "历史剧名") for value in (payload.get("history_names") or []) if str(value).strip()]
    conn = connection()
    try:
        theater = conn.execute("SELECT name, status FROM theaters WHERE id=?", (theater_id,)).fetchone()
        if not theater: raise ValueError("所属剧场不存在")
        if theater["status"] != "启用": raise ValueError("停用剧场不能新增剧集")
        if drama_name_used(conn, name) or any(drama_name_used(conn, value) or value == name for value in histories):
            raise ValueError("当前剧名或历史剧名已被其他剧集使用")
        stamp = now_text(); item = {"id": uuid.uuid4().hex, "current_name": name, "theater_id": theater_id, "theater_name": str(theater["name"]), "created_at": stamp, "updated_at": stamp, "history_names": histories}
        conn.execute("INSERT INTO dramas(id,current_name,theater_id,created_at,updated_at) VALUES (?,?,?,?,?)", (item["id"], name, theater_id, stamp, stamp))
        for alias in histories: conn.execute("INSERT INTO drama_aliases(id,drama_id,alias_name,created_at) VALUES (?,?,?,?)", (uuid.uuid4().hex, item["id"], alias, stamp))
        conn.commit(); return item
    except sqlite3.IntegrityError as exc:
        raise ValueError("剧名或历史剧名已存在") from exc
    finally: conn.close()


def create_dramas_batch(payload: dict[str, object]) -> dict[str, object]:
    created, skipped = [], []
    for raw in payload.get("items", []):
        try: created.append(create_drama(raw))
        except ValueError as exc:
            if "已被其他剧集使用" in str(exc) or "已存在" in str(exc): skipped.append(str(raw.get("current_name") or ""))
            else: raise
    return {"items": created, "created_count": len(created), "skipped_names": skipped}


def upload_drama_cover(drama_id: str, payload: dict[str, object]) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT current_name FROM dramas WHERE id=?", (drama_id,)).fetchone()
        if not row:
            raise ValueError("剧集不存在")
        filename = Path(str(payload.get("filename") or "")).name
        extension = Path(filename).suffix.lower()
        if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            raise ValueError("封面只支持 JPG、PNG、WEBP 或 GIF 图片")
        encoded = str(payload.get("content_base64") or "")
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        data = base64.b64decode(encoded, validate=True)
        cover_dir = WORKSPACE / "剧集资料" / str(row["current_name"]) / "封面"
        cover_dir.mkdir(parents=True, exist_ok=True)
        target = cover_dir / f"{row['current_name']}-封面{extension}"
        target.write_bytes(data)
        conn.execute("UPDATE drama_profiles SET cover_path=?, updated_at=? WHERE drama_id=?", (str(target), now_text(), drama_id))
        conn.commit()
        return {"drama_id": drama_id, "file_path": str(target), "filename": target.name}
    finally:
        conn.close()


def create_drama_profile(drama_id: str) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT current_name FROM dramas WHERE id=?", (drama_id,)).fetchone()
        if not row:
            raise ValueError("剧集不存在")
        root = WORKSPACE / "剧集资料" / str(row["current_name"])
        (root / "原片").mkdir(parents=True, exist_ok=True)
        (root / "封面").mkdir(parents=True, exist_ok=True)
        stamp = now_text()
        conn.execute("INSERT OR REPLACE INTO drama_profiles(id,drama_id,root_path,master_path,cover_path,updated_at) VALUES (?,?,?,?,?,?)", (uuid.uuid4().hex, drama_id, str(root), str(root / "原片"), "", stamp))
        conn.commit()
        return {"drama_id": drama_id, "folder_path": str(root), "master_folder_path": str(root / "原片"), "cover_folder_path": str(root / "封面"), "cover_path": ""}
    finally:
        conn.close()


def list_drama_profiles() -> dict[str, object]:
    conn = connection()
    try:
        return {"items": [dict(row) for row in conn.execute("SELECT * FROM drama_profiles").fetchall()]}
    finally:
        conn.close()


def list_production_resources() -> dict[str, object]:
    roots = (("真人视频", "real_video", "真人视频", VIDEO_EXTENSIONS), ("真人图片", "real_image", "真人图片", IMAGE_EXTENSIONS), ("BGM", "bgm", "BGM", BGM_EXTENSIONS))
    items: list[dict[str, object]] = []
    for folder, category, category_name, extensions in roots:
        root = WORKSPACE / "生成资源" / folder
        root.mkdir(parents=True, exist_ok=True)
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            stat = path.stat()
            items.append({"id": hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:24], "name": path.name, "category": category, "categoryName": category_name, "filePath": str(path), "fileSizeMb": round(stat.st_size / 1024 / 1024, 2), "status": "used" if path.name.startswith("已使用") else "available", "addedAt": date.fromtimestamp(stat.st_mtime).isoformat(), "tags": []})
    return {"items": items}


DEFAULT_SETTINGS = {
    "data_drive": "",
    "data_root_dir": "",
    "raw_material_retention_days": 7,
    "short_term_cleanup_hours": 24,
    "publish_presets": ["12:00", "18:30", "19:45", "21:00"],
    "publish_date_offset_days": 0,
    "jianying_executable": "",
    "jianying_draft_root": "",
    "template_timeout_min": 15,
    "video_export_timeout_min": 20,
    "final_video_manual_check": False,
    "video_export_debug": False,
}


def list_windows_drives() -> list[str]:
    mask = ctypes.windll.kernel32.GetLogicalDrives() if os.name == "nt" else 0
    return [f"{chr(65 + index)}:\\" for index in range(26) if mask & (1 << index)]


def get_v2_settings() -> dict[str, object]:
    configured_drive = _configured_data_drive()
    result = dict(DEFAULT_SETTINGS)
    result["data_drive"] = configured_drive or ""
    result["data_root_dir"] = str(WORKSPACE) if WORKSPACE is not None else ""
    if WORKSPACE is None:
        return result
    conn = connection()
    try:
        for row in conn.execute("SELECT key, value_json FROM v2_settings").fetchall():
            key = str(row["key"])
            # The system root is derived from the bootstrap data drive. Never
            # let an older database row turn it back into a user-editable path.
            if key not in {"data_drive", "data_root_dir"}:
                result[key] = json.loads(str(row["value_json"]))
        return result
    finally:
        conn.close()


def update_v2_settings(payload: dict[str, object]) -> dict[str, object]:
    global WORKSPACE, DATA_ROOT
    # data_root_dir is a derived display value. Accept the immediately
    # preceding API shape only when it is the standard root for its drive.
    payload = dict(payload)
    legacy_root = payload.pop("data_root_dir", None)
    if legacy_root is not None and "data_drive" not in payload:
        legacy_path = Path(str(legacy_root or "").strip())
        if legacy_path.drive and legacy_path == system_root_from_drive(legacy_path.drive):
            payload["data_drive"] = normalize_data_drive(legacy_path.drive)
        else:
            raise ValueError("系统根目录由数据盘自动生成，不能手工设置")
    allowed = set(DEFAULT_SETTINGS) - {"data_root_dir"}
    invalid = set(payload) - allowed
    if invalid:
        raise ValueError("包含不支持的系统设置")
    values = dict(DEFAULT_SETTINGS)
    values.update(get_v2_settings())
    if "data_drive" in payload:
        payload["data_drive"] = normalize_data_drive(payload["data_drive"])
    values.update(payload)
    if WORKSPACE is None and not str(values["data_drive"] or "").strip():
        raise ValueError("需要配置数据盘")
    if not isinstance(values["raw_material_retention_days"], int) or not 1 <= values["raw_material_retention_days"] <= 90:
        raise ValueError("原素材保留时间必须为 1-90 天")
    if not isinstance(values["short_term_cleanup_hours"], int) or not 1 <= values["short_term_cleanup_hours"] <= 168:
        raise ValueError("短期清理时间必须为 1-168 小时")
    if not isinstance(values["publish_presets"], list) or not all(isinstance(item, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in values["publish_presets"]):
        raise ValueError("发布时间预设格式不正确")
    if not isinstance(values["publish_date_offset_days"], int) or values["publish_date_offset_days"] < 0:
        raise ValueError("发布日期偏移必须是 0 或更大的整数天数")
    for key in ("jianying_executable", "jianying_draft_root"):
        if not isinstance(values[key], str):
            raise ValueError("剪映路径设置格式不正确")
    executable = str(values["jianying_executable"]).strip()
    draft_root = str(values["jianying_draft_root"]).strip()
    if executable and (not Path(executable).is_file() or Path(executable).suffix.lower() != ".exe"):
        raise ValueError("剪映程序路径必须是存在的 .exe 文件")
    if draft_root and not Path(draft_root).is_dir():
        raise ValueError("剪映草稿目录必须是存在的文件夹")
    if not isinstance(values["template_timeout_min"], int) or not 1 <= values["template_timeout_min"] <= 120:
        raise ValueError("模板生成超时时间必须为 1-120 分钟")
    if not isinstance(values["video_export_timeout_min"], int) or not 1 <= values["video_export_timeout_min"] <= 120:
        raise ValueError("视频导出超时时间必须为 1-120 分钟")
    for key in ("final_video_manual_check", "video_export_debug"):
        if not isinstance(values[key], bool):
            raise ValueError("视频导出器开关必须是布尔值")
    if "data_drive" in payload:
        WORKSPACE = system_root_from_drive(payload["data_drive"])
        DATA_ROOT = WORKSPACE / "系统数据"
        bootstrap = _bootstrap_settings_path()
        bootstrap.parent.mkdir(parents=True, exist_ok=True)
        bootstrap.write_text(json.dumps({"data_drive": payload["data_drive"]}, ensure_ascii=False), encoding="utf-8")
        ensure_v2_root_layout()
    conn = connection()
    try:
        # A drive change deliberately creates/uses a different system root.
        # Copy the complete settings snapshot into that root so changing the
        # data location never clears independent Jianying or task settings.
        settings_to_persist = values if "data_drive" in payload else payload
        for key, value in settings_to_persist.items():
            if key in {"data_drive", "data_root_dir"}:
                continue
            conn.execute("INSERT INTO v2_settings(key,value_json,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at", (key, json.dumps(value, ensure_ascii=False), now_text()))
        conn.commit()
        return get_v2_settings()
    finally:
        conn.close()


def select_v2_path(kind: str) -> dict[str, str]:
    """Open a native Windows chooser for the two path settings."""
    if kind not in {"file", "directory"}:
        raise ValueError("不支持的路径选择类型")
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError as exc:
        raise RuntimeError("当前环境无法打开 Windows 路径选择器") from exc
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            if kind == "file":
                selected = filedialog.askopenfilename(title="选择剪映程序", filetypes=[("剪映程序", "*.exe"), ("所有文件", "*.*")])
            else:
                selected = filedialog.askdirectory(title="选择剪映草稿目录", mustexist=True)
        finally:
            root.destroy()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Windows 选择框打开失败：{exc}") from exc
    if not selected:
        return {"path": "", "cancelled": "true"}
    return {"path": str(Path(selected).resolve()), "cancelled": "false"}


def update_drama(drama_id: str, payload: dict[str, object]) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT * FROM dramas WHERE id=?", (drama_id,)).fetchone()
        if not row: raise ValueError("剧集不存在")
        name = safe_component(str(payload.get("current_name") or row["current_name"]), "剧名")
        histories = [safe_component(str(value), "历史剧名") for value in (payload.get("history_names") or []) if str(value).strip()]
        if len(set(histories)) != len(histories) or name in histories or drama_name_used(conn, name, drama_id) or any(drama_name_used(conn, value, drama_id) for value in histories):
            raise ValueError("当前剧名或历史剧名已被其他剧集使用")
        conn.execute("UPDATE dramas SET current_name=?, updated_at=? WHERE id=?", (name, now_text(), drama_id))
        conn.execute("DELETE FROM drama_aliases WHERE drama_id=?", (drama_id,))
        for alias in histories: conn.execute("INSERT INTO drama_aliases(id,drama_id,alias_name,created_at) VALUES (?,?,?,?)", (uuid.uuid4().hex, drama_id, alias, now_text()))
        conn.commit()
        return next(item for item in list_dramas()["items"] if item["id"] == drama_id)
    except sqlite3.IntegrityError as exc: raise ValueError("历史剧名已存在") from exc
    finally: conn.close()


def delete_drama(drama_id: str) -> None:
    conn = connection()
    try:
        if not conn.execute("SELECT 1 FROM dramas WHERE id=?", (drama_id,)).fetchone(): raise ValueError("剧集不存在")
        task_count = conn.execute("SELECT COUNT(*) FROM production_tasks WHERE drama_name=(SELECT current_name FROM dramas WHERE id=?)", (drama_id,)).fetchone()[0]
        if task_count: raise ValueError("剧集已有生产任务，不能删除")
        conn.execute("DELETE FROM dramas WHERE id=?", (drama_id,)); conn.commit()
    finally: conn.close()


def create_theater(payload: dict[str, object]) -> dict[str, object]:
    name = safe_component(str(payload.get("name") or ""), "剧场名称")
    commission = float(payload.get("default_commission_rate") or 0)
    tax = float(payload.get("default_tax_rate") or 0)
    status = str(payload.get("status") or "启用")
    if not 0 <= commission <= 100 or not 0 <= tax <= 100 or status not in {"启用", "停用"}:
        raise ValueError("剧场分成、税率须在 0 到 100 之间，状态须为启用或停用")
    item = {"id": uuid.uuid4().hex, "name": name, "default_commission_rate": commission,
            "default_tax_rate": tax, "status": status, "created_at": now_text(), "updated_at": now_text()}
    conn = connection()
    try:
        conn.execute("INSERT INTO theaters VALUES (:id,:name,:default_commission_rate,:default_tax_rate,:status,:created_at,:updated_at)", item)
        conn.commit()
        return item
    except sqlite3.IntegrityError as exc:
        raise ValueError("剧场名称已存在") from exc
    finally:
        conn.close()


def create_theaters_batch(payload: dict[str, object]) -> dict[str, object]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("请至少提供一个剧场")
    prepared: list[dict[str, object]] = []
    names: set[str] = set()
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 行剧场格式不正确")
        name = safe_component(str(raw.get("name") or ""), f"第 {index} 行剧场名称")
        if name in names:
            continue
        names.add(name)
        commission = float(raw.get("default_commission_rate") or 0)
        tax = float(raw.get("default_tax_rate") or 0)
        status = str(raw.get("status") or "启用")
        if not 0 <= commission <= 100 or not 0 <= tax <= 100 or status not in {"启用", "停用"}:
            raise ValueError(f"第 {index} 行剧场的分成、税率或状态不正确")
        stamp = now_text()
        prepared.append({"id": uuid.uuid4().hex, "name": name, "default_commission_rate": commission,
                         "default_tax_rate": tax, "status": status, "created_at": stamp, "updated_at": stamp})
    conn = connection()
    try:
        existing = {str(row[0]) for row in conn.execute(
            f"SELECT name FROM theaters WHERE name IN ({','.join('?' for _ in prepared)})", tuple(item["name"] for item in prepared)
        ).fetchall()}
        new_items = [item for item in prepared if str(item["name"]) not in existing]
        if new_items:
            conn.executemany(
                "INSERT INTO theaters VALUES (:id,:name,:default_commission_rate,:default_tax_rate,:status,:created_at,:updated_at)", new_items
            )
        conn.commit()
        return {"items": new_items, "created_count": len(new_items), "skipped_names": sorted(existing)}
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("剧场导入失败，未写入任何数据") from exc
    finally:
        conn.close()


def update_theater(theater_id: str, payload: dict[str, object]) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT * FROM theaters WHERE id=?", (theater_id,)).fetchone()
        if not row:
            raise ValueError("剧场不存在")
        name = safe_component(str(payload.get("name", row["name"])), "剧场名称")
        commission = float(payload.get("default_commission_rate", row["default_commission_rate"]))
        tax = float(payload.get("default_tax_rate", row["default_tax_rate"]))
        status = str(payload.get("status", row["status"]))
        if not 0 <= commission <= 100 or not 0 <= tax <= 100 or status not in {"启用", "停用"}:
            raise ValueError("剧场分成、税率须在 0 到 100 之间，状态须为启用或停用")
        conn.execute(
            "UPDATE theaters SET name=?, default_commission_rate=?, default_tax_rate=?, status=?, updated_at=? WHERE id=?",
            (name, commission, tax, status, now_text(), theater_id),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM theaters WHERE id=?", (theater_id,)).fetchone()
        return {**dict(updated), "accounts_count": conn.execute("SELECT COUNT(*) FROM accounts WHERE theater_id=?", (theater_id,)).fetchone()[0]}
    except sqlite3.IntegrityError as exc:
        raise ValueError("剧场名称已存在") from exc
    finally:
        conn.close()


def delete_theater(theater_id: str) -> None:
    conn = connection()
    try:
        row = conn.execute("SELECT name FROM theaters WHERE id=?", (theater_id,)).fetchone()
        if not row:
            raise ValueError("剧场不存在")
        account_count = conn.execute("SELECT COUNT(*) FROM accounts WHERE theater_id=?", (theater_id,)).fetchone()[0]
        sub_theater_count = conn.execute("SELECT COUNT(*) FROM sub_theaters WHERE theater_id=?", (theater_id,)).fetchone()[0]
        if sub_theater_count:
            raise ValueError(f"剧场“{row['name']}”已有 {sub_theater_count} 个子剧场，不能删除。请先处理子剧场。")
        if account_count:
            raise ValueError(f"剧场“{row['name']}”已关联 {account_count} 个账号，不能删除。请先处理关联账号。")
        conn.execute("DELETE FROM theaters WHERE id=?", (theater_id,))
        conn.commit()
    finally:
        conn.close()


def create_sub_theater(payload: dict[str, object]) -> dict[str, object]:
    theater_id = str(payload.get("theater_id") or "").strip()
    name = safe_component(str(payload.get("name") or ""), "子剧场名称")
    commission = float(payload.get("commission_rate") or 0)
    overridden = 1 if bool(payload.get("is_commission_overridden")) else 0
    status = str(payload.get("status") or "启用")
    if not theater_id or not 0 <= commission <= 100 or status not in {"启用", "停用"}:
        raise ValueError("子剧场所属剧场、分成或状态不正确")
    conn = connection()
    try:
        theater = conn.execute("SELECT name, status FROM theaters WHERE id=?", (theater_id,)).fetchone()
        if not theater:
            raise ValueError("所属剧场不存在")
        if theater["status"] != "启用":
            raise ValueError("停用剧场不能新增子剧场")
        stamp = now_text()
        item = {"id": uuid.uuid4().hex, "theater_id": theater_id, "name": name, "commission_rate": commission,
                "is_commission_overridden": overridden, "status": status, "created_at": stamp, "updated_at": stamp,
                "theater_name": str(theater["name"]), "bound_accounts_count": 0}
        conn.execute(
            "INSERT INTO sub_theaters(id,theater_id,name,commission_rate,is_commission_overridden,status,created_at,updated_at) "
            "VALUES (:id,:theater_id,:name,:commission_rate,:is_commission_overridden,:status,:created_at,:updated_at)", item
        )
        conn.commit()
        return item
    except sqlite3.IntegrityError as exc:
        raise ValueError("子剧场名称已存在，不能重复创建") from exc
    finally:
        conn.close()


def create_sub_theaters_batch(payload: dict[str, object]) -> dict[str, object]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("请至少提供一个子剧场")
    created: list[dict[str, object]] = []
    skipped: list[str] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("子剧场导入格式不正确")
        try:
            created.append(create_sub_theater(raw))
        except ValueError as exc:
            if "已存在" in str(exc):
                skipped.append(str(raw.get("name") or ""))
            else:
                raise
    return {"items": created, "created_count": len(created), "skipped_names": skipped}


def update_sub_theater(sub_id: str, payload: dict[str, object]) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT s.*, t.name AS theater_name FROM sub_theaters s JOIN theaters t ON t.id=s.theater_id WHERE s.id=?", (sub_id,)).fetchone()
        if not row:
            raise ValueError("子剧场不存在")
        name = safe_component(str(payload.get("name", row["name"])), "子剧场名称")
        theater_id = str(payload.get("theater_id", row["theater_id"]))
        status = str(payload.get("status", row["status"]))
        commission = float(payload.get("commission_rate", row["commission_rate"]))
        if status not in {"启用", "停用"} or not 0 <= commission <= 100:
            raise ValueError("子剧场分成或状态不正确")
        bound = conn.execute("SELECT COUNT(*) FROM accounts WHERE sub_theater_name=? AND theater_id=?", (row["name"], row["theater_id"])).fetchone()[0]
        if bound and theater_id != str(row["theater_id"]):
            raise ValueError(f"子剧场已绑定 {bound} 个账号，不能更换所属剧场")
        theater = conn.execute("SELECT name, status FROM theaters WHERE id=?", (theater_id,)).fetchone()
        if not theater:
            raise ValueError("所属剧场不存在")
        conn.execute("UPDATE sub_theaters SET theater_id=?, name=?, commission_rate=?, is_commission_overridden=?, status=?, updated_at=? WHERE id=?",
                     (theater_id, name, commission, 1 if payload.get("is_commission_overridden") else 0, status, now_text(), sub_id))
        if bound and name != str(row["name"]):
            conn.execute("UPDATE accounts SET sub_theater_name=?, updated_at=? WHERE sub_theater_name=? AND theater_id=?", (name, now_text(), row["name"], row["theater_id"]))
        conn.commit()
        updated = conn.execute("SELECT s.*, t.name AS theater_name FROM sub_theaters s JOIN theaters t ON t.id=s.theater_id WHERE s.id=?", (sub_id,)).fetchone()
        return {**dict(updated), "bound_accounts_count": conn.execute("SELECT COUNT(*) FROM accounts WHERE sub_theater_name=? AND theater_id=?", (name, theater_id)).fetchone()[0]}
    except sqlite3.IntegrityError as exc:
        raise ValueError("子剧场名称已存在，不能重复创建") from exc
    finally:
        conn.close()


def delete_sub_theater(sub_id: str) -> None:
    conn = connection()
    try:
        row = conn.execute("SELECT name, theater_id FROM sub_theaters WHERE id=?", (sub_id,)).fetchone()
        if not row:
            raise ValueError("子剧场不存在")
        bound = conn.execute("SELECT COUNT(*) FROM accounts WHERE sub_theater_name=? AND theater_id=?", (row["name"], row["theater_id"])).fetchone()[0]
        if bound:
            raise ValueError(f"子剧场“{row['name']}”已绑定 {bound} 个账号，不能删除")
        conn.execute("DELETE FROM sub_theaters WHERE id=?", (sub_id,))
        conn.commit()
    finally:
        conn.close()


def create_account(payload: dict[str, object]) -> dict[str, object]:
    nickname = safe_component(str(payload.get("nickname") or ""), "账号昵称")
    theater_id = str(payload.get("theater_id") or "").strip()
    if not theater_id:
        raise ValueError("账号必须选择所属剧场")
    status = str(payload.get("status") or "正常")
    if status not in {"正常", "观察", "限流", "二限", "实名", "封禁", "停用"}:
        raise ValueError("账号状态不正确")
    channel_id = str(payload.get("channel_id") or "").strip()
    reporting_date = str(payload.get("reporting_date") or "").strip()
    registration_date = str(payload.get("registration_date") or "").strip()
    if not channel_id:
        raise ValueError("平台iD不能为空")
    if reporting_date and reporting_date != "未报白" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reporting_date):
        raise ValueError("报白时间只能填写“未报白”或有效日期")
    if registration_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", registration_date):
        raise ValueError("注册时间必须是有效日期")
    item = {"id": uuid.uuid4().hex, "nickname": nickname, "channel_id": channel_id,
            "theater_id": theater_id, "sub_theater_name": str(payload.get("sub_theater_name") or "").strip(),
            "status": status, "reporting_date": reporting_date if reporting_date != "未报白" else "",
            "registration_date": registration_date, "notes": str(payload.get("notes") or "").strip(),
            "created_at": now_text(), "updated_at": now_text()}
    conn = connection()
    try:
        if not conn.execute("SELECT 1 FROM theaters WHERE id=?", (theater_id,)).fetchone():
            raise ValueError("所属剧场不存在")
        if conn.execute("SELECT 1 FROM accounts WHERE channel_id=?", (channel_id,)).fetchone():
            raise ValueError("平台iD已存在")
        conn.execute("INSERT INTO accounts VALUES (:id,:nickname,:channel_id,:theater_id,:sub_theater_name,:status,:reporting_date,:registration_date,:notes,:created_at,:updated_at)", item)
        conn.commit()
        return item
    except sqlite3.IntegrityError as exc:
        raise ValueError("账号昵称已存在") from exc
    finally:
        conn.close()


def create_accounts_batch(payload: dict[str, object]) -> dict[str, object]:
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("请至少提供一个账号")
    conn = connection()
    created: list[dict[str, object]] = []
    skipped: list[str] = []
    try:
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError("账号导入格式不正确")
            nickname = str(raw.get("nickname") or "").strip()
            channel_id = str(raw.get("channel_id") or "").strip()
            theater_name = str(raw.get("theater_name") or "").strip()
            theater = conn.execute("SELECT id, name, status FROM theaters WHERE name=?", (theater_name,)).fetchone()
            if not theater:
                raise ValueError(f"账号“{nickname}”所属剧场不存在")
            if theater["status"] != "启用":
                raise ValueError(f"账号“{nickname}”不能归属停用剧场")
            sub_theater_name = str(raw.get("sub_theater_name") or "").strip()
            if sub_theater_name:
                sub_theater = conn.execute(
                    "SELECT 1 FROM sub_theaters WHERE name=? AND theater_id=?",
                    (sub_theater_name, theater["id"]),
                ).fetchone()
                if not sub_theater:
                    raise ValueError(f"账号“{nickname}”所属子剧场不存在或不属于该剧场")
            duplicate = conn.execute("SELECT 1 FROM accounts WHERE nickname=? OR channel_id=?", (nickname, channel_id)).fetchone()
            if duplicate:
                skipped.append(nickname or channel_id)
                continue
            item = create_account({**raw, "theater_id": str(theater["id"])})
            item["theater_name"] = str(theater["name"])
            created.append(item)
        return {"items": created, "created_count": len(created), "skipped_names": skipped}
    finally:
        conn.close()


def update_account(account_id: str, payload: dict[str, object]) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row:
            raise ValueError("账号不存在")
        nickname = safe_component(str(payload.get("nickname", row["nickname"])), "账号昵称")
        channel_id = str(payload.get("channel_id", row["channel_id"])).strip()
        theater_id = str(payload.get("theater_id", row["theater_id"])).strip()
        status = str(payload.get("status", row["status"]))
        if not channel_id or status not in {"正常", "观察", "限流", "二限", "实名", "封禁", "停用"}:
            raise ValueError("账号资料或状态不正确")
        reporting_date = str(payload.get("reporting_date", row["reporting_date"])).strip()
        registration_date = str(payload.get("registration_date", row["registration_date"])).strip()
        if reporting_date and reporting_date != "未报白" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reporting_date):
            raise ValueError("报白时间只能填写“未报白”或有效日期")
        if registration_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", registration_date):
            raise ValueError("注册时间必须是有效日期")
        if not conn.execute("SELECT 1 FROM theaters WHERE id=?", (theater_id,)).fetchone():
            raise ValueError("所属剧场不存在")
        if conn.execute("SELECT 1 FROM accounts WHERE channel_id=? AND id<>?", (channel_id, account_id)).fetchone():
            raise ValueError("平台iD已存在")
        conn.execute("UPDATE accounts SET nickname=?, channel_id=?, theater_id=?, sub_theater_name=?, status=?, reporting_date=?, registration_date=?, notes=?, updated_at=? WHERE id=?",
                     (nickname, channel_id, theater_id, str(payload.get("sub_theater_name", row["sub_theater_name"])), status,
                      "" if reporting_date == "未报白" else reporting_date, registration_date,
                      str(payload.get("notes", row["notes"])), now_text(), account_id))
        conn.commit()
        updated = conn.execute("SELECT a.*, t.name AS theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id WHERE a.id=?", (account_id,)).fetchone()
        return dict(updated)
    except sqlite3.IntegrityError as exc:
        raise ValueError("账号昵称或账号 ID 已存在") from exc
    finally:
        conn.close()


def delete_account(account_id: str) -> None:
    conn = connection()
    try:
        row = conn.execute("SELECT nickname FROM accounts WHERE id=?", (account_id,)).fetchone()
        if not row:
            raise ValueError("账号不存在")
        task_count = conn.execute("SELECT COUNT(*) FROM production_tasks WHERE account_name=?", (row["nickname"],)).fetchone()[0]
        if task_count:
            raise ValueError(f"账号“{row['nickname']}”已有生产任务，不能删除")
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        conn.commit()
    finally:
        conn.close()


def create_task(payload: dict[str, object]) -> dict[str, object]:
    source_id = safe_component(str(payload.get("source_id") or ""), "生产任务来源")
    created_date = task_created_date()
    account = safe_component(str(payload.get("account_name") or ""), "账号")
    drama = safe_component(str(payload.get("drama_name") or ""), "剧集")
    planned_publish_at = parse_planned_publish_at(str(payload.get("planned_publish_at") or ""))
    root, materials, template, finals = task_paths(created_date, account, drama)
    for directory in (materials, template, finals):
        directory.mkdir(parents=True, exist_ok=True)
    stamp = now_text()
    task_id = uuid.uuid4().hex
    conn = connection()
    try:
        existing = conn.execute("SELECT * FROM production_tasks WHERE source_id=?", (source_id,)).fetchone()
        if existing:
            return task_response(existing)
        conn.execute(
            """
            INSERT INTO production_tasks (
                id, source_id, created_date, account_name, drama_name, root_path, material_path,
                template_path, final_path, planned_publish_at, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, source_id, created_date, account, drama, str(root), str(materials), str(template), str(finals), planned_publish_at, "materials_pending", stamp, stamp),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": task_id, "source_id": source_id, "created_date": created_date,
        "account_name": account, "drama_name": drama, "planned_publish_at": planned_publish_at,
        "paths": {"root": str(root), "materials": str(materials), "template": str(template), "finals": str(finals)},
    }


def create_export_job(payload: dict[str, object]) -> dict[str, object]:
    """Create one real V2 export job without inventing a production queue."""
    from server.v2_exporter.core import ExportRepository
    task_id = str(payload.get("production_task_id") or "").strip()
    subject_type = str(payload.get("subject_type") or "").strip()
    subject_id = str(payload.get("subject_id") or "").strip()
    draft_name = str(payload.get("draft_name") or "").strip()
    draft_path = Path(str(payload.get("draft_path") or "")).expanduser()
    if not draft_path.is_dir():
        raise ValueError("真实剪映草稿目录不存在")
    conn = connection()
    try:
        task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("生产任务不存在")
        if subject_type not in {"template", "final"}:
            raise ValueError("导出对象类型只能是 template 或 final")
        group = Path(str(task["template_path"] if subject_type == "template" else task["final_path"]))
        suffix = "模板" if subject_type == "template" else "成片"
        filename = f"{safe_component(str(task['created_date']), '日期')}-{safe_component(str(task['account_name']), '账号')}-{safe_component(str(task['drama_name']), '剧集')}-{suffix}.mp4"
        job = ExportRepository(conn).create_job(
            production_task_id=task_id, subject_type=subject_type, subject_id=subject_id or draft_name,
            draft_name=draft_name, draft_path=str(draft_path.resolve()), target_path=str((group / filename).resolve()),
            manual_check_required=bool(payload.get("manual_check_required", False)) and subject_type == "final",
        )
        return {"job": job, "target_path": job["target_path"]}
    finally:
        conn.close()


def start_export_job(job_id: str) -> dict[str, object]:
    """The testable real-entry point: queue exactly one V2 attempt and run it."""
    from server.executor_management import ExecutorManager
    from server.v2_exporter.core import ExportRepository
    from server.v2_exporter.runner import start_attempt_in_background
    conn = connection()
    try:
        control = ExecutorManager(conn).state("video_exporter")
        if bool(control["is_paused"]):
            raise ValueError("视频导出器已因连续失败暂停，请在任务中心人工重新启动")
        settings = get_v2_settings()
        attempt = ExportRepository(conn).queue_new_attempt(job_id, deadline_minutes=int(settings["video_export_timeout_min"]), debug_enabled=bool(settings["video_export_debug"]))
    finally:
        conn.close()
    start_attempt_in_background(connection, attempt_id=str(attempt["id"]), settings=settings)
    return {"attempt": attempt}


def list_tasks() -> dict[str, object]:
    conn = connection()
    try:
        items: list[dict[str, object]] = []
        for row in conn.execute("SELECT * FROM production_tasks ORDER BY created_at DESC").fetchall():
            item = task_response(row)
            material_directory = Path(str(row["material_path"]))
            scanned_paths = {
                str(Path(str(file["file_path"])).resolve())
                for file in conn.execute(
                    "SELECT file_path FROM production_files WHERE task_id=? AND file_type='original_material' AND status='available'",
                    (str(row["id"]),),
                ).fetchall()
            }
            pending_material_count = 0
            if material_directory.is_dir():
                pending_material_count = sum(
                    1
                    for file in material_directory.iterdir()
                    if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS and str(file.resolve()) not in scanned_paths
                )
            material_rows = conn.execute(
                "SELECT * FROM production_files WHERE task_id=? AND file_type='original_material' AND status='available' ORDER BY sequence_no, file_name",
                (str(row["id"]),),
            ).fetchall()
            item["materials"] = [
                {
                    "id": str(file["id"]),
                    "name": str(file["file_name"]),
                    "path": str(file["file_path"]),
                    "sequence_no": file["sequence_no"],
                    "size_bytes": int(file["size_bytes"]),
                    "duration_seconds": float(file["duration_seconds"] or 0),
                    "thumbnail_path": str(file["thumbnail_path"] or ""),
                    "scanned_at": str(file["updated_at"]),
                }
                for file in material_rows
                if Path(str(file["file_path"])).is_file()
            ]
            video_rows = conn.execute(
                "SELECT v.*, f.sequence_no, f.file_name, f.file_path, f.size_bytes "
                "FROM production_video_tasks v "
                "JOIN production_files f ON f.id=v.source_material_id "
                "WHERE v.task_id=? AND f.status='available' "
                "AND v.status NOT IN ('cancelled', 'cancellation_requested', 'invalidated') "
                "ORDER BY f.sequence_no, f.file_name",
                (str(row["id"]),),
            ).fetchall()
            item["videos"] = [
                {
                    "id": str(video["id"]),
                    "source_material_id": str(video["source_material_id"]),
                    "status": str(video["status"]),
                    "sequence_no": video["sequence_no"],
                    "name": str(video["file_name"]),
                    "size_bytes": int(video["size_bytes"]),
                    "draft_path": str(video["draft_path"]),
                    "output_path": str(video["output_path"]),
                }
                for video in video_rows
                if Path(str(video["file_path"])).is_file()
            ]
            template = conn.execute(
                "SELECT * FROM template_jobs WHERE task_id=? ORDER BY version_no DESC LIMIT 1", (str(row["id"]),)
            ).fetchone()
            if template:
                template_item = dict(template)
                video_file = Path(str(template["video_path"] or ""))
                template_item["video_size_bytes"] = video_file.stat().st_size if video_file.is_file() else 0
                template_item["draft_duration_seconds"], template_item["draft_duration_formatted"] = _template_duration(
                    str(template["started_at"] or ""), str(template["finished_at"] or "")
                )
                item["template"] = template_item
            else:
                item["template"] = None
            item["pending_material_count"] = pending_material_count
            items.append(item)
        return {"items": items}
    finally:
        conn.close()


def _template_duration(started_at: str, finished_at: str = "") -> tuple[int, str]:
    if not started_at:
        return 0, "—"
    try:
        started = datetime.fromisoformat(started_at)
        ended = datetime.fromisoformat(finished_at) if finished_at else datetime.now()
        seconds = max(0, int((ended - started).total_seconds()))
    except ValueError:
        return 0, "—"
    if seconds < 60:
        return seconds, f"{seconds:02d}秒"
    return seconds, f"{seconds // 60}分{seconds % 60:02d}秒"


def repair_empty_task_date(task_id: str, target_date: str) -> dict[str, object]:
    """Move one empty V2 task to its correct creation-date directory.

    This narrow repair is safe only before any production file is recorded and
    while all three task directories are empty. It exists to correct tasks
    created by the initial migration version that mistakenly used V1 plan dates.
    """
    repaired_date = parse_created_date(target_date)
    workspace, _ = require_configured_paths()
    production_root = (workspace / "生产文件").resolve()
    conn = connection()
    try:
        task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("生产任务不存在")
        if str(task["created_date"]) == repaired_date:
            return task_response(task)
        file_count = conn.execute("SELECT COUNT(*) FROM production_files WHERE task_id=?", (task_id,)).fetchone()[0]
        if file_count:
            raise ValueError("任务已有文件记录，不能自动更正创建日期")
        source_root = Path(str(task["root_path"])).resolve()
        source_directories = [Path(str(task[column])).resolve() for column in ("material_path", "template_path", "final_path")]
        if not source_root.is_relative_to(production_root) or any(not directory.is_relative_to(source_root) for directory in source_directories):
            raise ValueError("任务目录不属于 V2 生产文件根目录，已停止更正")
        if not source_root.is_dir() or any(not directory.is_dir() or any(directory.iterdir()) for directory in source_directories):
            raise ValueError("任务目录不是空目录，不能自动更正创建日期")
        target_root, target_materials, target_template, target_finals = task_paths(
            repaired_date, str(task["account_name"]), str(task["drama_name"])
        )
        if target_root.exists():
            raise ValueError("正确日期目录已存在，不能自动合并")
        target_root.parent.mkdir(parents=True, exist_ok=True)
        source_root.rename(target_root)
        try:
            stamp = now_text()
            conn.execute(
                "UPDATE production_tasks SET created_date=?, root_path=?, material_path=?, template_path=?, final_path=?, updated_at=? WHERE id=?",
                (repaired_date, str(target_root), str(target_materials), str(target_template), str(target_finals), stamp, task_id),
            )
            conn.commit()
        except Exception:
            target_root.rename(source_root)
            raise
        for parent in (source_root.parent, source_root.parent.parent):
            if parent != production_root:
                try:
                    parent.rmdir()
                except OSError:
                    break
        repaired = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        return task_response(repaired)
    finally:
        conn.close()


def scan_task(task_id: str) -> dict[str, object]:
    # 扫描包含哈希、视频探测和首帧缓存；同一时间只运行一个，避免大批量文件并发占满磁盘。
    with SCAN_LOCK:
      conn = connection()
      try:
        task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("生产任务不存在")
        directory = Path(str(task["material_path"]))
        directory.mkdir(parents=True, exist_ok=True)
        files = sorted((item for item in directory.iterdir() if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS), key=lambda item: natural_key(item.name))
        renamed = rename_without_overwrite(directory, files, str(task["drama_name"]))
        stamp = now_text()
        items: list[dict[str, object]] = []
        for original, path in zip(files, renamed):
            md5 = content_hash(path, "md5")
            sha256 = content_hash(path, "sha256")
            sequence = canonical_sequence(path, str(task["drama_name"]))
            duration_seconds, thumbnail_path = probe_material(path, md5)
            conn.execute(
                "INSERT INTO production_files "
                "(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds,thumbnail_path) "
                "VALUES (?, ?, 'original_material', ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?) "
                "ON CONFLICT(task_id, file_path) DO UPDATE SET "
                "original_name=excluded.original_name, file_name=excluded.file_name, md5=excluded.md5, sha256=excluded.sha256, "
                "size_bytes=excluded.size_bytes, sequence_no=excluded.sequence_no, duration_seconds=excluded.duration_seconds, "
                "thumbnail_path=excluded.thumbnail_path, status='available', updated_at=excluded.updated_at",
                (uuid.uuid4().hex, task_id, original.name, path.name, str(path), md5, sha256, path.stat().st_size, sequence, stamp, stamp, duration_seconds, thumbnail_path),
            )
            material = conn.execute(
                "SELECT id FROM production_files WHERE task_id=? AND file_path=?",
                (task_id, str(path)),
            ).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO production_video_tasks "
                "(id, task_id, source_material_id, status, draft_path, output_path, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending_generation', '', '', ?, ?)",
                (uuid.uuid4().hex, task_id, str(material["id"]), stamp, stamp),
            )
            conn.execute(
                "UPDATE production_video_tasks SET status='pending_generation', updated_at=? "
                "WHERE source_material_id=? AND status IN ('cancelled', 'invalidated')",
                (stamp, str(material["id"])),
            )
            items.append({"name": path.name, "path": str(path), "sequence_no": sequence, "md5": md5, "size_bytes": path.stat().st_size})
        current_paths = {str(path) for path in renamed}
        recorded_paths = conn.execute(
            "SELECT id, file_path FROM production_files WHERE task_id=? AND file_type='original_material'",
            (task_id,),
        ).fetchall()
        for recorded in recorded_paths:
            if str(recorded["file_path"]) not in current_paths:
                material_id = str(recorded["id"])
                conn.execute(
                    "UPDATE production_files SET status='source_missing', updated_at=? WHERE id=?",
                    (stamp, material_id),
                )
                conn.execute(
                    "UPDATE production_video_tasks SET status=CASE "
                    "WHEN status IN ('pending_generation', 'generation_queued') THEN 'cancelled' "
                    "WHEN status='generating' THEN 'cancellation_requested' "
                    "ELSE 'invalidated' END, updated_at=? WHERE source_material_id=?",
                    (stamp, material_id),
                )
        conn.execute("UPDATE production_tasks SET status=?, updated_at=? WHERE id=?", ("materials_scanned", stamp, task_id))
        conn.commit()
        return {"task_id": task_id, "directory": str(directory), "discovered": len(files), "items": items}
      finally:
          conn.close()


def template_stem(task: sqlite3.Row) -> str:
    created = str(task["created_date"])
    return f"{int(created[5:7])}月{int(created[8:10])}日-{safe_component(str(task['account_name']), '账号')}-{safe_component(str(task['drama_name']), '剧集')}"


def queue_template_job(task_id: str, *, regenerate: bool = False) -> dict[str, object]:
    """Reserve exactly three real videos for one V2 template attempt.

    This intentionally stops before invoking Jianying.  The separate runner is
    responsible for photo preparation and draft creation, so a failed preflight
    can restore these names without touching a draft.
    """
    with TEMPLATE_JOB_LOCK:
        conn = connection()
        renamed: list[tuple[Path, Path]] = []
        try:
            task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise ValueError("生产任务不存在")
            current = conn.execute(
                "SELECT * FROM template_jobs WHERE task_id=? ORDER BY version_no DESC LIMIT 1", (task_id,)
            ).fetchone()
            if current and str(current["status"]) in {"queued", "dispatching", "running"}:
                raise ValueError("当前任务已有模板生成任务")
            if current and str(current["status"]) == "draft_ready" and not regenerate:
                raise ValueError("当前任务已有模板草稿，请使用“重新生成”创建新版本")
            videos_root = WORKSPACE / "生成资源" / "真人视频"
            videos_root.mkdir(parents=True, exist_ok=True)
            candidates = sorted(
                (item for item in videos_root.iterdir()
                 if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS and not item.name.startswith("已使用")),
                key=lambda item: natural_key(item.name),
            )
            if len(candidates) < 3:
                raise ValueError(f"真人视频不足 3 条，当前可领取 {len(candidates)} 条")
            current_status = str(current["status"]) if current else ""
            # 失败/超时是同一次尝试的重新执行，继续使用 R01；只有成功
            # 的模板被用户主动重新生成时，才创建 R02、R03 新版本。
            version = int(current["version_no"]) if current and regenerate and current_status in {"error", "timeout"} else (int(current["version_no"]) + 1 if current else 1)
            stamp = now_text(); job_id = uuid.uuid4().hex; stem = template_stem(task)
            attempt_root = Path(str(task["template_path"])) / f"R{version:02d}"
            if current and version == int(current["version_no"]) and current_status in {"error", "timeout"}:
                shutil.rmtree(attempt_root / "模板剧照缓存", ignore_errors=True)
                shutil.rmtree(attempt_root / "照片缓存", ignore_errors=True)
                configured_draft_root = str(get_v2_settings().get("jianying_draft_root") or "").strip()
                if configured_draft_root:
                    shutil.rmtree(Path(configured_draft_root).expanduser() / str(current["draft_name"]), ignore_errors=True)
            attempt_root.mkdir(parents=True, exist_ok=True)
            reserved: list[dict[str, str]] = []
            try:
                for index, source in enumerate(candidates[:3], start=1):
                    # 每个模板版本都保留独立的领取记录，避免重新生成时覆盖上一版本。
                    target = source.with_name(f"已使用-{stem}-R{version:02d}-{index:02d}{source.suffix.lower()}")
                    if target.exists():
                        raise ValueError("真人视频领取命名冲突，未覆盖任何文件")
                    source.rename(target); renamed.append((source, target))
                    reserved.append({"original_path": str(source), "reserved_path": str(target)})
                draft_name = f"{stem}-模板-R{version:02d}"
                report_path = str(attempt_root / "生成报告.json")
                log_path = str(attempt_root / "执行日志.txt")
                seed = int(datetime.now().strftime("%Y%m%d%H%M%S"))
                if current and version == int(current["version_no"]) and current_status in {"error", "timeout"}:
                    conn.execute(
                        "UPDATE template_jobs SET status='queued', draft_path='', video_path='', pairing_path='', "
                        "report_path=?, log_path=?, error_message='', seed=?, reserved_videos_json=?, "
                        "started_at='', finished_at='', updated_at=? WHERE id=?",
                        (report_path, log_path, seed, json.dumps(reserved, ensure_ascii=False), stamp, str(current["id"])),
                    )
                    job_id = str(current["id"])
                else:
                    conn.execute(
                        "INSERT INTO template_jobs(id,task_id,version_no,status,draft_name,draft_path,report_path,log_path,seed,reserved_videos_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (job_id, task_id, version, "queued", draft_name, "", report_path, log_path,
                         seed, json.dumps(reserved, ensure_ascii=False), stamp, stamp),
                    )
                conn.commit()
                return {"id": job_id, "task_id": task_id, "version_no": version, "draft_name": draft_name, "status": "queued"}
            except Exception:
                for original, target in reversed(renamed):
                    if target.exists() and not original.exists(): target.rename(original)
                raise
        finally:
            conn.close()


def regenerate_template_job(job_id: str) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT task_id FROM template_jobs WHERE id=?", (job_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("模板任务不存在")
    return queue_template_job(str(row["task_id"]), regenerate=True)


def cleanup_orphan_template_job(job_id: str) -> dict[str, object]:
    """Remove only a terminal template record whose production task is gone."""
    conn = connection()
    try:
        row = conn.execute(
            "SELECT j.id, j.task_id, j.status, t.id AS parent_id "
            "FROM template_jobs j LEFT JOIN production_tasks t ON t.id=j.task_id WHERE j.id=?",
            (job_id,),
        ).fetchone()
        if not row:
            raise ValueError("任务记录不存在")
        if row["parent_id"] is not None:
            raise ValueError("该任务仍关联有效生产任务，不能按孤儿记录清理")
        if str(row["status"]) in {"queued", "dispatching", "running", "retry_requested"}:
            raise ValueError("任务仍在执行或排队，不能清理")
        conn.execute("DELETE FROM template_jobs WHERE id=?", (job_id,))
        conn.commit()
        return {"deleted": True}
    finally:
        conn.close()


def production_media(file_id: str, *, thumbnail: bool = False) -> Path:
    conn = connection()
    try:
        row = conn.execute("SELECT file_path, thumbnail_path FROM production_files WHERE id=?", (file_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("素材文件不存在")
    candidate = Path(str(row["thumbnail_path"] if thumbnail else row["file_path"] or "")).resolve()
    allowed_root = DATA_ROOT.resolve() if thumbnail else WORKSPACE.resolve()
    if not candidate.is_relative_to(allowed_root) or not candidate.is_file():
        raise ValueError("素材预览文件不存在")
    return candidate


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        match = re.fullmatch(r"/api/v2/production-files/([a-f0-9]+)/thumbnail", path)
        if match:
            try:
                file_path = production_media(match.group(1), thumbnail=True)
                body = file_path.read_bytes()
                self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/v2/production-files/([a-f0-9]+)/media", path)
        if match:
            try:
                file_path = production_media(match.group(1)); size = file_path.stat().st_size
                self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "video/mp4"); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(size)); self.end_headers()
                with file_path.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile)
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        if path == "/api/v2/health":
            self._json(HTTPStatus.OK, {"status": "ok", "service": "v2-file-service"})
            return
        if path == "/api/v2/theaters":
            self._json(HTTPStatus.OK, list_theaters())
            return
        if path == "/api/v2/accounts":
            self._json(HTTPStatus.OK, list_accounts())
            return
        if path == "/api/v2/sub-theaters":
            self._json(HTTPStatus.OK, list_sub_theaters())
            return
        if path == "/api/v2/dramas":
            self._json(HTTPStatus.OK, list_dramas())
            return
        if path == "/api/v2/drama-profiles":
            self._json(HTTPStatus.OK, list_drama_profiles())
            return
        match = re.fullmatch(r"/api/v2/dramas/([a-f0-9]+)/cover", path)
        if match:
            conn = connection()
            try:
                row = conn.execute("SELECT cover_path FROM drama_profiles WHERE drama_id=?", (match.group(1),)).fetchone()
                cover = Path(str(row["cover_path"] or "")) if row else None
            finally:
                conn.close()
            if not cover or not cover.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "封面不存在"})
                return
            content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(cover.suffix.lower(), "application/octet-stream")
            data = cover.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/v2/production-resources":
            self._json(HTTPStatus.OK, list_production_resources())
            return
        if path == "/api/v2/settings":
            self._json(HTTPStatus.OK, get_v2_settings())
            return
        if path == "/api/v2/drives":
            self._json(HTTPStatus.OK, {"items": list_windows_drives()})
            return
        if path == "/api/v2/production-tasks":
            self._json(HTTPStatus.OK, list_tasks())
            return
        if path == "/api/v2/task-center":
            try:
                from server.task_center_service import task_center_snapshot
            except ModuleNotFoundError:
                from task_center_service import task_center_snapshot
            self._json(HTTPStatus.OK, task_center_snapshot())
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "V2 接口不存在"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/v2/production-tasks":
                self._json(HTTPStatus.CREATED, create_task(payload))
                return
            if path == "/api/v2/exporter/jobs":
                self._json(HTTPStatus.CREATED, create_export_job(payload))
                return
            match = re.fullmatch(r"/api/v2/exporter/jobs/([a-f0-9]+)/start", path)
            if match:
                self._json(HTTPStatus.ACCEPTED, start_export_job(match.group(1)))
                return
            if path == "/api/v2/theaters":
                self._json(HTTPStatus.CREATED, create_theater(payload))
                return
            if path == "/api/v2/theaters/batch":
                self._json(HTTPStatus.CREATED, create_theaters_batch(payload))
                return
            if path == "/api/v2/accounts":
                self._json(HTTPStatus.CREATED, create_account(payload))
                return
            if path == "/api/v2/accounts/batch":
                self._json(HTTPStatus.CREATED, create_accounts_batch(payload))
                return
            if path == "/api/v2/sub-theaters":
                self._json(HTTPStatus.CREATED, create_sub_theater(payload))
                return
            if path == "/api/v2/sub-theaters/batch":
                self._json(HTTPStatus.CREATED, create_sub_theaters_batch(payload))
                return
            if path == "/api/v2/dramas":
                self._json(HTTPStatus.CREATED, create_drama(payload)); return
            if path == "/api/v2/dramas/batch":
                self._json(HTTPStatus.CREATED, create_dramas_batch(payload)); return
            if path == "/api/v2/open-folder":
                folder = Path(str(payload.get("path") or ""))
                if not folder.is_dir(): raise ValueError("目录不存在")
                os.startfile(str(folder))
                self._json(HTTPStatus.OK, {"opened": True}); return
            if path == "/api/v2/open-file":
                file_path = Path(str(payload.get("path") or "")).resolve()
                if not file_path.is_relative_to(WORKSPACE.resolve()) or not file_path.is_file():
                    raise ValueError("文件不存在或不属于 V2 工作目录")
                os.startfile(str(file_path))
                self._json(HTTPStatus.OK, {"opened": True}); return
            if path == "/api/v2/settings":
                self._json(HTTPStatus.OK, update_v2_settings(payload)); return
            if path == "/api/v2/select-path":
                self._json(HTTPStatus.OK, select_v2_path(str(payload.get("kind") or ""))); return
            match = re.fullmatch(r"/api/v2/task-center/tasks/([a-f0-9]+)/retry", path)
            if match:
                try:
                    from server.template_engine.runner import request_retry
                except ModuleNotFoundError:
                    from template_engine.runner import request_retry
                self._json(HTTPStatus.OK, request_retry(match.group(1))); return
            match = re.fullmatch(r"/api/v2/task-center/tasks/([a-f0-9]+)/regenerate", path)
            if match:
                self._json(HTTPStatus.CREATED, regenerate_template_job(match.group(1))); return
            match = re.fullmatch(r"/api/v2/dramas/([a-f0-9]+)/cover", path)
            if match:
                self._json(HTTPStatus.OK, upload_drama_cover(match.group(1), payload)); return
            match = re.fullmatch(r"/api/v2/dramas/([a-f0-9]+)/profile", path)
            if match:
                self._json(HTTPStatus.OK, create_drama_profile(match.group(1))); return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/scan", path)
            if match:
                self._json(HTTPStatus.OK, scan_task(match.group(1)))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/template", path)
            if match:
                self._json(HTTPStatus.CREATED, queue_template_job(match.group(1), regenerate=bool(payload.get("regenerate", False))))
                return
            if path in {"/api/v2/task-center/pause", "/api/v2/task-center/resume"}:
                try:
                    from server.task_center_service import set_queue_paused, task_center_snapshot
                except ModuleNotFoundError:
                    from task_center_service import set_queue_paused, task_center_snapshot
                set_queue_paused(path.endswith("/pause"))
                self._json(HTTPStatus.OK, task_center_snapshot())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "V2 接口不存在"})
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_PATCH(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            match = re.fullmatch(r"/api/v2/theaters/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                self._json(HTTPStatus.OK, update_theater(match.group(1), payload))
                return
            match = re.fullmatch(r"/api/v2/sub-theaters/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                self._json(HTTPStatus.OK, update_sub_theater(match.group(1), payload))
                return
            match = re.fullmatch(r"/api/v2/accounts/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                self._json(HTTPStatus.OK, update_account(match.group(1), payload))
                return
            match = re.fullmatch(r"/api/v2/dramas/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                self._json(HTTPStatus.OK, update_drama(match.group(1), payload)); return
            self._json(HTTPStatus.NOT_FOUND, {"error": "V2 接口不存在"})
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            match = re.fullmatch(r"/api/v2/task-center/tasks/([a-f0-9]+)/orphan", urlparse(self.path).path)
            if match:
                self._json(HTTPStatus.OK, cleanup_orphan_template_job(match.group(1)))
                return
            match = re.fullmatch(r"/api/v2/theaters/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                delete_theater(match.group(1))
                self._json(HTTPStatus.OK, {"deleted": True})
                return
            match = re.fullmatch(r"/api/v2/sub-theaters/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                delete_sub_theater(match.group(1))
                self._json(HTTPStatus.OK, {"deleted": True})
                return
            match = re.fullmatch(r"/api/v2/accounts/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                delete_account(match.group(1))
                self._json(HTTPStatus.OK, {"deleted": True})
                return
            match = re.fullmatch(r"/api/v2/dramas/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                delete_drama(match.group(1)); self._json(HTTPStatus.OK, {"deleted": True}); return
            self._json(HTTPStatus.NOT_FOUND, {"error": "V2 接口不存在"})
        except (ValueError, RuntimeError, OSError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    if WORKSPACE is not None:
        ensure_v2_root_layout()
    try:
        from server.task_center_service import start_scheduler
    except ModuleNotFoundError:
        from task_center_service import start_scheduler
    start_scheduler()
    state = "V2 文件服务已启动" if WORKSPACE is not None else "V2 文件服务已启动：需要配置数据盘"
    print(f"{state}，http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
