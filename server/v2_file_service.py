"""Minimal V2 production-file service for the first migration step.

This service owns V2 paths and metadata. It never imports or mutates V1.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import sys
import uuid
import base64
import ctypes
import queue
import threading
import shutil
import unicodedata
import subprocess
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from server.tool_resolver import ToolResolutionError, resolve_ffmpeg, resolve_ffprobe
from server.runtime_process import no_window_kwargs

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
BGM_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
HOST = os.environ.get("V2_FILE_SERVICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("V2_FILE_SERVICE_PORT", "8782"))
STANDARD_SYSTEM_ROOT_NAME = "短剧推广运营系统"
REVENUE_RUN_RECOVERY_LOCK = threading.Lock()
REVENUE_RUNS_RECOVERED = False
DATABASE_INITIALIZATION_LOCK = threading.Lock()
DATABASE_INITIALIZED_PATH: Path | None = None


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
RESOURCE_RESERVATION_LOCK = threading.Lock()
SCAN_LOCK = threading.Lock()
RESOURCE_PROBE_CACHE: dict[str, tuple[int, int, float, str, str]] = {}
RESOURCE_PROBE_QUEUE: queue.Queue[tuple[str, Path, str, int, int]] = queue.Queue()
RESOURCE_PROBE_PENDING: set[str] = set()
RESOURCE_PROBE_LOCK = threading.Lock()
RESOURCE_PROBE_THREAD: threading.Thread | None = None
# A template run records several concrete steps for each of ten photos.  Keep
# one complete run visible without turning task diagnostics into an unbounded
# log store (cleanup still owns the lifecycle of these rows).
EXECUTOR_TRACE_LIMIT = 160


def application_resource_root() -> Path:
    """Locate read-only application resources in source and frozen runs."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parents[1]


def frontend_dist_root() -> Path:
    """Return the built React application bundled with the V2 runtime."""
    root = application_resource_root() / "dist"
    if not (root / "index.html").is_file():
        raise RuntimeError(f"找不到 V2 前端构建文件：{root}；请先执行 npm run build")
    return root


def resolve_frontend_asset(request_path: str) -> tuple[Path, bool]:
    """Resolve a static asset, falling back to the SPA shell for client routes."""
    root = frontend_dist_root().resolve()
    relative = unquote(request_path).lstrip("/") or "index.html"
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("前端资源路径不合法")
    if candidate.is_file():
        return candidate, candidate.name == "index.html"
    if Path(relative).suffix:
        raise FileNotFoundError(relative)
    return root / "index.html", True


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


def _initialize_connection() -> sqlite3.Connection:
    """Create or migrate one database once for each service process/path."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Background executors and button actions share this SQLite database.
    # Wait briefly for the active writer instead of dropping the HTTP request
    # with ``database is locked`` while a task is being retried.
    conn = sqlite3.connect(path, timeout=30.0)
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
            final_video_manual_check INTEGER NOT NULL DEFAULT 0 CHECK(final_video_manual_check IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cleanup_records (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, cleanup_type TEXT NOT NULL,
            status TEXT NOT NULL, deleted_json TEXT NOT NULL DEFAULT '[]',
            retained_json TEXT NOT NULL DEFAULT '[]', error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT ''
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
            resolution TEXT NOT NULL DEFAULT '',
            missing_scan_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(task_id, file_path)
        );
        CREATE TABLE IF NOT EXISTS resource_index (
            resource_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            category_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            file_size_bytes INTEGER NOT NULL,
            file_mtime_ns INTEGER NOT NULL,
            file_identity TEXT NOT NULL DEFAULT '',
            duration_seconds REAL,
            resolution TEXT NOT NULL DEFAULT '',
            thumbnail_path TEXT NOT NULL DEFAULT '',
            probe_status TEXT NOT NULL DEFAULT 'pending',
            probe_error TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL,
            source_present INTEGER NOT NULL DEFAULT 1
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
        CREATE TABLE IF NOT EXISTS production_resource_reservations (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES production_tasks(id) ON DELETE CASCADE,
            resource_type TEXT NOT NULL CHECK(resource_type IN ('real_video','real_image')),
            version_no INTEGER NOT NULL DEFAULT 1,
            sequence_no INTEGER NOT NULL,
            original_path TEXT NOT NULL,
            reserved_path TEXT NOT NULL,
            original_name TEXT NOT NULL,
            reserved_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'reserved' CHECK(status IN ('reserved','released','missing')),
            created_at TEXT NOT NULL,
            released_at TEXT NOT NULL DEFAULT '',
            UNIQUE(task_id, resource_type, version_no, sequence_no),
            UNIQUE(reserved_path)
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
        CREATE TABLE IF NOT EXISTS wechat_index_keywords (
            id TEXT PRIMARY KEY,
            drama_id TEXT NOT NULL REFERENCES dramas(id) ON DELETE CASCADE,
            keyword TEXT NOT NULL,
            normalized_keyword TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('primary', 'equivalent', 'related', 'candidate', 'rejected')),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
            source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual', 'suggestion_import')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(drama_id, keyword)
        );
        CREATE TABLE IF NOT EXISTS wechat_index_fetches (
            id TEXT PRIMARY KEY,
            keyword_id TEXT NOT NULL REFERENCES wechat_index_keywords(id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL CHECK(source_kind IN ('history_import', 'collector')),
            response_json TEXT NOT NULL,
            received_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS wechat_index_observations (
            id TEXT PRIMARY KEY,
            keyword_id TEXT NOT NULL REFERENCES wechat_index_keywords(id) ON DELETE CASCADE,
            ymd TEXT NOT NULL,
            total_score INTEGER NOT NULL,
            source_fetch_id TEXT NOT NULL REFERENCES wechat_index_fetches(id) ON DELETE CASCADE,
            collected_at TEXT NOT NULL,
            UNIQUE(keyword_id, ymd)
        );
        CREATE TABLE IF NOT EXISTS wechat_index_suggestions (
            id TEXT PRIMARY KEY,
            keyword_id TEXT NOT NULL REFERENCES wechat_index_keywords(id) ON DELETE CASCADE,
            suggested_keyword TEXT NOT NULL,
            normalized_keyword TEXT NOT NULL,
            normalization_match INTEGER NOT NULL DEFAULT 0 CHECK(normalization_match IN (0, 1)),
            decision TEXT NOT NULL DEFAULT 'pending' CHECK(decision IN ('pending', 'adopted', 'rejected')),
            source_response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(keyword_id, suggested_keyword)
        );
        CREATE TABLE IF NOT EXISTS v2_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS release_address_history (
            id TEXT PRIMARY KEY,
            account_name TEXT NOT NULL,
            province TEXT NOT NULL,
            city TEXT NOT NULL,
            district TEXT NOT NULL,
            detail_address TEXT NOT NULL,
            normalized_key TEXT NOT NULL,
            use_count INTEGER NOT NULL DEFAULT 0,
            first_used_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL,
            UNIQUE(account_name, normalized_key)
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
        CREATE TABLE IF NOT EXISTS executor_trace_events (
            id TEXT PRIMARY KEY,
            executor_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            production_task_id TEXT NOT NULL,
            sequence_no INTEGER NOT NULL,
            phase TEXT NOT NULL,
            message TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(run_id, sequence_no)
        );
        CREATE INDEX IF NOT EXISTS idx_executor_trace_task
            ON executor_trace_events(production_task_id, created_at);
        CREATE TABLE IF NOT EXISTS executor_controls (
            executor_id TEXT PRIMARY KEY,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            is_paused INTEGER NOT NULL DEFAULT 0 CHECK(is_paused IN (0, 1)),
            control_state TEXT NOT NULL DEFAULT 'idle',
            pause_requested INTEGER NOT NULL DEFAULT 0 CHECK(pause_requested IN (0, 1)),
            pause_reason TEXT NOT NULL DEFAULT '',
            current_task_id TEXT NOT NULL DEFAULT '',
            last_error_message TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v2_revenue_collection_attempts (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            theater_id TEXT NOT NULL REFERENCES theaters(id),
            adapter_key TEXT NOT NULL,
            revenue_date TEXT NOT NULL,
            collection_status TEXT NOT NULL CHECK(collection_status IN ('success', 'no_data', 'failed')),
            amount TEXT,
            error_message TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v2_revenue_collection_runs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            trigger_source TEXT NOT NULL DEFAULT 'manual',
            scheduled_slots_json TEXT NOT NULL DEFAULT '[]',
            total_units INTEGER NOT NULL DEFAULT 0,
            completed_units INTEGER NOT NULL DEFAULT 0,
            success_units INTEGER NOT NULL DEFAULT 0,
            no_data_units INTEGER NOT NULL DEFAULT 0,
            failed_units INTEGER NOT NULL DEFAULT 0,
            current_theater TEXT NOT NULL DEFAULT '',
            current_account TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v2_daily_revenues (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            theater_id TEXT NOT NULL REFERENCES theaters(id),
            revenue_date TEXT NOT NULL,
            amount TEXT NOT NULL,
            quality TEXT NOT NULL CHECK(quality='direct'),
            source_attempt_id TEXT NOT NULL REFERENCES v2_revenue_collection_attempts(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(account_id, revenue_date)
        );
        CREATE TABLE IF NOT EXISTS v2_revenue_video_details (
            id TEXT PRIMARY KEY,
            attempt_id TEXT NOT NULL REFERENCES v2_revenue_collection_attempts(id) ON DELETE CASCADE,
            account_id TEXT NOT NULL REFERENCES accounts(id), theater_id TEXT NOT NULL REFERENCES theaters(id),
            revenue_date TEXT NOT NULL, source_video_id TEXT NOT NULL, source_drama_name TEXT NOT NULL,
            video_views INTEGER NOT NULL DEFAULT 0, drama_views INTEGER NOT NULL DEFAULT 0,
            gross_revenue TEXT NOT NULL, source_rank INTEGER NOT NULL DEFAULT 0,
            matched_drama_id TEXT REFERENCES dramas(id), match_status TEXT NOT NULL DEFAULT 'unmatched',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE(revenue_date, account_id, source_video_id)
        );
        CREATE TABLE IF NOT EXISTS v2_revenue_video_links (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            source_video_id TEXT NOT NULL,
            production_task_id TEXT NOT NULL REFERENCES production_tasks(id),
            production_video_task_id TEXT NOT NULL REFERENCES production_video_tasks(id),
            source_material_id TEXT NOT NULL REFERENCES production_files(id),
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(account_id, source_video_id)
        );
        CREATE TABLE IF NOT EXISTS v2_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            change_type TEXT NOT NULL,
            production_task_id TEXT NOT NULL DEFAULT '',
            task_id TEXT NOT NULL DEFAULT '',
            account_id TEXT NOT NULL DEFAULT '',
            drama_id TEXT NOT NULL DEFAULT '',
            video_id TEXT NOT NULL DEFAULT '',
            material_id TEXT NOT NULL DEFAULT '',
            entity_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """
    )
    task_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_tasks)")}
    change_event_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(v2_change_events)")}
    if "entity_id" not in change_event_columns:
        conn.execute("ALTER TABLE v2_change_events ADD COLUMN entity_id TEXT NOT NULL DEFAULT ''")
    if "planned_publish_at" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN planned_publish_at TEXT NOT NULL DEFAULT ''")
    if "release_status" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN release_status TEXT NOT NULL DEFAULT 'unregistered'")
    if "actual_release_time" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN actual_release_time TEXT NOT NULL DEFAULT ''")
    for column in ("release_province", "release_city", "release_district", "release_detail_address"):
        if column not in task_columns:
            conn.execute(f"ALTER TABLE production_tasks ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if "cleanup_status" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN cleanup_status TEXT NOT NULL DEFAULT 'active'")
    if "cleaned_at" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN cleaned_at TEXT NOT NULL DEFAULT ''")
    if "process_cleanup_at" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN process_cleanup_at TEXT NOT NULL DEFAULT ''")
    if "raw_cleanup_at" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN raw_cleanup_at TEXT NOT NULL DEFAULT ''")
    if "final_video_manual_check" not in task_columns:
        conn.execute("ALTER TABLE production_tasks ADD COLUMN final_video_manual_check INTEGER NOT NULL DEFAULT 0")
    file_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_files)")}
    resource_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(resource_index)")}
    revenue_attempt_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(v2_revenue_collection_attempts)")}
    for column, definition in (("data_kind", "TEXT NOT NULL DEFAULT 'account_daily_total'"), ("period_end", "TEXT NOT NULL DEFAULT ''"), ("period_type", "TEXT NOT NULL DEFAULT 'date_range'")):
        if column not in revenue_attempt_columns:
            conn.execute(f"ALTER TABLE v2_revenue_collection_attempts ADD COLUMN {column} {definition}")
    revenue_run_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(v2_revenue_collection_runs)")}
    for column, definition in (("trigger_source", "TEXT NOT NULL DEFAULT 'manual'"), ("scheduled_slots_json", "TEXT NOT NULL DEFAULT '[]'")):
        if column not in revenue_run_columns:
            conn.execute(f"ALTER TABLE v2_revenue_collection_runs ADD COLUMN {column} {definition}")
    if "duration_seconds" not in file_columns:
        conn.execute("ALTER TABLE production_files ADD COLUMN duration_seconds REAL NOT NULL DEFAULT 0")
    if "thumbnail_path" not in file_columns:
        conn.execute("ALTER TABLE production_files ADD COLUMN thumbnail_path TEXT NOT NULL DEFAULT ''")
    if "missing_scan_count" not in file_columns:
        conn.execute("ALTER TABLE production_files ADD COLUMN missing_scan_count INTEGER NOT NULL DEFAULT 0")
    if "resolution" not in file_columns:
        conn.execute("ALTER TABLE production_files ADD COLUMN resolution TEXT NOT NULL DEFAULT ''")
    if "file_identity" not in resource_columns:
        conn.execute("ALTER TABLE resource_index ADD COLUMN file_identity TEXT NOT NULL DEFAULT ''")
    if "probe_status" not in resource_columns:
        conn.execute("ALTER TABLE resource_index ADD COLUMN probe_status TEXT NOT NULL DEFAULT 'pending'")
        conn.execute("UPDATE resource_index SET probe_status=CASE WHEN category IN ('real_video', 'lead_video') AND thumbnail_path<>'' THEN 'ready' ELSE 'pending' END")
    if "probe_error" not in resource_columns:
        conn.execute("ALTER TABLE resource_index ADD COLUMN probe_error TEXT NOT NULL DEFAULT ''")
    video_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(production_video_tasks)")}
    for column, definition in (("error_message", "TEXT NOT NULL DEFAULT ''"), ("started_at", "TEXT NOT NULL DEFAULT ''"), ("finished_at", "TEXT NOT NULL DEFAULT ''")):
        if column not in video_columns:
            conn.execute(f"ALTER TABLE production_video_tasks ADD COLUMN {column} {definition}")
    conn.executescript(
        "CREATE INDEX IF NOT EXISTS idx_production_tasks_release_status ON production_tasks(release_status, cleanup_status);"
        "CREATE INDEX IF NOT EXISTS idx_production_tasks_schedule ON production_tasks(planned_publish_at, created_at);"
        "CREATE INDEX IF NOT EXISTS idx_template_jobs_task_version ON template_jobs(task_id, version_no DESC);"
        "CREATE INDEX IF NOT EXISTS idx_production_video_tasks_task_status ON production_video_tasks(task_id, status, created_at);"
        "CREATE INDEX IF NOT EXISTS idx_export_jobs_subject ON export_jobs(subject_type, subject_id, created_at DESC);"
        "CREATE INDEX IF NOT EXISTS idx_export_attempts_job_attempt ON export_attempts(job_id, attempt_no DESC);"
        "CREATE INDEX IF NOT EXISTS idx_v2_revenue_attempts_date ON v2_revenue_collection_attempts(revenue_date, account_id, collected_at DESC);"
        "CREATE INDEX IF NOT EXISTS idx_v2_daily_revenues_date ON v2_daily_revenues(revenue_date, account_id);"
        "CREATE INDEX IF NOT EXISTS idx_v2_revenue_video_details_date ON v2_revenue_video_details(revenue_date, account_id, source_video_id);"
        "CREATE INDEX IF NOT EXISTS idx_v2_revenue_video_details_video_first ON v2_revenue_video_details(account_id, source_video_id, revenue_date);"
        "CREATE INDEX IF NOT EXISTS idx_production_tasks_account_drama_dates ON production_tasks(account_name, drama_name, planned_publish_at, actual_release_time);"
        "CREATE INDEX IF NOT EXISTS idx_v2_revenue_video_links_video ON v2_revenue_video_links(account_id, source_video_id);"
        "CREATE INDEX IF NOT EXISTS idx_v2_change_events_id ON v2_change_events(id);"
        "CREATE INDEX IF NOT EXISTS idx_resource_index_identity ON resource_index(file_identity);"
        "CREATE INDEX IF NOT EXISTS idx_wechat_index_keywords_drama ON wechat_index_keywords(drama_id, role, enabled);"
        "CREATE INDEX IF NOT EXISTS idx_wechat_index_observations_keyword_date ON wechat_index_observations(keyword_id, ymd);"
    )
    # SQLite triggers make background executors participate in the same
    # change stream as button-driven API operations.  They carry ownership
    # IDs only; the UI still reads the authoritative single-object endpoint.
    # Keep trigger creation idempotent. Dropping a trigger on every connection
    # needlessly takes a schema write lock and races with executor updates.
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS v2_evt_production_task_update AFTER UPDATE ON production_tasks BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,updated_at) VALUES ('production_task_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_production_task_insert AFTER INSERT ON production_tasks BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,updated_at) VALUES ('production_task_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_material_change AFTER INSERT ON production_files BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,material_id,updated_at) VALUES ('material_changed',NEW.task_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_material_update AFTER UPDATE ON production_files BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,material_id,updated_at) VALUES ('material_changed',NEW.task_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_template_change AFTER INSERT ON template_jobs BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,task_id,updated_at) VALUES ('template_changed',NEW.task_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_template_update AFTER UPDATE ON template_jobs BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,task_id,updated_at) VALUES ('template_changed',NEW.task_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_video_change AFTER INSERT ON production_video_tasks BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,task_id,video_id,updated_at) VALUES ('video_changed',NEW.task_id,NEW.id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_video_update AFTER UPDATE ON production_video_tasks BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,task_id,video_id,updated_at) VALUES ('video_changed',NEW.task_id,NEW.id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_export_job_update AFTER UPDATE ON export_jobs BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,task_id,updated_at) VALUES ('video_export_changed',NEW.production_task_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_export_attempt_update AFTER UPDATE ON export_attempts BEGIN
          INSERT INTO v2_change_events(change_type,production_task_id,task_id,updated_at)
          SELECT 'video_export_changed', j.production_task_id, NEW.id, NEW.updated_at FROM export_jobs j WHERE j.id=NEW.job_id;
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_executor_update AFTER UPDATE ON executor_controls BEGIN
          INSERT INTO v2_change_events(change_type,task_id,updated_at) VALUES ('task_changed',NEW.current_task_id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_account_update AFTER UPDATE ON accounts BEGIN
          INSERT INTO v2_change_events(change_type,account_id,updated_at) VALUES ('account_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_account_insert AFTER INSERT ON accounts BEGIN
          INSERT INTO v2_change_events(change_type,account_id,updated_at) VALUES ('account_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_account_delete AFTER DELETE ON accounts BEGIN
          INSERT INTO v2_change_events(change_type,account_id,updated_at) VALUES ('account_changed',OLD.id,OLD.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_drama_update AFTER UPDATE ON dramas BEGIN
          INSERT INTO v2_change_events(change_type,drama_id,updated_at) VALUES ('drama_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_drama_insert AFTER INSERT ON dramas BEGIN
          INSERT INTO v2_change_events(change_type,drama_id,updated_at) VALUES ('drama_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_drama_delete AFTER DELETE ON dramas BEGIN
          INSERT INTO v2_change_events(change_type,drama_id,updated_at) VALUES ('drama_changed',OLD.id,OLD.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_theater_update AFTER UPDATE ON theaters BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('theater_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_theater_insert AFTER INSERT ON theaters BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('theater_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_theater_delete AFTER DELETE ON theaters BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('theater_changed',OLD.id,OLD.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_sub_theater_update AFTER UPDATE ON sub_theaters BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('sub_theater_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_sub_theater_insert AFTER INSERT ON sub_theaters BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('sub_theater_changed',NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_sub_theater_delete AFTER DELETE ON sub_theaters BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('sub_theater_changed',OLD.id,OLD.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_drama_profile_update AFTER UPDATE ON drama_profiles BEGIN
          INSERT INTO v2_change_events(change_type,drama_id,entity_id,updated_at) VALUES ('profile_changed',NEW.drama_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_drama_profile_insert AFTER INSERT ON drama_profiles BEGIN
          INSERT INTO v2_change_events(change_type,drama_id,entity_id,updated_at) VALUES ('profile_changed',NEW.drama_id,NEW.id,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_drama_profile_delete AFTER DELETE ON drama_profiles BEGIN
          INSERT INTO v2_change_events(change_type,drama_id,entity_id,updated_at) VALUES ('profile_changed',OLD.drama_id,OLD.id,OLD.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_settings_update AFTER UPDATE ON v2_settings BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('settings_changed',NEW.key,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_settings_insert AFTER INSERT ON v2_settings BEGIN
          INSERT INTO v2_change_events(change_type,entity_id,updated_at) VALUES ('settings_changed',NEW.key,NEW.updated_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_resource_insert AFTER INSERT ON resource_index BEGIN
          INSERT INTO v2_change_events(change_type,updated_at) VALUES ('resource_changed',NEW.last_seen_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_resource_update AFTER UPDATE ON resource_index BEGIN
          INSERT INTO v2_change_events(change_type,updated_at) VALUES ('resource_changed',NEW.last_seen_at);
        END;
        CREATE TRIGGER IF NOT EXISTS v2_evt_revenue_run_update AFTER UPDATE OF status ON v2_revenue_collection_runs
        WHEN NEW.status IN ('completed','failed') AND OLD.status<>NEW.status BEGIN
          INSERT INTO v2_change_events(change_type,updated_at) VALUES ('revenue_changed',NEW.updated_at);
        END;
    """)
    global REVENUE_RUNS_RECOVERED
    with REVENUE_RUN_RECOVERY_LOCK:
        if not REVENUE_RUNS_RECOVERED:
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute("""UPDATE v2_revenue_collection_runs SET status='failed', error_message='软件重启，未完成的收益采集已停止，请重新发起采集',
                finished_at=?, updated_at=? WHERE status IN ('queued', 'running')""", (now, now))
            REVENUE_RUNS_RECOVERED = True
    conn.commit()
    return conn


def connection() -> sqlite3.Connection:
    """Open a request connection without repeating schema writes.

    SQLite permits one writer at a time.  Running DDL, index creation and
    trigger installation for every HTTP request caused concurrently mounted
    V2 pages to block one another before they could perform ordinary reads.
    """
    global DATABASE_INITIALIZED_PATH
    path = db_path().resolve()
    with DATABASE_INITIALIZATION_LOCK:
        if DATABASE_INITIALIZED_PATH != path:
            conn = _initialize_connection()
            DATABASE_INITIALIZED_PATH = path
            return conn
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn


def clear_executor_trace(run_id: str) -> None:
    """Replace the previous diagnostic trail when one logical job is retried."""
    conn = connection()
    try:
        conn.execute("DELETE FROM executor_trace_events WHERE run_id=?", (run_id,))
        conn.commit()
    finally:
        conn.close()


def record_executor_trace(*, executor_id: str, run_id: str, production_task_id: str,
                          phase: str, message: str, detail: dict[str, object] | None = None,
                          created_at: str | None = None) -> None:
    """Persist a compact, user-readable progress trail for one executor run.

    The fixed per-run limit is deliberate: diagnostics must help a failed task
    without becoming a second unbounded log store.
    """
    conn = connection()
    try:
        conn.execute(
            "INSERT INTO executor_trace_events(id,executor_id,run_id,production_task_id,sequence_no,phase,message,detail_json,created_at) "
            "SELECT ?,?,?,?,?,?,?,?,?", (
                uuid.uuid4().hex, executor_id, run_id, production_task_id,
                int(conn.execute("SELECT COALESCE(MAX(sequence_no), 0) FROM executor_trace_events WHERE run_id=?", (run_id,)).fetchone()[0]) + 1,
                phase, message, json.dumps(detail or {}, ensure_ascii=False, sort_keys=True), created_at or now_text(),
            ),
        )
        conn.execute(
            "DELETE FROM executor_trace_events WHERE id IN ("
            "SELECT id FROM executor_trace_events WHERE run_id=? ORDER BY sequence_no DESC LIMIT -1 OFFSET ?)",
            (run_id, EXECUTOR_TRACE_LIMIT),
        )
        conn.commit()
    finally:
        conn.close()


def executor_trace_excerpt(run_id: str, *, limit: int = EXECUTOR_TRACE_LIMIT) -> str:
    """Return the bounded trace as plain text for the existing task drawer."""
    conn = connection()
    try:
        rows = conn.execute(
            "SELECT created_at, phase, message FROM executor_trace_events WHERE run_id=? "
            "ORDER BY sequence_no ASC LIMIT ?", (run_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return "\n".join(f"[{row['created_at']}] {row['phase']}：{row['message']}" for row in rows)


def purge_executor_traces_for_task(conn: sqlite3.Connection, task_id: str) -> None:
    """Use the production task's existing cleanup lifecycle for diagnostics too."""
    conn.execute("DELETE FROM executor_trace_events WHERE production_task_id=?", (task_id,))


def list_change_events(after_id: int | None, limit: int = 200) -> dict[str, object]:
    """Return lightweight ownership changes without returning business data."""
    conn = connection()
    try:
        latest = int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM v2_change_events").fetchone()[0])
        # A fresh desktop session starts at the current point. Its normal
        # cache-then-summary startup check already reconciles older changes.
        if after_id is None:
            return {"items": [], "latest_id": latest}
        rows = conn.execute(
            "SELECT id,change_type,production_task_id,task_id,account_id,drama_id,video_id,material_id,entity_id,updated_at "
            "FROM v2_change_events WHERE id>? ORDER BY id LIMIT ?", (after_id, max(1, min(limit, 500))),
        ).fetchall()
        return {"items": [dict(row) for row in rows], "latest_id": latest}
    finally:
        conn.close()


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
    try:
        ffprobe = resolve_ffprobe()
    except ToolResolutionError:
        ffprobe = None
    if ffprobe is not None:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False, **no_window_kwargs(),
            )
            duration = max(0.0, float((result.stdout or "").strip() or 0))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            duration = 0.0
    # Versioned cache name forces regeneration after thumbnail quality/frame rules change.
    thumbnail = DATA_ROOT / "cache" / "material-thumbnails" / f"{cache_key}-v3.jpg"
    try:
        ffmpeg = resolve_ffmpeg()
    except ToolResolutionError:
        ffmpeg = None
    if ffmpeg is not None and not thumbnail.is_file():
        try:
            thumbnail.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [ffmpeg, "-y", "-i", str(path), "-frames:v", "1", str(thumbnail)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False, **no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            thumbnail.unlink(missing_ok=True)
    return duration, str(thumbnail) if thumbnail.is_file() else ""


def probe_resource_metadata(path: Path, cache_key: str) -> tuple[float, str, str]:
    duration, thumbnail_path = probe_material(path, cache_key)
    resolution = ""
    try:
        ffprobe = resolve_ffprobe()
    except ToolResolutionError:
        ffprobe = None
    if ffprobe is not None:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False, **no_window_kwargs(),
            )
            value = (result.stdout or "").strip()
            if re.fullmatch(r"\d+x\d+", value):
                resolution = value
        except (OSError, subprocess.TimeoutExpired):
            pass
    return duration, resolution, thumbnail_path

def media_resolution(path: Path) -> str:
    try:
        ffprobe = resolve_ffprobe()
    except ToolResolutionError:
        return ""
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, check=False, **no_window_kwargs())
        value = (result.stdout or "").strip()
        return value if re.fullmatch(r"\d+x\d+", value) else ""
    except (OSError, subprocess.TimeoutExpired): return ""


def _file_identity(stat: os.stat_result) -> str:
    """Use the filesystem identity for a rename/move when Windows exposes it."""
    inode = int(getattr(stat, "st_ino", 0) or 0)
    return f"{int(getattr(stat, 'st_dev', 0) or 0)}:{inode}" if inode else ""


def _new_resource_id(path: Path, file_identity: str) -> str:
    stable_key = f"identity:{file_identity}" if file_identity else f"path:{path.resolve()}"
    return hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:24]


def _resource_index_row(resource_id: str, conn: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    owns_connection = conn is None
    conn = conn or connection()
    try:
        return conn.execute("SELECT * FROM resource_index WHERE resource_id=?", (resource_id,)).fetchone()
    finally:
        if owns_connection:
            conn.close()


def _find_resource_index_row(conn: sqlite3.Connection, path: Path, file_identity: str) -> sqlite3.Row | None:
    """Find by current path first, then preserve the record across a rename/move."""
    row = conn.execute("SELECT * FROM resource_index WHERE file_path=?", (str(path),)).fetchone()
    if row is not None:
        return row
    if file_identity:
        row = conn.execute(
            "SELECT * FROM resource_index WHERE file_identity=? ORDER BY source_present DESC, last_seen_at DESC LIMIT 1",
            (file_identity,),
        ).fetchone()
        if row is not None:
            return row
    return None


def _upsert_resource_index(*, resource_id: str, category: str, category_name: str, path: Path,
                           stat: os.stat_result, file_identity: str, duration: float | None,
                           resolution: str, thumbnail_path: str, probe_status: str,
                           probe_error: str = "", source_present: bool = True,
                           conn: sqlite3.Connection | None = None) -> None:
    owns_connection = conn is None
    conn = conn or connection()
    try:
        conn.execute(
            "INSERT INTO resource_index(resource_id,category,category_name,file_path,file_size_bytes,file_mtime_ns,file_identity,duration_seconds,resolution,thumbnail_path,probe_status,probe_error,last_seen_at,source_present) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(resource_id) DO UPDATE SET category=excluded.category,category_name=excluded.category_name,file_path=excluded.file_path,file_size_bytes=excluded.file_size_bytes,file_mtime_ns=excluded.file_mtime_ns,file_identity=excluded.file_identity,duration_seconds=excluded.duration_seconds,resolution=excluded.resolution,thumbnail_path=excluded.thumbnail_path,probe_status=excluded.probe_status,probe_error=excluded.probe_error,last_seen_at=excluded.last_seen_at,source_present=excluded.source_present",
            (resource_id, category, category_name, str(path), stat.st_size, stat.st_mtime_ns, file_identity, duration, resolution, thumbnail_path, probe_status, probe_error, now_text(), 1 if source_present else 0),
        )
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()


def _cleanup_missing_resource_index(active_ids: set[str], conn: sqlite3.Connection | None = None) -> None:
    """Remove short-lived thumbnails; retain reusable lead-video/BGM cache rows."""
    owns_connection = conn is None
    conn = conn or connection()
    try:
        rows = conn.execute("SELECT resource_id, category, thumbnail_path, source_present FROM resource_index").fetchall()
        for row in rows:
            resource_id = str(row["resource_id"])
            if resource_id in active_ids:
                continue
            category = str(row["category"])
            thumbnail = Path(str(row["thumbnail_path"] or ""))
            if category not in {"lead_video", "bgm"} and thumbnail.is_file():
                thumbnail.unlink(missing_ok=True)
                conn.execute("DELETE FROM resource_index WHERE resource_id=?", (resource_id,))
            elif int(row["source_present"]):
                conn.execute("UPDATE resource_index SET source_present=0,last_seen_at=? WHERE resource_id=?", (now_text(), resource_id))
        if owns_connection:
            conn.commit()
    finally:
        if owns_connection:
            conn.close()


def _process_resource_probe(resource_id: str, path: Path, file_identity: str, size_bytes: int, mtime_ns: int) -> None:
    """Run slow media inspection outside the HTTP request that lists resources."""
    try:
        duration, resolution, thumbnail_path = probe_resource_metadata(path, resource_id)
        status, error = "ready", ""
    except Exception as exc:  # One damaged file must never break the resource list.
        duration, resolution, thumbnail_path = None, "", ""
        status, error = "failed", str(exc)
    try:
        conn = connection()
        try:
            row = _resource_index_row(resource_id, conn)
            if row is None:
                return
            # Do not attach an old probe result after a file was replaced.
            if (str(row["file_identity"] or "") != file_identity
                    or int(row["file_size_bytes"]) != size_bytes
                    or int(row["file_mtime_ns"]) != mtime_ns):
                return
            conn.execute(
                "UPDATE resource_index SET duration_seconds=?, resolution=?, thumbnail_path=?, probe_status=?, probe_error=?, last_seen_at=? WHERE resource_id=?",
                (duration, resolution, thumbnail_path, status, error, now_text(), resource_id),
            )
            conn.commit()
        finally:
            conn.close()
    finally:
        with RESOURCE_PROBE_LOCK:
            RESOURCE_PROBE_PENDING.discard(resource_id)


def _resource_probe_loop() -> None:
    while True:
        resource_id, path, file_identity, size_bytes, mtime_ns = RESOURCE_PROBE_QUEUE.get()
        try:
            _process_resource_probe(resource_id, path, file_identity, size_bytes, mtime_ns)
        finally:
            RESOURCE_PROBE_QUEUE.task_done()


def queue_resource_probe(resource_id: str, path: Path, file_identity: str, stat: os.stat_result) -> None:
    """Queue at most one low-priority probe per resource; never block the page request."""
    global RESOURCE_PROBE_THREAD
    with RESOURCE_PROBE_LOCK:
        if resource_id in RESOURCE_PROBE_PENDING:
            return
        RESOURCE_PROBE_PENDING.add(resource_id)
        if RESOURCE_PROBE_THREAD is None or not RESOURCE_PROBE_THREAD.is_alive():
            RESOURCE_PROBE_THREAD = threading.Thread(target=_resource_probe_loop, name="V2ResourceProbe", daemon=True)
            RESOURCE_PROBE_THREAD.start()
        RESOURCE_PROBE_QUEUE.put((resource_id, path, file_identity, int(stat.st_size), int(stat.st_mtime_ns)))


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
        "release_status": str(task["release_status"] or "unregistered"),
        "actual_release_time": str(task["actual_release_time"] or ""),
        "release_province": str(task["release_province"] or ""),
        "release_city": str(task["release_city"] or ""),
        "release_district": str(task["release_district"] or ""),
        "release_detail_address": str(task["release_detail_address"] or ""),
        "final_video_manual_check": bool(task["final_video_manual_check"]),
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


def get_account(account_id: str) -> dict[str, object]:
    conn = connection()
    try:
        row = conn.execute("SELECT a.*, t.name AS theater_name FROM accounts a JOIN theaters t ON t.id=a.theater_id WHERE a.id=?", (account_id,)).fetchone()
        if not row:
            raise ValueError("账号不存在")
        return dict(row)
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
        task_matches_drama = """(p.drama_name=d.current_name OR EXISTS
            (SELECT 1 FROM drama_aliases da WHERE da.drama_id=d.id AND da.alias_name=p.drama_name))"""
        rows = conn.execute(f"""SELECT d.*, t.name AS theater_name,
            (SELECT COUNT(*) FROM production_tasks p WHERE {task_matches_drama}) AS production_count,
            (SELECT MAX(COALESCE(NULLIF(p.planned_publish_at, ''), p.created_at)) FROM production_tasks p WHERE {task_matches_drama}) AS last_scheduled_at,
            (SELECT COUNT(*) FROM production_tasks p WHERE {task_matches_drama} AND (
                EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=p.id AND j.status IN ('queued','dispatching','running','retry_requested'))
                OR EXISTS (SELECT 1 FROM production_video_tasks v WHERE v.task_id=p.id AND v.status IN ('pending_generation','generation_queued','generating'))
                OR EXISTS (SELECT 1 FROM export_jobs e WHERE e.production_task_id=p.id AND e.status IN ('queued','active'))
            )) AS active_production_count
            FROM dramas d JOIN theaters t ON t.id=d.theater_id
            ORDER BY active_production_count DESC, last_scheduled_at DESC, production_count DESC, d.current_name COLLATE NOCASE""").fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["history_names"] = [str(value[0]) for value in conn.execute("SELECT alias_name FROM drama_aliases WHERE drama_id=? ORDER BY created_at", (row["id"],)).fetchall()]
            items.append(item)
        return {"items": items}
    finally:
        conn.close()


def get_drama(drama_id: str) -> dict[str, object]:
    conn = connection()
    try:
        task_matches_drama = """(p.drama_name=d.current_name OR EXISTS
            (SELECT 1 FROM drama_aliases da WHERE da.drama_id=d.id AND da.alias_name=p.drama_name))"""
        row = conn.execute(f"""SELECT d.*, t.name AS theater_name,
            (SELECT COUNT(*) FROM production_tasks p WHERE {task_matches_drama}) AS production_count,
            (SELECT MAX(COALESCE(NULLIF(p.planned_publish_at, ''), p.created_at)) FROM production_tasks p WHERE {task_matches_drama}) AS last_scheduled_at,
            (SELECT COUNT(*) FROM production_tasks p WHERE {task_matches_drama} AND (
                EXISTS (SELECT 1 FROM template_jobs j WHERE j.task_id=p.id AND j.status IN ('queued','dispatching','running','retry_requested'))
                OR EXISTS (SELECT 1 FROM production_video_tasks v WHERE v.task_id=p.id AND v.status IN ('pending_generation','generation_queued','generating'))
                OR EXISTS (SELECT 1 FROM export_jobs e WHERE e.production_task_id=p.id AND e.status IN ('queued','active'))
            )) AS active_production_count
            FROM dramas d JOIN theaters t ON t.id=d.theater_id WHERE d.id=?""", (drama_id,)).fetchone()
        if not row:
            raise ValueError("剧集不存在")
        item = dict(row)
        item["history_names"] = [str(value[0]) for value in conn.execute("SELECT alias_name FROM drama_aliases WHERE drama_id=? ORDER BY created_at", (drama_id,)).fetchall()]
        return item
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


WECHAT_INDEX_KEYWORD_ROLES = {"primary", "equivalent", "related", "candidate", "rejected"}


def normalize_wechat_index_keyword(value: object) -> str:
    """Create a comparison key only; this never decides that scores can be added."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        raise ValueError("微信指数关键词不能为空")
    # Chinese titles often differ only by full-/half-width punctuation or spaces.
    # Retain this key solely for candidate review, never as an aggregation rule.
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def _wechat_index_keyword_row(conn: sqlite3.Connection, keyword_id: str) -> sqlite3.Row:
    row = conn.execute(
        """SELECT k.*, d.current_name AS drama_name FROM wechat_index_keywords k
           JOIN dramas d ON d.id=k.drama_id WHERE k.id=?""",
        (keyword_id,),
    ).fetchone()
    if not row:
        raise ValueError("微信指数关键词不存在")
    return row


def list_wechat_index_keywords(drama_id: str = "") -> dict[str, object]:
    conn = connection()
    try:
        clauses, params = [], []
        if drama_id:
            clauses.append("k.drama_id=?")
            params.append(drama_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"""SELECT k.*, d.current_name AS drama_name,
                (SELECT COUNT(*) FROM wechat_index_observations o WHERE o.keyword_id=k.id) AS observation_count,
                (SELECT MIN(ymd) FROM wechat_index_observations o WHERE o.keyword_id=k.id) AS first_observed_ymd,
                (SELECT MAX(ymd) FROM wechat_index_observations o WHERE o.keyword_id=k.id) AS last_observed_ymd
                FROM wechat_index_keywords k JOIN dramas d ON d.id=k.drama_id
                {where} ORDER BY d.current_name COLLATE NOCASE, CASE k.role WHEN 'primary' THEN 0 WHEN 'equivalent' THEN 1 WHEN 'related' THEN 2 WHEN 'candidate' THEN 3 ELSE 4 END, k.keyword COLLATE NOCASE""",
            params,
        ).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


def create_wechat_index_keyword(payload: dict[str, object]) -> dict[str, object]:
    drama_id = str(payload.get("drama_id") or "").strip()
    keyword = str(payload.get("keyword") or "").strip()
    role = str(payload.get("role") or "candidate").strip()
    if not drama_id:
        raise ValueError("请选择归属剧集")
    if role not in WECHAT_INDEX_KEYWORD_ROLES:
        raise ValueError("微信指数关键词角色无效")
    normalized = normalize_wechat_index_keyword(keyword)
    if len(keyword) > 100:
        raise ValueError("微信指数关键词不能超过 100 个字符")
    enabled = 1 if bool(payload.get("enabled", True)) else 0
    source = str(payload.get("source") or "manual")
    if source not in {"manual", "suggestion_import"}:
        raise ValueError("微信指数关键词来源无效")
    conn = connection()
    try:
        if not conn.execute("SELECT 1 FROM dramas WHERE id=?", (drama_id,)).fetchone():
            raise ValueError("归属剧集不存在")
        stamp = now_text()
        item = {"id": uuid.uuid4().hex, "drama_id": drama_id, "keyword": keyword, "normalized_keyword": normalized,
                "role": role, "enabled": enabled, "source": source, "created_at": stamp, "updated_at": stamp}
        conn.execute(
            """INSERT INTO wechat_index_keywords(id,drama_id,keyword,normalized_keyword,role,enabled,source,created_at,updated_at)
               VALUES (:id,:drama_id,:keyword,:normalized_keyword,:role,:enabled,:source,:created_at,:updated_at)""",
            item,
        )
        conn.commit()
        return item
    except sqlite3.IntegrityError as exc:
        raise ValueError("该剧集已经维护了相同的微信指数关键词") from exc
    finally:
        conn.close()


def update_wechat_index_keyword(keyword_id: str, payload: dict[str, object]) -> dict[str, object]:
    conn = connection()
    try:
        current = _wechat_index_keyword_row(conn, keyword_id)
        role = str(payload.get("role", current["role"]))
        if role not in WECHAT_INDEX_KEYWORD_ROLES:
            raise ValueError("微信指数关键词角色无效")
        raw_enabled = payload.get("enabled", current["enabled"])
        if not isinstance(raw_enabled, (bool, int)):
            raise ValueError("微信指数关键词启用状态无效")
        enabled = int(bool(raw_enabled))
        stamp = now_text()
        conn.execute("UPDATE wechat_index_keywords SET role=?,enabled=?,updated_at=? WHERE id=?", (role, enabled, stamp, keyword_id))
        conn.commit()
        return {**dict(current), "role": role, "enabled": enabled, "updated_at": stamp}
    finally:
        conn.close()


def _reject_wechat_index_secret_fields(value: object) -> None:
    if isinstance(value, dict):
        blocked = {"openid", "search_key", "cookie", "authorization", "token"}
        if blocked.intersection(str(key).casefold() for key in value):
            raise ValueError("原始响应中不能包含微信会话或认证参数")
        for nested in value.values():
            _reject_wechat_index_secret_fields(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_wechat_index_secret_fields(nested)


def _parse_wechat_index_history(response: object, expected_keyword: str) -> list[tuple[str, int]]:
    if not isinstance(response, dict):
        raise ValueError("微信指数历史响应不是对象")
    if response.get("code") != 0:
        code = response.get("code")
        message = str(response.get("msg") or response.get("message") or response.get("error") or "").strip().replace("\n", " ")[:160]
        suffix = f"：{message}" if message else ""
        raise ValueError(f"微信指数历史请求未成功（code={code}）{suffix}")
    index = response.get("index")
    resp_list = index.get("resp_list") if isinstance(index, dict) else None
    if not isinstance(resp_list, list):
        raise ValueError("微信指数历史响应缺少 index.resp_list")
    target = next((item for item in resp_list if isinstance(item, dict) and item.get("query") == expected_keyword), None)
    if not isinstance(target, dict):
        raise ValueError("历史响应与当前关键词不一致")
    if target.get("status") != 0:
        raise ValueError("微信指数未返回该关键词的可用历史数据")
    result: dict[str, int] = {}
    for channel in target.get("indexes", []):
        if not isinstance(channel, dict):
            continue
        for point in channel.get("time_indexes", []):
            if not isinstance(point, dict):
                continue
            raw_date, score = str(point.get("time") or ""), point.get("score")
            if not re.fullmatch(r"\d{8}", raw_date) or not isinstance(score, int) or score < 0:
                raise ValueError("微信指数历史数据中存在无效日期或指数")
            existing = result.get(raw_date)
            if existing is not None and existing != score:
                raise ValueError("微信指数历史响应包含冲突的同日指数")
            result[raw_date] = score
    if not result:
        raise ValueError("微信指数历史响应未包含逐日指数")
    return sorted(result.items())


def import_wechat_index_history(payload: dict[str, object], source_kind: str = "history_import") -> dict[str, object]:
    keyword_id = str(payload.get("keyword_id") or "").strip()
    response = payload.get("source_response")
    if not isinstance(response, dict):
        raise ValueError("需要提供微信指数原始响应对象")
    _reject_wechat_index_secret_fields(response)
    conn = connection()
    try:
        keyword = _wechat_index_keyword_row(conn, keyword_id)
        points = _parse_wechat_index_history(response, str(keyword["keyword"]))
        stamp = now_text()
        fetch_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO wechat_index_fetches(id,keyword_id,source_kind,response_json,received_at,created_at) VALUES (?,?,?,?,?,?)",
            (fetch_id, keyword_id, source_kind, json.dumps(response, ensure_ascii=False, separators=(",", ":")), stamp, stamp),
        )
        for ymd, score in points:
            conn.execute(
                """INSERT INTO wechat_index_observations(id,keyword_id,ymd,total_score,source_fetch_id,collected_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(keyword_id,ymd) DO UPDATE SET total_score=excluded.total_score,
                       source_fetch_id=excluded.source_fetch_id,collected_at=excluded.collected_at""",
                (uuid.uuid4().hex, keyword_id, ymd, score, fetch_id, stamp),
            )
        conn.commit()
        return {"keyword_id": keyword_id, "imported_points": len(points), "first_ymd": points[0][0], "last_ymd": points[-1][0], "fetch_id": fetch_id}
    finally:
        conn.close()


def wechat_index_connection_state() -> dict[str, object]:
    try:
        from server.wechat_index_client import connection_status
    except ModuleNotFoundError:
        from wechat_index_client import connection_status
    _, data_root = require_configured_paths()
    return connection_status(data_root)


def initialize_wechat_index_connection(payload: dict[str, object]) -> dict[str, object]:
    try:
        from server.wechat_index_client import save_connection_template
    except ModuleNotFoundError:
        from wechat_index_client import save_connection_template
    request_template = payload.get("request_template")
    _, data_root = require_configured_paths()
    return save_connection_template(data_root, request_template)


def collect_wechat_index_history(payload: dict[str, object]) -> dict[str, object]:
    # WeChat binds X-Request-Sign to the actual mini-program request. A saved
    # request cannot safely be replayed for another word. Collection therefore
    # happens only by ingesting a real, passively captured mini-program reply.
    raise ValueError("微信指数不支持静态重放采集。请先启动本机捕获，再在微信小程序查询该关键词；成功响应会自动入库。")


def wechat_index_capture_status() -> dict[str, object]:
    try:
        from server.wechat_index_proxy import capture_status
    except ModuleNotFoundError:
        from wechat_index_proxy import capture_status
    _, data_root = require_configured_paths()
    state = capture_status(data_root)
    state["ingested"] = ingest_wechat_index_capture_inbox(data_root)
    return state


def start_wechat_index_capture() -> dict[str, object]:
    try:
        from server.wechat_index_proxy import start_capture
    except ModuleNotFoundError:
        from wechat_index_proxy import start_capture
    _, data_root = require_configured_paths()
    return start_capture(data_root)


def stop_wechat_index_capture() -> dict[str, object]:
    try:
        from server.wechat_index_proxy import stop_capture
    except ModuleNotFoundError:
        from wechat_index_proxy import stop_capture
    _, data_root = require_configured_paths()
    return stop_capture(data_root)




def import_wechat_index_suggestions(payload: dict[str, object]) -> dict[str, object]:
    keyword_id = str(payload.get("keyword_id") or "").strip()
    response = payload.get("source_response")
    if not isinstance(response, dict) or response.get("code") != 0 or not isinstance(response.get("content"), list):
        raise ValueError("不是成功的微信指数联想词响应")
    _reject_wechat_index_secret_fields(response)
    conn = connection()
    try:
        keyword = _wechat_index_keyword_row(conn, keyword_id)
        if response.get("query") != keyword["keyword"]:
            raise ValueError("联想词响应与当前关键词不一致")
        stamp, inserted = now_text(), 0
        for value in response["content"]:
            suggested = str(value or "").strip()
            if not suggested or len(suggested) > 100:
                continue
            normalized = normalize_wechat_index_keyword(suggested)
            cursor = conn.execute(
                """INSERT INTO wechat_index_suggestions(id,keyword_id,suggested_keyword,normalized_keyword,normalization_match,source_response_json,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(keyword_id,suggested_keyword) DO UPDATE SET
                   normalized_keyword=excluded.normalized_keyword,normalization_match=excluded.normalization_match,
                   source_response_json=excluded.source_response_json,updated_at=excluded.updated_at""",
                (uuid.uuid4().hex, keyword_id, suggested, normalized, int(normalized == keyword["normalized_keyword"]),
                 json.dumps(response, ensure_ascii=False, separators=(",", ":")), stamp, stamp),
            )
            inserted += int(cursor.rowcount > 0)
        conn.commit()
        return {"keyword_id": keyword_id, "suggestion_count": inserted}
    finally:
        conn.close()


def ingest_wechat_index_capture_inbox(data_root: Path) -> dict[str, int]:
    """Match passively captured, signed WeChat responses to maintained words."""
    try:
        from server.wechat_index_client import capture_inbox_path
    except ModuleNotFoundError:
        from wechat_index_client import capture_inbox_path
    imported_history = imported_suggestions = ignored = 0
    inbox = capture_inbox_path(data_root)
    for file_path in sorted(inbox.glob("*.json"))[:50] if inbox.is_dir() else []:
        try:
            item = json.loads(file_path.read_text(encoding="utf-8"))
            if not isinstance(item, dict): raise ValueError("捕获文件无效")
            query = str(item.get("query") or "")
            kind = str(item.get("kind") or "")
            response = item.get("response")
            conn = connection()
            try:
                row = conn.execute("SELECT id FROM wechat_index_keywords WHERE keyword=?", (query,)).fetchone()
            finally:
                conn.close()
            if not row:
                ignored += 1
            elif kind == "history":
                import_wechat_index_history({"keyword_id": str(row["id"]), "source_response": response}, source_kind="collector")
                imported_history += 1
            elif kind == "suggestions":
                import_wechat_index_suggestions({"keyword_id": str(row["id"]), "source_response": response})
                imported_suggestions += 1
            else:
                ignored += 1
            file_path.unlink()
        except (OSError, ValueError, json.JSONDecodeError):
            # Leave malformed or temporarily incomplete captures for diagnosis;
            # never turn an ingest failure into zero-valued data.
            continue
    return {"history": imported_history, "suggestions": imported_suggestions, "ignored": ignored}


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
    roots = (("真人视频", "real_video", "真人视频", VIDEO_EXTENSIONS), ("真人图片", "real_image", "真人图片", IMAGE_EXTENSIONS), ("BGM", "bgm", "BGM", BGM_EXTENSIONS), ("引流视频", "lead_video", "引流视频", VIDEO_EXTENSIONS))
    items: list[dict[str, object]] = []
    active_ids: set[str] = set()
    probes_to_queue: list[tuple[str, Path, str, os.stat_result]] = []
    # This request only records filesystem changes. FFmpeg/FFprobe work happens
    # later in one background thread, so a large video import cannot hold the UI.
    with SCAN_LOCK:
        conn = connection()
        try:
            for folder, category, category_name, extensions in roots:
                root = WORKSPACE / "生成资源" / folder
                root.mkdir(parents=True, exist_ok=True)
                for path in sorted(root.rglob("*")):
                    if not path.is_file() or path.suffix.lower() not in extensions:
                        continue
                    stat = path.stat()
                    file_identity = _file_identity(stat)
                    indexed = _find_resource_index_row(conn, path, file_identity)
                    resource_id = str(indexed["resource_id"]) if indexed is not None else _new_resource_id(path, file_identity)
                    active_ids.add(resource_id)
                    unchanged = indexed is not None and int(indexed["file_size_bytes"]) == stat.st_size and int(indexed["file_mtime_ns"]) == stat.st_mtime_ns
                    duration_seconds = indexed["duration_seconds"] if unchanged and indexed is not None else None
                    resolution = str(indexed["resolution"] or "") if unchanged and indexed is not None else ""
                    thumbnail_path = str(indexed["thumbnail_path"] or "") if unchanged and indexed is not None else ""
                    probe_status = str(indexed["probe_status"] or "pending") if unchanged and indexed is not None else "pending"
                    probe_error = str(indexed["probe_error"] or "") if unchanged and indexed is not None else ""

                    if path.suffix.lower() in IMAGE_EXTENSIONS:
                        thumbnail_path, probe_status, probe_error = str(path.resolve()), "ready", ""
                    elif path.suffix.lower() not in VIDEO_EXTENSIONS:
                        probe_status, probe_error = "ready", ""
                    elif not unchanged or probe_status == "pending":
                        # A file is immediately visible with its name/size; details arrive later.
                        duration_seconds, resolution, thumbnail_path = None, "", ""
                        probe_status, probe_error = "pending", ""
                        probes_to_queue.append((resource_id, path, file_identity, stat))

                    changed = (indexed is None or not unchanged
                               or str(indexed["file_path"]) != str(path)
                               or str(indexed["category"]) != category
                               or str(indexed["file_identity"] or "") != file_identity
                               or not int(indexed["source_present"])
                               or probe_status != str(indexed["probe_status"] or "")
                               or thumbnail_path != str(indexed["thumbnail_path"] or ""))
                    if changed:
                        _upsert_resource_index(
                            resource_id=resource_id, category=category, category_name=category_name, path=path,
                            stat=stat, file_identity=file_identity, duration=duration_seconds, resolution=resolution,
                            thumbnail_path=thumbnail_path, probe_status=probe_status, probe_error=probe_error, conn=conn,
                        )
                    items.append({"id": resource_id, "name": path.name, "category": category, "categoryName": category_name, "filePath": str(path), "fileSizeMb": round(stat.st_size / 1024 / 1024, 2), "status": "used" if category != "lead_video" and path.name.startswith("已使用") else "available", "addedAt": date.fromtimestamp(stat.st_mtime).isoformat(), "tags": [], "durationSeconds": duration_seconds, "resolution": resolution, "thumbnailUrl": f"/api/v2/production-resources/{resource_id}/thumbnail" if thumbnail_path else "", "mediaUrl": f"/api/v2/production-resources/{resource_id}/media" if path.suffix.lower() in VIDEO_EXTENSIONS or path.suffix.lower() in IMAGE_EXTENSIONS else "", "probeStatus": probe_status, "probeError": probe_error})
            _cleanup_missing_resource_index(active_ids, conn)
            conn.commit()
        finally:
            conn.close()
    for resource_id, path, file_identity, stat in probes_to_queue:
        queue_resource_probe(resource_id, path, file_identity, stat)
    return {"items": items}


def production_resource_media(resource_id: str, *, thumbnail: bool = False) -> Path:
    """Resolve a scanned resource by id, constrained to the configured workspace."""
    indexed = _resource_index_row(resource_id)
    if indexed and thumbnail:
        source = Path(str(indexed["file_path"] or ""))
        try:
            source_stat = source.stat()
        except OSError:
            source_stat = None
        candidate = Path(str(indexed["thumbnail_path"] or "")).resolve()
        if (source_stat is not None and int(indexed["file_size_bytes"]) == source_stat.st_size
                and int(indexed["file_mtime_ns"]) == source_stat.st_mtime_ns
                and candidate.is_file() and candidate.is_relative_to(WORKSPACE.resolve())):
            return candidate
    roots = ("真人视频", "真人图片", "BGM", "引流视频")
    for folder in roots:
        root = (WORKSPACE / "生成资源" / folder).resolve()
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:24] != resource_id:
                continue
            if thumbnail:
                stat = path.stat()
                current = _resource_index_row(resource_id)
                if current and int(current["file_size_bytes"]) == stat.st_size and int(current["file_mtime_ns"]) == stat.st_mtime_ns:
                    thumbnail_path = str(current["thumbnail_path"] or "")
                else:
                    duration, resolution, thumbnail_path = probe_resource_metadata(path, resource_id)
                    _upsert_resource_index(resource_id=resource_id, category=str(current["category"] if current else "lead_video"), category_name=str(current["category_name"] if current else "引流视频"), path=path, stat=stat, file_identity=_file_identity(stat), duration=duration, resolution=resolution, thumbnail_path=thumbnail_path, probe_status="ready")
                candidate = Path(thumbnail_path) if thumbnail_path else Path()
                if candidate.is_file():
                    return candidate.resolve()
                raise ValueError("资源缩略图不存在")
            return path.resolve()
    raise ValueError("生产资源不存在")


DEFAULT_SETTINGS = {
    "data_drive": "",
    "data_root_dir": "",
    "raw_material_retention_days": 7,
    "short_term_cleanup_hours": 24,
    "publish_presets": ["12:00", "18:30", "19:45", "21:00"],
    "publish_date_offset_days": 0,
    "jianying_executable": "",
    "jianying_draft_root": "",
    "jianying_user_data_root": "",
    "template_timeout_min": 15,
    "final_generation_timeout_min": 30,
    "video_export_timeout_min": 20,
    "final_video_manual_check": False,
    "video_export_debug": False,
    "revenue_auto_collection_enabled": True,
    "revenue_auto_collection_times": ["06:00", "12:30", "18:00"],
    "local_vision_ai_mode": "compatibility",
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
    for key in ("jianying_executable", "jianying_draft_root", "jianying_user_data_root"):
        if not isinstance(values[key], str):
            raise ValueError("剪映路径设置格式不正确")
    executable = str(values["jianying_executable"]).strip()
    draft_root = str(values["jianying_draft_root"]).strip()
    user_data_root = str(values["jianying_user_data_root"]).strip()
    if executable and (not Path(executable).is_file() or Path(executable).suffix.lower() != ".exe"):
        raise ValueError("剪映程序路径必须是存在的 .exe 文件")
    if draft_root and not Path(draft_root).is_dir():
        raise ValueError("剪映草稿目录必须是存在的文件夹")
    if user_data_root and not Path(user_data_root).is_dir():
        raise ValueError("剪映用户数据目录必须是存在的文件夹")
    if not isinstance(values["template_timeout_min"], int) or not 1 <= values["template_timeout_min"] <= 120:
        raise ValueError("模板生成超时时间必须为 1-120 分钟")
    if not isinstance(values["final_generation_timeout_min"], int) or not 1 <= values["final_generation_timeout_min"] <= 180:
        raise ValueError("成片生成超时时间必须为 1-180 分钟")
    if not isinstance(values["video_export_timeout_min"], int) or not 1 <= values["video_export_timeout_min"] <= 120:
        raise ValueError("视频导出超时时间必须为 1-120 分钟")
    if not isinstance(values["revenue_auto_collection_enabled"], bool):
        raise ValueError("收益自动采集开关必须是布尔值")
    if values["local_vision_ai_mode"] not in {"compatibility", "quality", "disabled"}:
        raise ValueError("本地视觉 AI 模式不正确")
    if (not isinstance(values["revenue_auto_collection_times"], list)
            or not values["revenue_auto_collection_times"]
            or not all(isinstance(item, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in values["revenue_auto_collection_times"])
            or len(set(values["revenue_auto_collection_times"])) != len(values["revenue_auto_collection_times"])):
        raise ValueError("收益自动采集时间必须是互不重复的 HH:MM 时间点")
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
        account_row = conn.execute("SELECT status FROM accounts WHERE nickname=?", (account,)).fetchone()
        if account_row and str(account_row["status"]) != "正常":
            raise ValueError("只有正常账号可以安排生产任务")
        same_identity = conn.execute(
            "SELECT * FROM production_tasks WHERE created_date=? AND account_name=? AND drama_name=?",
            (created_date, account, drama),
        ).fetchone()
        if same_identity:
            return task_response(same_identity)
        conn.execute(
            """
            INSERT INTO production_tasks (
                id, source_id, created_date, account_name, drama_name, root_path, material_path,
                template_path, final_path, planned_publish_at, status, final_video_manual_check, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, source_id, created_date, account, drama, str(root), str(materials), str(template), str(finals), planned_publish_at, "materials_pending", int(bool(get_v2_settings()["final_video_manual_check"])), stamp, stamp),
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


def ensure_export_job_for_template(template_row: object, *, draft_path: Path) -> dict[str, object]:
    """Create the automatic template-video export job once a draft is ready."""
    task_id = str(template_row["task_id"])  # type: ignore[index]
    subject_id = str(template_row["id"])  # type: ignore[index]
    from server.v2_exporter.core import ExportRepository
    conn = connection()
    try:
        existing = conn.execute("SELECT * FROM export_jobs WHERE subject_type='template' AND subject_id=?", (subject_id,)).fetchone()
        if existing:
            job = dict(existing)
            attempts = conn.execute("SELECT 1 FROM export_attempts WHERE job_id=? LIMIT 1", (str(existing["id"]),)).fetchone()
            if not attempts and str(existing["status"]) == "ready":
                settings = get_v2_settings()
                ExportRepository(conn).queue_new_attempt(
                    str(existing["id"]),
                    deadline_minutes=int(settings["video_export_timeout_min"]),
                    debug_enabled=bool(settings["video_export_debug"]),
                )
                job = ExportRepository(conn).job(str(existing["id"]))
            return {"job": job, "target_path": str(job["target_path"])}
        task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("模板任务所属生产任务不存在，无法创建导出任务")
        group = Path(str(task["template_path"]))
        filename = f"{safe_component(str(task['created_date']), '日期')}-{safe_component(str(task['account_name']), '账号')}-{safe_component(str(task['drama_name']), '剧集')}-模板.mp4"
        job = ExportRepository(conn).create_job(
            production_task_id=task_id, subject_type="template", subject_id=subject_id,
            draft_name=str(template_row["draft_name"]), draft_path=str(draft_path.resolve()),
            target_path=str((group / filename).resolve()), manual_check_required=False,
        )
        settings = get_v2_settings()
        ExportRepository(conn).queue_new_attempt(
            str(job["id"]),
            deadline_minutes=int(settings["video_export_timeout_min"]),
            debug_enabled=bool(settings["video_export_debug"]),
        )
        job = ExportRepository(conn).job(str(job["id"]))
        return {"job": job, "target_path": job["target_path"]}
    finally:
        conn.close()


def ensure_export_job_for_finished_video(video_row: object, *, draft_name: str, draft_path: Path) -> dict[str, object]:
    """Queue the first export attempt for one completed finished-video draft."""
    task_id = str(video_row["task_id"])  # type: ignore[index]
    video_id = str(video_row["id"])  # type: ignore[index]
    conn = connection()
    try:
        from server.v2_exporter.core import ExportRepository
        existing = conn.execute("SELECT * FROM export_jobs WHERE subject_type='final' AND subject_id=?", (video_id,)).fetchone()
        if existing:
            job = dict(existing)
            attempts = conn.execute("SELECT 1 FROM export_attempts WHERE job_id=? LIMIT 1", (str(existing["id"]),)).fetchone()
            if not attempts and str(existing["status"]) == "ready":
                settings = get_v2_settings()
                ExportRepository(conn).queue_new_attempt(str(existing["id"]), deadline_minutes=int(settings["video_export_timeout_min"]), debug_enabled=bool(settings["video_export_debug"]))
                job = ExportRepository(conn).job(str(existing["id"]))
            return {"job": job, "target_path": str(job["target_path"])}
        task = conn.execute(
            "SELECT t.final_path, t.drama_name, f.sequence_no FROM production_tasks t "
            "JOIN production_video_tasks v ON v.task_id=t.id "
            "JOIN production_files f ON f.id=v.source_material_id WHERE v.id=?",
            (video_id,),
        ).fetchone()
        if not task:
            raise ValueError("成片任务所属生产任务不存在，无法创建导出任务")
        sequence_no = task["sequence_no"]
        if sequence_no is None:
            raise ValueError("成片素材缺少序号，无法确定正式视频名称")
        output_stem = safe_component(f"{task['drama_name']}-{int(sequence_no)}", "成片视频名称")
        output = Path(str(task["final_path"])) / f"{output_stem}.mp4"
        job = ExportRepository(conn).create_job(
            production_task_id=task_id, subject_type="final", subject_id=video_id,
            draft_name=draft_name, draft_path=str(draft_path.resolve()), target_path=str(output.resolve()),
            manual_check_required=bool(get_v2_settings()["final_video_manual_check"]),
        )
        settings = get_v2_settings()
        ExportRepository(conn).queue_new_attempt(str(job["id"]), deadline_minutes=int(settings["video_export_timeout_min"]), debug_enabled=bool(settings["video_export_debug"]))
        job = ExportRepository(conn).job(str(job["id"]))
        return {"job": job, "target_path": str(job["target_path"])}
    finally:
        conn.close()


def requeue_finished_video(video_id: str) -> dict[str, str]:
    """Stop and clean a finished-video run, then return it to the queue."""
    from server.final_engine.runner import cancel_finished_video, _final_work_dir
    conn = connection()
    try:
        row = conn.execute(
            "SELECT v.status, v.draft_path, v.output_path, v.task_id, f.sequence_no, t.created_date, t.account_name, t.drama_name "
            "FROM production_video_tasks v JOIN production_tasks t ON t.id=v.task_id JOIN production_files f ON f.id=v.source_material_id WHERE v.id=?",
            (video_id,),
        ).fetchone()
        if not row:
            raise ValueError("成片生成任务不存在")
        if str(row["status"]) not in {"generation_queued", "generating", "generation_failed", "generation_timeout"}:
            raise ValueError("当前成片任务不支持重新执行")
        cancel_finished_video(video_id)
        # The cancelled worker must release its executor pointer immediately;
        # its late callback is intentionally ignored by the run token guard.
        conn.execute(
            "UPDATE executor_controls SET current_task_id='', control_state=CASE WHEN pause_requested THEN 'manual_paused' ELSE 'idle' END, updated_at=? "
            "WHERE executor_id='final_generator' AND current_task_id=?",
            (now_text(), video_id),
        )
        task = conn.execute("SELECT root_path FROM production_tasks WHERE id=?", (str(row["task_id"]),)).fetchone()
        if task:
            shutil.rmtree(_final_work_dir(task_root=Path(str(task["root_path"])), video_id=video_id), ignore_errors=True)
        old_draft = Path(str(row["draft_path"] or ""))
        draft_root = Path(str(get_v2_settings().get("jianying_draft_root") or "")).expanduser()
        if old_draft.is_dir():
            try:
                if draft_root.is_dir() and old_draft.resolve().is_relative_to(draft_root.resolve()):
                    shutil.rmtree(old_draft, ignore_errors=True)
            except OSError:
                pass
        # A previous run can have produced a draft but failed before writing
        # its path back to SQLite. Remove only this task's numbered draft
        # variants so the next run cannot be mistaken for an existing one.
        if draft_root.is_dir() and row["sequence_no"] is not None:
            prefix = f"{row['created_date']}-{row['account_name']}-{row['drama_name']}-成片-{int(row['sequence_no'])}"
            for candidate in draft_root.glob(prefix + "*"):
                if candidate.is_dir():
                    shutil.rmtree(candidate, ignore_errors=True)
        conn.execute("UPDATE production_video_tasks SET status='pending_generation', draft_path='', error_message='', started_at='', finished_at='', updated_at=? WHERE id=?", (now_text(), video_id))
        conn.commit()
        return {"id": video_id, "status": "pending_generation"}
    finally:
        conn.close()


def requeue_export_attempt(attempt_id: str) -> dict[str, object]:
    """Create exactly one new export attempt for a completed or failed task-center card."""
    from server.v2_exporter.core import ExportRepository
    conn = connection()
    try:
        attempt = conn.execute("SELECT job_id FROM export_attempts WHERE id=?", (attempt_id,)).fetchone()
        if not attempt:
            raise ValueError("视频导出尝试不存在")
        settings = get_v2_settings()
        return ExportRepository(conn).queue_new_attempt(
            str(attempt["job_id"]), deadline_minutes=int(settings["video_export_timeout_min"]), debug_enabled=bool(settings["video_export_debug"]),
        )
    finally:
        conn.close()


def start_export_job(job_id: str) -> dict[str, object]:
    """The testable real-entry point: queue exactly one V2 attempt and run it."""
    from server.executor_management import ExecutorManager
    from server.jianying_preflight import require_jianying_ready
    from server.v2_exporter.core import ExportRepository
    from server.v2_exporter.runner import start_attempt_in_background
    conn = connection()
    try:
        control = ExecutorManager(conn).state("video_exporter")
        if bool(control["is_paused"]):
            raise ValueError("视频导出器已因连续失败暂停，请在任务中心人工重新启动")
        settings = get_v2_settings()
        require_jianying_ready(settings)
        attempt = ExportRepository(conn).queue_new_attempt(job_id, deadline_minutes=int(settings["video_export_timeout_min"]), debug_enabled=bool(settings["video_export_debug"]))
    finally:
        conn.close()
    start_attempt_in_background(connection, attempt_id=str(attempt["id"]), settings=settings)
    return {"attempt": attempt}


_ACTIVE_EXPORT_ATTEMPTS = {"preparing", "awaiting_human_check", "submitting", "observing_output", "finalizing"}


def _executor_current_tasks(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["executor_id"]): str(row["current_task_id"] or "")
        for row in conn.execute(
            "SELECT executor_id, current_task_id FROM executor_controls "
            "WHERE executor_id IN ('template_generator','final_generator','video_exporter')"
        ).fetchall()
    }


def _final_display_status(video: object, *, final_current_id: str, exporter_current_id: str,
                          output_exists: bool) -> str:
    """Return the sole user-facing state for one submitted finished-video task."""
    raw = str(video["status"] or "")
    attempt_id = str(video["export_attempt_id"] or "")
    export = str(video["export_status"] or "")
    if export == "completed":
        return "video_exported" if output_exists else "video_error"
    if export in {"failed", "timeout"}:
        return "video_error"
    # The executor claim is the source of truth for “导出中”, including the
    # short handoff before the attempt changes from queued to preparing.
    if attempt_id and attempt_id == exporter_current_id:
        return "video_exporting"
    if export == "queued":
        return "video_queued"
    if export in _ACTIVE_EXPORT_ATTEMPTS:
        return "video_error"  # an active attempt without its owner is unsafe to misreport
    if raw in {"generation_failed", "generation_timeout", "error"}:
        return "draft_error"
    if str(video["id"]) == final_current_id or raw == "generating":
        return "draft_generating"
    if raw in {"pending_generation", "generation_queued"}:
        return "draft_queued"
    if raw == "draft_ready":
        return "draft_ready"
    return "draft_error"


def _template_display_status(template: dict[str, object] | None, *, template_current_id: str,
                             exporter_current_id: str) -> str:
    if not template:
        return "not_generated"
    raw = str(template.get("status") or "")
    export = str(template.get("export_status") or "")
    attempt_id = str(template.get("export_attempt_id") or "")
    if export == "completed":
        return "video_ready" if Path(str(template.get("video_path") or "")).is_file() and Path(str(template.get("pairing_path") or "")).is_file() else "video_error"
    if export in {"failed", "timeout"}:
        return "video_error"
    if attempt_id and attempt_id == exporter_current_id:
        return "video_exporting"
    if export == "queued":
        return "video_queued"
    if export in _ACTIVE_EXPORT_ATTEMPTS:
        return "video_error"
    if raw in {"error", "timeout"}:
        return "draft_error"
    if raw == "retry_requested":
        return "draft_retrying"
    if str(template.get("id") or "") == template_current_id or raw == "running":
        return "draft_generating"
    if raw in {"queued", "dispatching"}:
        return "draft_queued"
    if raw == "draft_ready":
        return "draft_ready"
    return "draft_error"


def _task_display_status(*, task: sqlite3.Row, material_count: int, pending_material_count: int,
                         final_statuses: list[str], template_status: str) -> str:
    """Aggregate only the task-card lifecycle; item-level phases stay on the right."""
    if str(task["release_status"] or "unregistered") == "registered":
        return "released"
    active = {"draft_generating", "video_exporting", "draft_queued", "video_queued", "draft_ready"}
    if any(status in active for status in final_statuses):
        return "final_processing"
    if any(status in {"draft_error", "video_error"} for status in final_statuses):
        return "action_required"
    if material_count and len(final_statuses) == material_count and all(status == "video_exported" for status in final_statuses):
        return "awaiting_release"
    if template_status == "video_ready":
        return "awaiting_final_generation"
    if template_status in {"draft_queued", "draft_generating", "draft_retrying", "draft_ready", "video_queued", "video_exporting"}:
        return "template_processing"
    if template_status in {"draft_error", "video_error"}:
        return "template_error"
    if material_count:
        return "awaiting_template"
    return "awaiting_scan" if pending_material_count else "awaiting_material"


def list_tasks(task_id: str | None = None) -> dict[str, object]:
    conn = connection()
    try:
        items: list[dict[str, object]] = []
        current_tasks = _executor_current_tasks(conn)
        if task_id:
            rows = conn.execute(
                "SELECT * FROM production_tasks WHERE id=? AND COALESCE(cleanup_status, 'active')='active'",
                (task_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM production_tasks WHERE COALESCE(cleanup_status, 'active')='active' ORDER BY created_at DESC"
            ).fetchall()
        for row in rows:
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
                    "resolution": str(file["resolution"] or ""),
                    "scanned_at": str(file["updated_at"]),
                    "status": str(file["status"]),
                }
                for file in material_rows
                if Path(str(file["file_path"])).is_file()
            ]
            video_rows = conn.execute(
                "SELECT v.*, f.sequence_no, f.file_name, f.file_path, f.size_bytes, f.duration_seconds AS source_duration_seconds, "
                "f.original_name, "
                "j.id AS export_job_id, j.status AS export_job_status, j.target_path AS export_target_path, "
                "a.id AS export_attempt_id, a.status AS export_status, a.error_message AS export_error_message, "
                "a.started_at AS export_started_at, a.finished_at AS export_finished_at "
                "FROM production_video_tasks v "
                "JOIN production_files f ON f.id=v.source_material_id "
                "LEFT JOIN export_jobs j ON j.id=(SELECT candidate.id FROM export_jobs candidate "
                " WHERE candidate.subject_type='final' AND candidate.subject_id=v.id "
                " ORDER BY candidate.created_at DESC LIMIT 1) "
                "LEFT JOIN export_attempts a ON a.job_id=j.id AND a.attempt_no=(SELECT MAX(latest.attempt_no) "
                " FROM export_attempts latest WHERE latest.job_id=j.id) "
                "WHERE v.task_id=? AND f.status='available' "
                "AND v.status NOT IN ('cancelled', 'cancellation_requested', 'invalidated') "
                "ORDER BY f.sequence_no, f.file_name",
                (str(row["id"]),),
            ).fetchall()
            item["videos"] = []
            for video in video_rows:
                if not Path(str(video["file_path"])).is_file():
                    continue
                recorded_output = Path(str(video["output_path"] or ""))
                export_target = Path(str(video["export_target_path"] or ""))
                formal_output = _resolve_recorded_video_path(Path(str(row["final_path"])), recorded_output, export_target, str(row["drama_name"]), video["sequence_no"])
                output_exists = formal_output.is_file()
                display_status = _final_display_status(
                    video, final_current_id=current_tasks.get("final_generator", ""),
                    exporter_current_id=current_tasks.get("video_exporter", ""), output_exists=output_exists,
                )
                item["videos"].append({
                    "id": str(video["id"]),
                    "source_material_id": str(video["source_material_id"]),
                    "status": str(video["status"]),
                    "error_message": str(video["error_message"] or ""),
                    "generation_started_at": str(video["started_at"] or ""),
                    "generation_finished_at": str(video["finished_at"] or ""),
                    "sequence_no": video["sequence_no"],
                    "name": str(video["file_name"]),
                    "original_name": str(video["original_name"] or video["file_name"]),
                    "size_bytes": int(video["size_bytes"]),
                    "source_duration_seconds": float(video["source_duration_seconds"] or 0),
                    "draft_path": str(video["draft_path"]),
                    "output_path": str(formal_output) if output_exists else str(video["output_path"] or ""),
                    "output_exists": output_exists,
                    "output_size_bytes": formal_output.stat().st_size if output_exists else 0,
                    "export_job_id": str(video["export_job_id"] or ""),
                    "export_attempt_id": str(video["export_attempt_id"] or ""),
                    "export_status": str(video["export_status"] or ""),
                    "export_job_status": str(video["export_job_status"] or ""),
                    "export_error_message": str(video["export_error_message"] or ""),
                    "export_started_at": str(video["export_started_at"] or ""),
                    "export_finished_at": str(video["export_finished_at"] or ""),
                    "output_duration_seconds": _verified_export_duration(conn, str(video["export_attempt_id"] or "")),
                    "display_status": display_status,
                }
                )
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
                export = conn.execute(
                    "SELECT j.id AS export_job_id, j.status AS export_job_status, j.target_path, a.id AS export_attempt_id, a.status AS export_status, a.error_code, a.error_message, a.started_at AS export_started_at, a.finished_at AS export_finished_at "
                    "FROM export_jobs j LEFT JOIN export_attempts a ON a.job_id=j.id AND a.attempt_no=(SELECT MAX(x.attempt_no) FROM export_attempts x WHERE x.job_id=j.id) "
                    "WHERE j.subject_type='template' AND j.subject_id=? ORDER BY j.created_at DESC LIMIT 1", (str(template["id"]),)
                ).fetchone()
                if export:
                    template_item["export_job_id"] = str(export["export_job_id"])
                    template_item["export_attempt_id"] = str(export["export_attempt_id"] or "")
                    export_status = str(export["export_status"] or export["export_job_status"] or "")
                    if "TIMEOUT" in str(export["error_code"] or "").upper():
                        export_status = "timeout"
                    template_item["export_status"] = export_status
                    template_item["export_error_message"] = str(export["error_message"] or "")
                    template_item["export_error_code"] = str(export["error_code"] or "")
                    template_item["export_target_path"] = str(export["target_path"] or "")
                    template_item["export_file_name"] = Path(str(export["target_path"] or "")).name
                    template_item["export_duration_seconds"], template_item["export_duration_formatted"] = _template_duration(str(export["export_started_at"] or ""), str(export["export_finished_at"] or ""))
                    target = Path(str(export["target_path"] or ""))
                    template_item["export_file_size_bytes"] = target.stat().st_size if target.is_file() else 0
                    template_item["video_duration_seconds"] = _verified_export_duration(conn, str(export["export_attempt_id"] or ""))
            else:
                item["template"] = None
            item["pending_material_count"] = pending_material_count
            template_status = _template_display_status(
                item["template"] if isinstance(item["template"], dict) else None,
                template_current_id=current_tasks.get("template_generator", ""),
                exporter_current_id=current_tasks.get("video_exporter", ""),
            )
            item["template_display_status"] = template_status
            item["task_display_status"] = _task_display_status(
                task=row, material_count=len(item["materials"]), pending_material_count=pending_material_count,
                final_statuses=[str(video["display_status"]) for video in item["videos"]], template_status=template_status,
            )
            items.append(item)
        return {"items": items}
    finally:
        conn.close()


def list_task_summaries() -> dict[str, object]:
    """Return only the fields needed to render production task cards.

    Heavy material/video path inspection stays in list_tasks() and is loaded
    only after the user opens a specific production task.
    """
    # Status has to come from the same canonical resolver as the detail pane.
    # The old SQL-only aggregate duplicated part of the state machine and was
    # the source of contradictory card/detail labels.
    details = list_tasks()["items"]
    items: list[dict[str, object]] = []
    for detail in details:
        videos = list(detail.get("videos") or [])
        statuses = [str(video.get("display_status") or "") for video in videos]
        material_count = int(detail.get("materials_count") or len(detail.get("materials") or []))
        item = dict(detail)
        item.update({
            "materials": [], "videos": [],
            "videos_count": len(videos),
            "draft_count": sum(status in {"draft_ready", "video_queued", "video_exporting", "video_exported", "video_error"} for status in statuses),
            "draft_queued_count": sum(status == "draft_queued" for status in statuses),
            "draft_generating_count": sum(status == "draft_generating" for status in statuses),
            "export_queued_count": sum(status == "video_queued" for status in statuses),
            "exporting_count": sum(status == "video_exporting" for status in statuses),
            "exported_count": sum(status == "video_exported" for status in statuses),
            "error_count": sum(status in {"draft_error", "video_error"} for status in statuses),
            "materials_count": material_count,
        })
        items.append(item)
    return {"items": items}


def get_task_details(task_id: str) -> dict[str, object]:
    for item in list_tasks(task_id)["items"]:
        if str(item.get("id")) == task_id:
            return item
    raise ValueError("生产任务不存在")


def list_release_addresses(account_name: str) -> dict[str, object]:
    conn = connection()
    try:
        rows = conn.execute("SELECT province, city, district, detail_address, use_count, last_used_at FROM release_address_history WHERE account_name=? ORDER BY use_count DESC, last_used_at DESC", (account_name,)).fetchall()
        all_rows = conn.execute("SELECT province, city, district, detail_address, SUM(use_count) AS use_count, MAX(last_used_at) AS last_used_at FROM release_address_history GROUP BY normalized_key ORDER BY use_count DESC, last_used_at DESC").fetchall()
        def item(row: sqlite3.Row) -> dict[str, object]:
            return {"province": str(row["province"]), "city": str(row["city"]), "district": str(row["district"]), "detail_address": str(row["detail_address"]), "use_count": int(row["use_count"] or 0), "last_used_at": str(row["last_used_at"] or "")}
        return {"account": [item(row) for row in rows], "public": [item(row) for row in all_rows]}
    finally:
        conn.close()


def register_release(task_id: str, payload: object) -> dict[str, object]:
    data = payload if isinstance(payload, dict) else {"actual_release_time": str(payload or "")}
    actual = str(data.get("actual_release_time") or "").strip()
    province = str(data.get("province") or "").strip()
    city = str(data.get("city") or "").strip()
    district = str(data.get("district") or "").strip()
    detail = str(data.get("detail_address") or "").strip()
    if not actual:
        raise ValueError("请输入实际发布日期和时间")
    conn = connection()
    try:
        task = conn.execute("SELECT id FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("生产任务不存在")
        pending = conn.execute(
            "SELECT COUNT(*) FROM production_video_tasks v JOIN production_files f ON f.id=v.source_material_id "
            "WHERE v.task_id=? AND f.status='available' AND "
            "(v.status!='draft_ready' OR v.output_path='' OR NOT EXISTS "
            "(SELECT 1 FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id "
            "WHERE j.subject_type='final' AND j.subject_id=v.id AND a.status='completed'))",
            (task_id,),
        ).fetchone()[0]
        if int(pending) > 0:
            raise ValueError("还有成片没有导出完成，暂不能登记发布")
        account_name = str(conn.execute("SELECT account_name FROM production_tasks WHERE id=?", (task_id,)).fetchone()[0])
        if not all((province, city, district, detail)):
            raise ValueError("请填写完整的发布地址")
        normalized = "|".join(re.sub(r"[\s　]+", "", value).casefold() for value in (province, city, district, detail))
        stamp = now_text()
        conn.execute("INSERT INTO release_address_history (id,account_name,province,city,district,detail_address,normalized_key,use_count,first_used_at,last_used_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_name,normalized_key) DO UPDATE SET use_count=use_count+1,last_used_at=excluded.last_used_at", (uuid.uuid4().hex, account_name, province, city, district, detail, normalized, 1, stamp, stamp))
        released = datetime.fromisoformat(actual.replace('T', ' '))
        settings = get_v2_settings()
        process_at = (released + timedelta(hours=int(settings["short_term_cleanup_hours"]))).isoformat(sep=' ')
        raw_at = (released + timedelta(days=int(settings["raw_material_retention_days"]))).isoformat(sep=' ')
        conn.execute("UPDATE production_tasks SET release_status='registered', actual_release_time=?, release_province=?, release_city=?, release_district=?, release_detail_address=?, process_cleanup_at=?, raw_cleanup_at=?, cleanup_status='active', updated_at=? WHERE id=?", (actual, province, city, district, detail, process_at, raw_at, now_text(), task_id))
        conn.commit()
        return {"id": task_id, "release_status": "registered", "actual_release_time": actual, "province": province, "city": city, "district": district, "detail_address": detail}
    finally:
        conn.close()


def revoke_release(task_id: str) -> dict[str, object]:
    conn = connection()
    try:
        # Keep the last actual release information so the next registration
        # opens with the previous values for quick correction/reuse.
        row = conn.execute("SELECT cleanup_status FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if row and str(row["cleanup_status"] or "active") != "active":
            raise ValueError("该任务已清理，不能撤销发布登记")
        updated = conn.execute("UPDATE production_tasks SET release_status='unregistered', updated_at=? WHERE id=?", (now_text(), task_id)).rowcount
        if not updated:
            raise ValueError("生产任务不存在")
        conn.commit()
        return {"id": task_id, "release_status": "unregistered", "actual_release_time": ""}
    finally:
        conn.close()

def _cleanup_file_items(paths: list[Path]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in paths:
        try: resolved = path.resolve()
        except OSError: continue
        if str(resolved) in seen or not resolved.exists(): continue
        seen.add(str(resolved))
        size = resolved.stat().st_size if resolved.is_file() else sum(p.stat().st_size for p in resolved.rglob('*') if p.is_file())
        items.append({"name": resolved.name, "path": str(resolved), "size_bytes": size})
    return items


def _task_reserved_resource_paths(conn: sqlite3.Connection, task_id: str) -> list[Path]:
    paths: list[Path] = []
    rows = conn.execute(
        "SELECT reserved_path FROM production_resource_reservations WHERE task_id=? AND status='reserved'",
        (task_id,),
    ).fetchall()
    paths.extend(Path(str(row["reserved_path"])) for row in rows)
    jobs = conn.execute("SELECT reserved_videos_json FROM template_jobs WHERE task_id=?", (task_id,)).fetchall()
    for job in jobs:
        try:
            paths.extend(Path(str(item.get("reserved_path") or "")) for item in json.loads(str(job["reserved_videos_json"] or "[]")))
        except (TypeError, json.JSONDecodeError):
            continue
    # Only remove the currently renamed reservation. Failed template attempts
    # restore their original name, so their stale JSON must never cause the
    # shared source file to be deleted.
    return [path for path in paths if str(path) and path.is_file() and path.name.startswith("已使用-")]


def _is_within(path: Path, root: Path) -> bool:
    """Return whether a resolved path is inside a verified owner root."""
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _task_external_draft_paths(conn: sqlite3.Connection, task_id: str) -> list[Path]:
    """Return only V2-recorded Jianying drafts inside the configured draft root.

    A database path alone must never allow a cleanup operation to remove an
    arbitrary user folder.  V2 owns a draft only when it is both recorded on
    this task and physically below the configured Jianying draft root.
    """
    configured_root = str(get_v2_settings().get("jianying_draft_root") or "").strip()
    if not configured_root:
        return []
    draft_root = Path(configured_root).expanduser()
    if not draft_root.is_dir():
        return []
    rows = conn.execute(
        "SELECT draft_path FROM template_jobs WHERE task_id=? AND draft_path<>'' "
        "UNION SELECT draft_path FROM production_video_tasks WHERE task_id=? AND draft_path<>'' "
        "UNION SELECT draft_path FROM export_jobs WHERE production_task_id=? AND draft_path<>''",
        (task_id, task_id, task_id),
    ).fetchall()
    paths: list[Path] = []
    for row in rows:
        candidate = Path(str(row["draft_path"])).expanduser()
        if _is_within(candidate, draft_root):
            paths.append(candidate)
    return paths


def _task_material_thumbnail_paths(conn: sqlite3.Connection, task_id: str) -> list[Path]:
    """Material thumbnails are short-lived task cache, never seven-day source data."""
    if DATA_ROOT is None:
        return []
    cache_root = DATA_ROOT / "cache" / "material-thumbnails"
    rows = conn.execute(
        "SELECT thumbnail_path FROM production_files WHERE task_id=? AND thumbnail_path<>''",
        (task_id,),
    ).fetchall()
    paths: list[Path] = []
    for row in rows:
        candidate = Path(str(row["thumbnail_path"])).expanduser()
        if _is_within(candidate, cache_root):
            paths.append(candidate)
    return paths


def _task_source_output_paths(conn: sqlite3.Connection, task_id: str) -> list[Path]:
    """Exact, recorded exporter leftovers from Jianying's uncontrollable default folder."""
    rows = conn.execute(
        "SELECT a.source_output_path FROM export_attempts a "
        "JOIN export_jobs j ON j.id=a.job_id "
        "WHERE j.production_task_id=? AND a.source_output_path<>''",
        (task_id,),
    ).fetchall()
    return [Path(str(row["source_output_path"])).expanduser() for row in rows]


def _task_process_cleanup_paths(conn: sqlite3.Connection, task: sqlite3.Row) -> list[Path]:
    """Every removable process artifact owned by one production task.

    This single list is intentionally shared by immediate and scheduled
    cleanup so the two paths cannot silently drift apart.
    """
    task_id = str(task["id"])
    paths = [
        Path(str(task["template_path"])),
        Path(str(task["final_path"])),
        Path(str(task["root_path"])) / "缓存",
    ]
    paths.extend(_task_external_draft_paths(conn, task_id))
    paths.extend(_task_material_thumbnail_paths(conn, task_id))
    paths.extend(_task_source_output_paths(conn, task_id))
    paths.extend(_task_reserved_resource_paths(conn, task_id))
    return paths


def _task_raw_cleanup_paths(conn: sqlite3.Connection, task: sqlite3.Row) -> list[Path]:
    """Raw-material cleanup removes source files and their derived thumbnails only."""
    paths = [Path(str(task["material_path"]))]
    paths.extend(_task_material_thumbnail_paths(conn, str(task["id"])))
    return paths


def _remove_paths(paths: list[Path], *, preserve_directory: Path | None = None) -> tuple[list[str], list[str]]:
    """Remove exact paths; optionally empty, rather than remove, one source directory."""
    deleted: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError as exc:
            errors.append(f"{path}: {exc}")
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        try:
            if preserve_directory is not None and resolved == preserve_directory.resolve():
                if resolved.exists():
                    for item in resolved.iterdir():
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                deleted.append(str(resolved))
            elif resolved.exists():
                if resolved.is_dir():
                    shutil.rmtree(resolved)
                else:
                    resolved.unlink()
                deleted.append(str(resolved))
        except OSError as exc:
            errors.append(f"{resolved.name}: {exc}")
    return deleted, errors


def _due_at_or_backfill(conn: sqlite3.Connection, task: sqlite3.Row, column: str, delta: timedelta) -> datetime | None:
    """Use the release-time snapshot; only legacy blank rows are backfilled once."""
    value = str(task[column] or "").strip()
    if value:
        try:
            return datetime.fromisoformat(value.replace("T", " "))
        except ValueError:
            return None
    try:
        released = datetime.fromisoformat(str(task["actual_release_time"] or "").replace("T", " "))
    except ValueError:
        return None
    due = released + delta
    conn.execute("UPDATE production_tasks SET " + column + "=?, updated_at=? WHERE id=?", (due.isoformat(sep=" "), now_text(), str(task["id"])))
    return due


def _format_storage_size(size_bytes: int) -> str:
    """Use MB for small values and automatically carry over to GB/TB."""
    value = float(max(0, size_bytes))
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024
        index += 1
    if index < 2:
        return f"{value:.0f} {units[index]}"
    return f"{value:.1f} {units[index]}"


def _resolve_recorded_video_path(final_root: Path, recorded: Path, target: Path, drama_name: str, sequence_no: object) -> Path:
    """Resolve legacy export names without changing the stored history."""
    if recorded.is_file():
        return recorded
    if target.is_file():
        return target
    try:
        sequence = int(sequence_no)
    except (TypeError, ValueError):
        return recorded
    exact = final_root / f"{drama_name}-{sequence}.mp4"
    if exact.is_file():
        return exact
    candidates = sorted(final_root.glob(f"*-{sequence}.mp4"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else recorded

def cleanup_preview(task_id: str) -> dict[str, object]:
    conn = connection()
    try:
        task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task: raise ValueError("生产任务不存在")
        registered = str(task["release_status"] or "unregistered") == "registered"
        if str(task["cleanup_status"] or "active") != "active": raise ValueError("该任务已经清理过")
        paths: list[Path] = []
        if registered:
            # 发布后的清理删除全部已证明归属的过程文件；原素材单独保留。
            paths.extend(_task_process_cleanup_paths(conn, task))
            retained = _cleanup_file_items([Path(str(task["material_path"]))])
        else:
            # 未发布的“删除剧集”删除整个任务根目录，以及根目录外已登记的草稿。
            paths.append(Path(str(task["root_path"])))
            paths.extend(_task_external_draft_paths(conn, task_id))
            paths.extend(_task_material_thumbnail_paths(conn, task_id))
            paths.extend(_task_source_output_paths(conn, task_id))
            paths.extend(_task_reserved_resource_paths(conn, task_id))
            retained = []
        deleted = _cleanup_file_items(paths)
        total = sum(int(x["size_bytes"]) for x in deleted)
        return {"isRegisteredRelease": registered, "taskTitle": f"{task['account_name']} × 《{task['drama_name']}》", "accountName": str(task["account_name"]), "dramaName": str(task["drama_name"]), "currentStage": str(task["status"]), "canExecute": True, "estimatedSpaceMb": round(total / 1024 / 1024, 2), "estimatedSpaceText": _format_storage_size(total), "itemsToDelete": [{"name": x["name"], "sizeMb": round(int(x["size_bytes"]) / 1024 / 1024, 2), "sizeText": _format_storage_size(int(x["size_bytes"]))} for x in deleted], "itemsToRetain": [f"原素材：{x['name']}" for x in retained] + (["账号、剧集、发布时间、发布地址和清理记录"] if registered else [])}
    finally: conn.close()

def execute_cleanup(task_id: str) -> dict[str, object]:
    preview = cleanup_preview(task_id)
    conn = connection(); deleted: list[str] = []; errors: list[str] = []
    try:
        task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        registered = bool(preview["isRegisteredRelease"])
        if registered:
            deleted, errors = _remove_paths(_task_process_cleanup_paths(conn, task))
        else:
            active = conn.execute(
                "SELECT 1 FROM template_jobs WHERE task_id=? AND status IN ('dispatching','running') "
                "UNION SELECT 1 FROM production_video_tasks WHERE task_id=? AND status IN ('generation_queued','generating') "
                "UNION SELECT 1 FROM export_attempts a JOIN export_jobs j ON j.id=a.job_id "
                "WHERE j.production_task_id=? AND a.status IN ('preparing','submitting','observing_output','finalizing') LIMIT 1",
                (task_id, task_id, task_id),
            ).fetchone()
            if active:
                raise ValueError("当前剧集仍有正在执行的任务，请先等待任务结束或在任务中心停止后再删除")
            paths = [Path(str(task["root_path"]))]
            paths.extend(_task_external_draft_paths(conn, task_id))
            paths.extend(_task_material_thumbnail_paths(conn, task_id))
            paths.extend(_task_source_output_paths(conn, task_id))
            paths.extend(_task_reserved_resource_paths(conn, task_id))
            deleted, errors = _remove_paths(paths)
        stamp = now_text(); status = "partial" if errors else "completed"
        if registered:
            conn.execute("UPDATE production_resource_reservations SET status=?, released_at=? WHERE task_id=? AND status='reserved'", ("missing" if errors else "released", stamp, task_id))
            conn.execute("INSERT INTO cleanup_records VALUES (?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, task_id, "immediate", status, json.dumps(deleted, ensure_ascii=False), json.dumps(preview["itemsToRetain"], ensure_ascii=False), "\n".join(errors), stamp, stamp))
            if not errors:
                conn.execute("UPDATE production_files SET thumbnail_path='', updated_at=? WHERE task_id=?", (stamp, task_id))
                purge_executor_traces_for_task(conn, task_id)
            # process_cleanup_at is the release-time deadline snapshot.  The
            # actual completion time belongs in cleaned_at / cleanup_records.
            conn.execute("UPDATE production_tasks SET cleanup_status=?, cleaned_at=?, updated_at=? WHERE id=?", ("process_cleaned" if not errors else "partial", stamp, stamp, task_id))
        elif not errors:
            # “删除剧集”是完全删除：不留下孤立的任务清理记录。
            conn.execute("DELETE FROM cleanup_records WHERE task_id=?", (task_id,))
            purge_executor_traces_for_task(conn, task_id)
            conn.execute("DELETE FROM production_tasks WHERE id=?", (task_id,))
        conn.commit()
        return {"status": status, "deleted": deleted, "errors": errors}
    finally: conn.close()

def run_due_cleanup() -> dict[str, int]:
    """Run due post-release cleanup in two independent stages."""
    conn = connection(); process_count = raw_count = 0
    try:
        settings = get_v2_settings()
        now = datetime.now()
        rows = conn.execute("SELECT * FROM production_tasks WHERE release_status='registered' AND cleanup_status IN ('active','process_cleaned','partial','raw_partial') AND actual_release_time<>''").fetchall()
        for task in rows:
            process_due = _due_at_or_backfill(conn, task, "process_cleanup_at", timedelta(hours=int(settings["short_term_cleanup_hours"])))
            raw_due = _due_at_or_backfill(conn, task, "raw_cleanup_at", timedelta(days=int(settings["raw_material_retention_days"])))
            if process_due is None or raw_due is None:
                continue
            status = str(task["cleanup_status"] or "active")
            if status in {"active", "partial"} and now >= process_due:
                deleted, errors = _remove_paths(_task_process_cleanup_paths(conn, task))
                stamp = now_text()
                conn.execute("UPDATE production_tasks SET cleanup_status=?, cleaned_at=?, updated_at=? WHERE id=?", ("partial" if errors else "process_cleaned", stamp, stamp, str(task["id"])))
                conn.execute("INSERT INTO cleanup_records VALUES (?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, str(task["id"]), "scheduled_process", "partial" if errors else "completed", json.dumps(deleted, ensure_ascii=False), json.dumps(["原素材、素材登记信息、发布和收益信息"], ensure_ascii=False), "\n".join(errors), stamp, stamp))
                conn.execute("UPDATE production_resource_reservations SET status=?, released_at=? WHERE task_id=? AND status='reserved'", ("missing" if errors else "released", stamp, str(task["id"])))
                if not errors:
                    conn.execute("UPDATE production_files SET thumbnail_path='', updated_at=? WHERE task_id=?", (stamp, str(task["id"])))
                    purge_executor_traces_for_task(conn, str(task["id"]))
                process_count += 1
            current = conn.execute("SELECT cleanup_status FROM production_tasks WHERE id=?", (str(task["id"]),)).fetchone()
            # A partial process cleanup must be retried first.  Never destroy
            # the seven-day source evidence while process artifacts remain.
            if not current or str(current["cleanup_status"]) not in {"process_cleaned", "raw_partial"}: continue
            if now < raw_due: continue
            material_root = Path(str(task["material_path"])); deleted, errors = _remove_paths(
                _task_raw_cleanup_paths(conn, task), preserve_directory=material_root,
            )
            stamp = now_text(); status = "raw_partial" if errors else "raw_cleaned"
            conn.execute("UPDATE production_tasks SET cleanup_status=?, cleaned_at=?, updated_at=? WHERE id=?", (status, stamp, stamp, str(task["id"])))
            if not errors:
                conn.execute("UPDATE production_files SET status='source_cleaned', thumbnail_path='', missing_scan_count=0, updated_at=? WHERE task_id=?", (stamp, str(task["id"])))
            conn.execute("INSERT INTO cleanup_records VALUES (?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, str(task["id"]), "scheduled_raw", status, json.dumps(deleted, ensure_ascii=False), json.dumps(["素材登记信息、账号、剧集、发布时间、发布地址、收益和爆款关联"], ensure_ascii=False), "\n".join(errors), stamp, stamp))
            raw_count += 1
        conn.commit()
        return {"process": process_count, "raw": raw_count}
    finally: conn.close()


def start_finished_video_generation(video_id: str) -> dict[str, str]:
    from server.final_engine.runner import start_finished_video
    return start_finished_video(video_id)


def create_finished_video_task(task_id: str, source_material_id: str) -> dict[str, str]:
    """Create one finished-video task only after an explicit user action.

    Scanning records materials, but never submits them for finished-video
    generation.  This function is the sole submission boundary used by the
    production-center "生成成片" action.
    """
    conn = connection()
    try:
        material = conn.execute(
            "SELECT id, file_path, status FROM production_files "
            "WHERE id=? AND task_id=? AND file_type='original_material'",
            (source_material_id, task_id),
        ).fetchone()
        if not material:
            raise ValueError("成片任务对应的素材不存在")
        if str(material["status"]) != "available" or not Path(str(material["file_path"])).is_file():
            raise ValueError("成片任务对应的素材不可用")
        existing = conn.execute(
            "SELECT * FROM production_video_tasks WHERE task_id=? AND source_material_id=?",
            (task_id, source_material_id),
        ).fetchone()
        stamp = now_text()
        if existing:
            if str(existing["status"]) in {"cancelled", "invalidated"}:
                conn.execute(
                    "UPDATE production_video_tasks SET status='pending_generation', "
                    "error_message='', started_at='', finished_at='', updated_at=? WHERE id=?",
                    (stamp, str(existing["id"])),
                )
                conn.commit()
            return {"id": str(existing["id"]), "status": "pending_generation" if str(existing["status"]) in {"cancelled", "invalidated"} else str(existing["status"])}
        video_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO production_video_tasks "
            "(id, task_id, source_material_id, status, draft_path, output_path, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending_generation', '', '', ?, ?)",
            (video_id, task_id, source_material_id, stamp, stamp),
        )
        conn.commit()
        return {"id": video_id, "status": "pending_generation"}
    finally:
        conn.close()


def create_finished_video_tasks_batch(task_id: str, source_material_ids: list[str]) -> dict[str, object]:
    """Submit several material-driven finished-video tasks in one user action."""
    ids = list(dict.fromkeys(str(item).strip() for item in source_material_ids if str(item).strip()))
    if not ids:
        raise ValueError("请至少选择一条素材")
    conn = connection()
    try:
        task = conn.execute("SELECT id FROM production_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise ValueError("生产任务不存在")
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT id, file_path, status FROM production_files WHERE task_id=? AND file_type='original_material' AND id IN ({placeholders})",
            (task_id, *ids),
        ).fetchall()
        by_id = {str(row["id"]): row for row in rows}
        missing = [item for item in ids if item not in by_id]
        if missing:
            raise ValueError("所选素材不存在或不属于当前生产任务")
        unavailable = [item for item in ids if str(by_id[item]["status"]) != "available" or not Path(str(by_id[item]["file_path"])).is_file()]
        if unavailable:
            raise ValueError("所选素材中存在已删除或不可用文件，请重新扫描")
        stamp = now_text()
        created: list[dict[str, str]] = []
        new_count = 0
        for material_id in ids:
            existing = conn.execute(
                "SELECT id, status FROM production_video_tasks WHERE task_id=? AND source_material_id=?",
                (task_id, material_id),
            ).fetchone()
            if existing:
                status = str(existing["status"])
                if status in {"cancelled", "invalidated"}:
                    conn.execute("UPDATE production_video_tasks SET status='pending_generation', error_message='', started_at='', finished_at='', updated_at=? WHERE id=?", (stamp, str(existing["id"])))
                    status = "pending_generation"
                created.append({"id": str(existing["id"]), "source_material_id": material_id, "status": status})
                continue
            video_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO production_video_tasks (id, task_id, source_material_id, status, draft_path, output_path, created_at, updated_at) VALUES (?, ?, ?, 'pending_generation', '', '', ?, ?)",
                (video_id, task_id, material_id, stamp, stamp),
            )
            created.append({"id": video_id, "source_material_id": material_id, "status": "pending_generation"})
            new_count += 1
        conn.commit()
        return {"task_id": task_id, "items": created, "created_count": new_count}
    finally:
        conn.close()


def update_task_manual_check(task_id: str, enabled: bool) -> dict[str, object]:
    """Update the live manual-check policy for one production drama."""
    conn = connection()
    try:
        updated = conn.execute(
            "UPDATE production_tasks SET final_video_manual_check=?, updated_at=? "
            "WHERE id=? AND COALESCE(cleanup_status, 'active')='active'",
            (int(bool(enabled)), now_text(), task_id),
        ).rowcount
        if updated != 1:
            raise ValueError("生产任务不存在")
        conn.commit()
        return get_task_details(task_id)
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


def _verified_export_duration(conn: sqlite3.Connection, attempt_id: str) -> float:
    """Read the MP4 duration captured at successful export finalisation."""
    if not attempt_id:
        return 0.0
    row = conn.execute(
        "SELECT detail_json FROM export_events WHERE attempt_id=? AND event_type='OUTPUT_FINALIZED' "
        "ORDER BY sequence_no DESC LIMIT 1",
        (attempt_id,),
    ).fetchone()
    if not row:
        return 0.0
    try:
        return max(0.0, float(json.loads(str(row["detail_json"] or "{}")).get("duration_seconds") or 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0.0


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
            resolution = media_resolution(path)
            conn.execute(
                "INSERT INTO production_files "
                "(id,task_id,file_type,original_name,file_name,file_path,md5,sha256,size_bytes,sequence_no,status,created_at,updated_at,duration_seconds,thumbnail_path,resolution,missing_scan_count) "
                "VALUES (?, ?, 'original_material', ?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?, ?, 0) "
                "ON CONFLICT(task_id, file_path) DO UPDATE SET "
                "original_name=excluded.original_name, file_name=excluded.file_name, md5=excluded.md5, sha256=excluded.sha256, "
                "size_bytes=excluded.size_bytes, sequence_no=excluded.sequence_no, duration_seconds=excluded.duration_seconds, "
                "thumbnail_path=excluded.thumbnail_path, resolution=excluded.resolution, status='available', missing_scan_count=0, updated_at=excluded.updated_at",
                (uuid.uuid4().hex, task_id, original.name, path.name, str(path), md5, sha256, path.stat().st_size, sequence, stamp, stamp, duration_seconds, thumbnail_path, resolution),
            )
            material = conn.execute(
                "SELECT id FROM production_files WHERE task_id=? AND file_path=?",
                (task_id, str(path)),
            ).fetchone()
            items.append({"name": path.name, "path": str(path), "sequence_no": sequence, "md5": md5, "size_bytes": path.stat().st_size})
        current_paths = {str(path) for path in renamed}
        recorded_paths = conn.execute(
            "SELECT id, file_path FROM production_files WHERE task_id=? AND file_type='original_material'",
            (task_id,),
        ).fetchall()
        for recorded in recorded_paths:
            if str(recorded["file_path"]) not in current_paths:
                material_id = str(recorded["id"])
                previous = conn.execute("SELECT missing_scan_count FROM production_files WHERE id=?", (material_id,)).fetchone()
                count = int(previous["missing_scan_count"] or 0) + 1
                if count < 2:
                    conn.execute("UPDATE production_files SET status='source_missing', missing_scan_count=?, updated_at=? WHERE id=?", (count, stamp, material_id))
                    continue
                video_rows = conn.execute("SELECT id, draft_path, output_path FROM production_video_tasks WHERE source_material_id=?", (material_id,)).fetchall()
                for video in video_rows:
                    for raw_path in (video["draft_path"], video["output_path"]):
                        if raw_path:
                            target = Path(str(raw_path))
                            if target.is_file(): target.unlink(missing_ok=True)
                            elif target.is_dir(): shutil.rmtree(target, ignore_errors=True)
                    shutil.rmtree(Path(str(task["root_path"])) / "缓存" / "成片" / str(video["id"]), ignore_errors=True)
                    conn.execute("DELETE FROM export_jobs WHERE subject_type='final' AND subject_id=?", (str(video["id"]),))
                conn.execute("DELETE FROM production_video_tasks WHERE source_material_id=?", (material_id,))
                conn.execute("DELETE FROM production_files WHERE id=?", (material_id,))
        conn.execute("UPDATE production_tasks SET status=?, updated_at=? WHERE id=?", ("materials_scanned", stamp, task_id))
        conn.commit()
        return {"task_id": task_id, "directory": str(directory), "discovered": len(files), "items": items}
      finally:
          conn.close()


def template_stem(task: sqlite3.Row) -> str:
    created = str(task["created_date"])
    return f"{int(created[5:7])}月{int(created[8:10])}日-{safe_component(str(task['account_name']), '账号')}-{safe_component(str(task['drama_name']), '剧集')}"


def ensure_final_photo_reservation(task_id: str) -> list[Path]:
    """领取并固定一组真人图片，供该日期/账号/剧集的所有分集复用。"""
    with RESOURCE_RESERVATION_LOCK:
        conn = connection()
        renamed: list[tuple[Path, Path]] = []
        try:
            existing = conn.execute(
                "SELECT reserved_path FROM production_resource_reservations "
                "WHERE task_id=? AND resource_type='real_image' AND version_no=1 AND status='reserved' ORDER BY sequence_no",
                (task_id,),
            ).fetchall()
            if len(existing) == 6 and all(Path(str(row["reserved_path"])).is_file() for row in existing):
                return [Path(str(row["reserved_path"])) for row in existing]
            task = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
            if not task:
                raise ValueError("生产任务不存在")
            workspace, _ = require_configured_paths()
            root = workspace / "生成资源" / "真人图片"
            root.mkdir(parents=True, exist_ok=True)
            candidates = sorted(
                (p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and not p.name.startswith("已使用")),
                key=lambda path: natural_key(path.name),
            )
            if len(candidates) < 6:
                raise ValueError(f"真人图片不足 6 张，当前可领取 {len(candidates)} 张")
            stem = template_stem(task)
            stamp = now_text()
            paths: list[Path] = []
            try:
                for index, source in enumerate(candidates[:6], start=1):
                    target = source.with_name(f"已使用-{stem}-R01-{index:02d}{source.suffix.lower()}")
                    if target.exists():
                        raise ValueError("真人图片领取命名冲突，未覆盖任何文件")
                    source.rename(target); renamed.append((source, target)); paths.append(target)
                    conn.execute(
                        "INSERT INTO production_resource_reservations "
                        "(id,task_id,resource_type,version_no,sequence_no,original_path,reserved_path,original_name,reserved_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (uuid.uuid4().hex, task_id, "real_image", 1, index, str(source), str(target), source.name, target.name, stamp),
                    )
                conn.commit()
                return paths
            except Exception:
                for source, target in reversed(renamed):
                    if target.exists() and not source.exists(): target.rename(source)
                conn.rollback()
                raise
        finally:
            conn.close()


def queue_template_job(task_id: str, *, regenerate: bool = False, retry: bool = False) -> dict[str, object]:
    """Reserve exactly three real videos for one V2 template attempt.

    This intentionally stops before invoking Jianying.  The separate runner is
    responsible for photo preparation and draft creation, so a failed preflight
    can restore these names without touching a draft.
    """
    with TEMPLATE_JOB_LOCK:
        from server.jianying_preflight import require_jianying_ready
        require_jianying_ready(get_v2_settings())
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
            if len(candidates) < 1:
                raise ValueError(f"真人视频不足，当前可领取 {len(candidates)} 条")
            current_status = str(current["status"]) if current else ""
            # 失败/超时是同一次尝试的重新执行，继续使用 R01；只有成功
            # 的模板被用户主动重新生成时，才创建 R02、R03 新版本。
            if current and retry and current_status in {"error", "timeout"}:
                version = int(current["version_no"])
            else:
                version = int(current["version_no"]) + 1 if current else 1
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
                for index, source in enumerate(candidates[:1], start=1):
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


def finished_video_media(video_id: str) -> Path:
    """Return only a verified formal final video owned by the requested task."""
    conn = connection()
    try:
        row = conn.execute(
            "SELECT v.output_path, t.final_path FROM production_video_tasks v "
            "JOIN production_tasks t ON t.id=v.task_id WHERE v.id=?",
            (video_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError("成片视频不存在")
    candidate = Path(str(row["output_path"] or "")).resolve()
    final_root = Path(str(row["final_path"] or "")).resolve()
    if not candidate.is_relative_to(final_root) or not candidate.is_file():
        raise ValueError("成片视频尚未完成或正式文件不存在")
    return candidate


def finished_video_thumbnail(video_id: str) -> Path:
    """Create or reuse a first-frame thumbnail for a verified formal final video."""
    output = finished_video_media(video_id)
    stat = output.stat()
    cache_key = hashlib.sha1(
        f"finished:{output}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()
    _, thumbnail_path = probe_material(output, cache_key)
    thumbnail = Path(thumbnail_path)
    if not thumbnail.is_file():
        raise ValueError("成片预览缩略图暂时无法生成")
    return thumbnail


def request_open_finished_video_draft(video_id: str) -> dict[str, object]:
    """Open a completed final's draft only while the exporter is manually idle."""
    from server.executor_management import ExecutorManager
    from server.jianying_preflight import require_jianying_ready
    from server.v2_exporter.runner import start_manual_draft_open_in_background

    conn = connection()
    try:
        state = ExecutorManager(conn).state("video_exporter")
        if str(state.get("control_state") or "") != "manual_paused" or str(state.get("current_task_id") or ""):
            raise ValueError("请先将视频导出器设为人工暂停，并等待当前导出任务结束后再打开草稿")
        row = conn.execute(
            "SELECT v.draft_path, v.output_path, j.draft_name FROM production_video_tasks v "
            "LEFT JOIN export_jobs j ON j.id=(SELECT candidate.id FROM export_jobs candidate "
            "WHERE candidate.subject_type='final' AND candidate.subject_id=v.id ORDER BY candidate.created_at DESC LIMIT 1) "
            "WHERE v.id=?",
            (video_id,),
        ).fetchone()
        if not row:
            raise ValueError("成片任务不存在")
        draft_path = Path(str(row["draft_path"] or "")).resolve()
        if not draft_path.is_dir() or not finished_video_media(video_id).is_file():
            raise ValueError("当前成片缺少可打开的草稿或已验收视频")
        draft_name = str(row["draft_name"] or draft_path.name).strip()
        if not draft_name:
            raise ValueError("当前成片草稿名称不可用")
        settings = get_v2_settings()
        require_jianying_ready(settings)
        start_manual_draft_open_in_background(
            connection, video_id=video_id, draft_name=draft_name, draft_path=draft_path,
            settings=settings,
        )
        return {"accepted": True, "video_id": video_id}
    finally:
        conn.close()

def request_open_template_draft(task_id: str) -> dict[str, object]:
    from server.executor_management import ExecutorManager
    from server.jianying_preflight import require_jianying_ready
    from server.v2_exporter.runner import start_manual_template_draft_open_in_background
    conn = connection()
    try:
        state = ExecutorManager(conn).state("video_exporter")
        if str(state.get("control_state") or "") != "manual_paused" or str(state.get("current_task_id") or ""):
            raise ValueError("请先将视频导出器设为人工暂停，并等待当前导出任务结束后再打开草稿")
        row = conn.execute("SELECT draft_name, draft_path FROM template_jobs WHERE task_id=? ORDER BY version_no DESC LIMIT 1", (task_id,)).fetchone()
        if not row or not Path(str(row["draft_path"] or "")).is_dir():
            raise ValueError("当前剧集缺少可打开的模板草稿")
        settings = get_v2_settings()
        require_jianying_ready(settings)
        start_manual_template_draft_open_in_background(draft_name=str(row["draft_name"]), settings=settings)
        return {"accepted": True, "task_id": task_id}
    finally:
        conn.close()

def template_video_media(task_id: str) -> Path:
    conn = connection()
    try: row = conn.execute("SELECT COALESCE((SELECT target_path FROM export_jobs WHERE subject_type='template' AND subject_id=t.id ORDER BY created_at DESC LIMIT 1), t.video_path) AS video_path FROM template_jobs t WHERE t.task_id=? ORDER BY t.version_no DESC LIMIT 1", (task_id,)).fetchone()
    finally: conn.close()
    candidate = Path(str(row["video_path"] or "")).resolve() if row else Path("")
    if not candidate.is_file() or WORKSPACE is None or not candidate.is_relative_to(WORKSPACE.resolve()):
        raise ValueError("模板视频尚未完成或正式文件不存在")
    return candidate


REVENUE_COLLECTION_START_LOCK = threading.Lock()


def start_revenue_collection(
    start_date: str,
    end_date: str,
    *,
    theater_names: list[str] | None = None,
    account_ids: list[str] | None = None,
    trigger_source: str = "manual",
    scheduled_slots: list[str] | None = None,
) -> dict[str, object]:
    """Create one V2 revenue run and execute it in the background.

    Manual requests and automatic schedule checks intentionally share this
    entry point so they persist the same account-level evidence and results.
    """
    if trigger_source not in {"manual", "automatic"}:
        raise ValueError("收益采集触发来源不正确")
    if not start_date or not end_date:
        raise ValueError("请选择收益采集日期")
    slots = sorted(set(scheduled_slots or []))
    if not all(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", slot) for slot in slots):
        raise ValueError("自动采集时间点格式不正确")
    with REVENUE_COLLECTION_START_LOCK:
        conn = connection()
        try:
            from server.v2_revenue_service import estimate_collection_units
            run_id, now = uuid.uuid4().hex, datetime.now().isoformat(timespec="seconds")
            total_units = estimate_collection_units(conn, start_date, end_date, theater_names, account_ids)
            conn.execute(
                """INSERT INTO v2_revenue_collection_runs
                   (id, status, start_date, end_date, trigger_source, scheduled_slots_json, total_units, created_at, updated_at)
                   VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, start_date, end_date, trigger_source, json.dumps(slots, ensure_ascii=False), total_units, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    def run_collection() -> None:
        worker_conn = connection()
        try:
            from server.v2_revenue_service import collect_supported_theaters
            started = datetime.now().isoformat(timespec="seconds")
            worker_conn.execute("UPDATE v2_revenue_collection_runs SET status='running', started_at=?, updated_at=? WHERE id=?", (started, started, run_id))
            worker_conn.commit()

            def report(item: dict[str, object]) -> None:
                status = str(item.get("status") or "failed")
                if status == "running":
                    worker_conn.execute("UPDATE v2_revenue_collection_runs SET current_theater=?, current_account=?, updated_at=? WHERE id=?", (str(item.get("theater_name") or ""), str(item.get("account_name") or ""), datetime.now().isoformat(timespec="seconds"), run_id))
                else:
                    worker_conn.execute(
                        """UPDATE v2_revenue_collection_runs SET completed_units=completed_units+1,
                           success_units=success_units+?, no_data_units=no_data_units+?, failed_units=failed_units+?,
                           current_theater=?, current_account=?, updated_at=? WHERE id=?""",
                        (1 if status == "success" else 0, 1 if status == "no_data" else 0, 1 if status == "failed" else 0,
                         str(item.get("theater_name") or ""), str(item.get("account_name") or ""), datetime.now().isoformat(timespec="seconds"), run_id),
                    )
                worker_conn.commit()

            collect_supported_theaters(worker_conn, start_date, end_date, theater_names, account_ids, report)
            finished = datetime.now().isoformat(timespec="seconds")
            worker_conn.execute("UPDATE v2_revenue_collection_runs SET status='completed', finished_at=?, updated_at=? WHERE id=?", (finished, finished, run_id))
            worker_conn.commit()
        except Exception as exc:  # noqa: BLE001
            failed = datetime.now().isoformat(timespec="seconds")
            worker_conn.execute("UPDATE v2_revenue_collection_runs SET status='failed', error_message=?, finished_at=?, updated_at=? WHERE id=?", (str(exc), failed, failed, run_id))
            worker_conn.commit()
        finally:
            worker_conn.close()

    threading.Thread(target=run_collection, name=f"v2-revenue-{run_id[:8]}", daemon=True).start()
    return {"run_id": run_id, "status": "queued", "total_units": total_units}


class Handler(BaseHTTPRequestHandler):
    def _binary(self, file_path: Path, content_type: str, *, cache_control: str = "public, max-age=86400") -> None:
        body = file_path.read_bytes()
        stat = file_path.stat()
        etag = '"%s-%s"' % (stat.st_mtime_ns, stat.st_size)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _frontend(self, request_path: str) -> None:
        try:
            file_path, is_html = resolve_frontend_asset(request_path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        except RuntimeError as exc:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self._binary(file_path, content_type, cache_control="no-store" if is_html else "public, max-age=86400")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/cleanup/preview", path)
        if match:
            try: self._json(HTTPStatus.OK, cleanup_preview(match.group(1)))
            except (ValueError, OSError) as exc: self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/v2/production-files/([a-f0-9]+)/thumbnail", path)
        if match:
            try:
                file_path = production_media(match.group(1), thumbnail=True)
                content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}.get(file_path.suffix.lower(), "image/jpeg")
                self._binary(file_path, content_type)
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
        match = re.fullmatch(r"/api/v2/production-videos/([a-f0-9]+)/media", path)
        if match:
            try:
                file_path = finished_video_media(match.group(1)); size = file_path.stat().st_size
                self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "video/mp4"); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(size)); self.end_headers()
                with file_path.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile)
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/template-media", path)
        if match:
            try:
                file_path = template_video_media(match.group(1)); size = file_path.stat().st_size
                self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "video/mp4"); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(size)); self.end_headers()
                with file_path.open("rb") as stream: shutil.copyfileobj(stream, self.wfile)
            except (ValueError, OSError) as exc: self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/v2/production-videos/([a-f0-9]+)/thumbnail", path)
        if match:
            try:
                self._binary(finished_video_thumbnail(match.group(1)), "image/jpeg")
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/v2/production-resources/([a-f0-9]+)/thumbnail", path)
        if match:
            try:
                file_path = production_resource_media(match.group(1), thumbnail=True)
                self._binary(file_path, "image/jpeg")
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/v2/production-resources/([a-f0-9]+)/media", path)
        if match:
            try:
                file_path = production_resource_media(match.group(1)); size = file_path.stat().st_size
                content_type = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}.get(file_path.suffix.lower(), "application/octet-stream")
                self.send_response(HTTPStatus.OK); self.send_header("Content-Type", content_type); self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(size)); self.end_headers()
                with file_path.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile)
            except (ValueError, OSError) as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        if path == "/api/v2/health":
            self._json(HTTPStatus.OK, {"status": "ok", "service": "v2-file-service"})
            return
        if path == "/api/v2/settings/jianying-preflight":
            from server.jianying_preflight import run_jianying_preflight
            self._json(HTTPStatus.OK, run_jianying_preflight(get_v2_settings()).to_dict())
            return
        if path == "/api/v2/change-events":
            query = parse_qs(urlparse(self.path).query)
            raw_after = str(query.get("after_id", [""])[0]).strip()
            try:
                after_id = int(raw_after) if raw_after else None
                self._json(HTTPStatus.OK, list_change_events(after_id, int(query.get("limit", ["200"])[0])))
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "变化记录游标无效"})
            return
        if path == "/api/v2/theaters":
            self._json(HTTPStatus.OK, list_theaters())
            return
        if path == "/api/v2/accounts":
            self._json(HTTPStatus.OK, list_accounts())
            return
        match = re.fullmatch(r"/api/v2/accounts/([a-f0-9]+)", path)
        if match:
            try: self._json(HTTPStatus.OK, get_account(match.group(1)))
            except ValueError as exc: self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        if path == "/api/v2/sub-theaters":
            self._json(HTTPStatus.OK, list_sub_theaters())
            return
        if path == "/api/v2/dramas":
            self._json(HTTPStatus.OK, list_dramas())
            return
        if path == "/api/v2/wechat-index/connection":
            self._json(HTTPStatus.OK, wechat_index_connection_state())
            return
        if path == "/api/v2/wechat-index/capture":
            self._json(HTTPStatus.OK, wechat_index_capture_status())
            return
        if path == "/api/v2/wechat-index/keywords":
            query = parse_qs(urlparse(self.path).query)
            self._json(HTTPStatus.OK, list_wechat_index_keywords(str(query.get("drama_id", [""])[0])))
            return
        match = re.fullmatch(r"/api/v2/dramas/([a-f0-9]+)", path)
        if match:
            try: self._json(HTTPStatus.OK, get_drama(match.group(1)))
            except ValueError as exc: self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
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
        if path == "/api/v2/local-vision-ai/status":
            from server.local_vision_ai import status
            self._json(HTTPStatus.OK, status())
            return
        if path == "/api/v2/drives":
            self._json(HTTPStatus.OK, {"items": list_windows_drives()})
            return
        if path == "/api/v2/production-tasks":
            self._json(HTTPStatus.OK, list_tasks())
            return
        if path == "/api/v2/production-task-summaries":
            self._json(HTTPStatus.OK, list_task_summaries())
            return
        match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/details", path)
        if match:
            try:
                self._json(HTTPStatus.OK, get_task_details(match.group(1)))
            except ValueError as exc:
                self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        if path == "/api/v2/release-addresses":
            self._json(HTTPStatus.OK, list_release_addresses(str(parse_qs(urlparse(self.path).query).get("account_name", [""])[0])))
            return
        if path == "/api/v2/revenue/source-data":
            try:
                from server.v2_revenue_service import revenue_source_data
            except ModuleNotFoundError:
                from v2_revenue_service import revenue_source_data
            conn = connection()
            try:
                self._json(HTTPStatus.OK, revenue_source_data(conn))
            finally:
                conn.close()
            return
        if path == "/api/v2/revenue/daily-account-summary":
            try:
                from server.v2_revenue_service import revenue_daily_account_summary
            except ModuleNotFoundError:
                from v2_revenue_service import revenue_daily_account_summary
            query = parse_qs(urlparse(self.path).query)
            try:
                conn = connection()
                try:
                    self._json(HTTPStatus.OK, revenue_daily_account_summary(conn, str(query.get("date", [""])[0])))
                finally:
                    conn.close()
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path == "/api/v2/revenue/video-details":
            try:
                from server.v2_revenue_service import revenue_video_details
            except ModuleNotFoundError:
                from v2_revenue_service import revenue_video_details
            query = parse_qs(urlparse(self.path).query)
            start_date = str(query.get("start_date", [""])[0])
            end_date = str(query.get("end_date", [""])[0])
            account_id = str(query.get("account_id", [""])[0])
            try:
                limit = int(query.get("limit", ["12000"])[0])
                conn = connection()
                try:
                    self._json(HTTPStatus.OK, revenue_video_details(conn, start_date, end_date, account_id, limit))
                finally:
                    conn.close()
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if path == "/api/v2/revenue/video-candidates":
            try:
                from server.v2_revenue_service import revenue_video_candidates
            except ModuleNotFoundError:
                from v2_revenue_service import revenue_video_candidates
            query = parse_qs(urlparse(self.path).query)
            conn = connection()
            try:
                self._json(HTTPStatus.OK, revenue_video_candidates(conn, str(query.get("account_id", [""])[0]), str(query.get("video_id", [""])[0])))
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            finally:
                conn.close()
            return
        if path == "/api/v2/revenue/collection-logs":
            try:
                from server.v2_revenue_service import collection_logs
            except ModuleNotFoundError:
                from v2_revenue_service import collection_logs
            limit = int(parse_qs(urlparse(self.path).query).get("limit", ["80"])[0])
            conn = connection()
            try:
                self._json(HTTPStatus.OK, collection_logs(conn, limit))
            finally:
                conn.close()
            return
        match = re.fullmatch(r"/api/v2/revenue/collection-runs/([a-f0-9]+)", path)
        if match:
            conn = connection()
            try:
                row = conn.execute("""SELECT id, status, total_units, completed_units, success_units, no_data_units, failed_units,
                    current_theater, current_account, error_message, created_at, started_at, finished_at
                    FROM v2_revenue_collection_runs WHERE id=?""", (match.group(1),)).fetchone()
                if not row:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "未找到该采集任务"})
                else:
                    self._json(HTTPStatus.OK, dict(row))
            finally:
                conn.close()
            return
        if path == "/api/v2/task-center":
            try:
                from server.task_center_service import task_center_snapshot
            except ModuleNotFoundError:
                from task_center_service import task_center_snapshot
            try:
                self._json(HTTPStatus.OK, task_center_snapshot())
            except Exception as exc:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"任务中心加载失败：{exc}"})
            return
        match = re.fullmatch(r"/api/v2/task-center/production-tasks/([a-f0-9]+)", path)
        if match:
            try:
                from server.task_center_service import task_center_items_for_production_task
            except ModuleNotFoundError:
                from task_center_service import task_center_items_for_production_task
            try:
                self._json(HTTPStatus.OK, task_center_items_for_production_task(match.group(1)))
            except Exception as exc:  # noqa: BLE001
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"任务局部加载失败：{exc}"})
            return
        if path.startswith("/api/v2"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "V2 接口不存在"})
            return
        self._frontend(path)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/v2/production-tasks":
                self._json(HTTPStatus.CREATED, create_task(payload))
                return
            if path == "/api/v2/revenue/collect":
                start_date = str(payload.get("start_date") or "").strip()
                end_date = str(payload.get("end_date") or "").strip()
                theater_names = payload.get("theaters") if isinstance(payload.get("theaters"), list) else None
                account_ids = payload.get("account_ids") if isinstance(payload.get("account_ids"), list) else None
                self._json(HTTPStatus.ACCEPTED, start_revenue_collection(start_date, end_date, theater_names=theater_names, account_ids=account_ids))
                return
            if path == "/api/v2/revenue/video-links":
                try:
                    from server.v2_revenue_service import confirm_revenue_video_link
                except ModuleNotFoundError:
                    from v2_revenue_service import confirm_revenue_video_link
                conn = connection()
                try:
                    self._json(HTTPStatus.OK, confirm_revenue_video_link(conn, payload))
                finally:
                    conn.close()
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/release", path)
            if match:
                self._json(HTTPStatus.OK, register_release(match.group(1), payload))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/release/revoke", path)
            if match:
                self._json(HTTPStatus.OK, revoke_release(match.group(1)))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/cleanup/preview", path)
            if match:
                self._json(HTTPStatus.OK, cleanup_preview(match.group(1))); return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/cleanup", path)
            if match:
                self._json(HTTPStatus.OK, execute_cleanup(match.group(1))); return
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
            if path == "/api/v2/wechat-index/keywords":
                self._json(HTTPStatus.CREATED, create_wechat_index_keyword(payload)); return
            if path == "/api/v2/wechat-index/connection/initialize":
                self._json(HTTPStatus.OK, initialize_wechat_index_connection(payload)); return
            if path == "/api/v2/wechat-index/capture/start":
                self._json(HTTPStatus.ACCEPTED, start_wechat_index_capture()); return
            if path == "/api/v2/wechat-index/capture/stop":
                self._json(HTTPStatus.OK, stop_wechat_index_capture()); return
            if path == "/api/v2/wechat-index/history/collect":
                self._json(HTTPStatus.OK, collect_wechat_index_history(payload)); return
            if path == "/api/v2/wechat-index/history/import":
                self._json(HTTPStatus.OK, import_wechat_index_history(payload)); return
            if path == "/api/v2/wechat-index/suggestions/import":
                self._json(HTTPStatus.OK, import_wechat_index_suggestions(payload)); return
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
            if path == "/api/v2/local-vision-ai/download":
                from server.local_vision_ai import start_download
                self._json(HTTPStatus.ACCEPTED, start_download(str(payload.get("model") or ""))); return
            if path == "/api/v2/select-path":
                self._json(HTTPStatus.OK, select_v2_path(str(payload.get("kind") or ""))); return
            match = re.fullmatch(r"/api/v2/task-center/tasks/([a-f0-9]+)/retry", path)
            if match:
                try:
                    from server.template_engine.runner import request_retry
                except ModuleNotFoundError:
                    from template_engine.runner import request_retry
                task_id = match.group(1)
                conn = connection()
                try:
                    template = conn.execute("SELECT 1 FROM template_jobs WHERE id=?", (task_id,)).fetchone()
                    export_attempt = conn.execute("SELECT 1 FROM export_attempts WHERE id=?", (task_id,)).fetchone()
                finally:
                    conn.close()
                self._json(HTTPStatus.OK, request_retry(task_id) if template else requeue_export_attempt(task_id) if export_attempt else requeue_finished_video(task_id)); return
            match = re.fullmatch(r"/api/v2/task-center/tasks/([a-f0-9]+)/re-export", path)
            if match:
                self._json(HTTPStatus.ACCEPTED, requeue_export_attempt(match.group(1))); return
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
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/manual-check", path)
            if match:
                self._json(HTTPStatus.OK, update_task_manual_check(match.group(1), bool(payload.get("enabled", False))))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/template", path)
            if match:
                self._json(HTTPStatus.CREATED, queue_template_job(match.group(1), regenerate=bool(payload.get("regenerate", False))))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/videos", path)
            if match:
                source_material_id = str(payload.get("source_material_id") or "").strip()
                if not source_material_id:
                    raise ValueError("缺少素材 ID")
                self._json(HTTPStatus.CREATED, create_finished_video_task(match.group(1), source_material_id))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/videos/batch", path)
            if match:
                source_material_ids = payload.get("source_material_ids")
                if not isinstance(source_material_ids, list):
                    raise ValueError("缺少素材 ID 列表")
                self._json(HTTPStatus.CREATED, create_finished_video_tasks_batch(match.group(1), source_material_ids))
                return
            match = re.fullmatch(r"/api/v2/production-videos/([a-f0-9]+)/generate", path)
            if match:
                self._json(HTTPStatus.ACCEPTED, start_finished_video_generation(match.group(1)))
                return
            match = re.fullmatch(r"/api/v2/production-videos/([a-f0-9]+)/retry", path)
            if match:
                self._json(HTTPStatus.ACCEPTED, start_finished_video_generation(match.group(1)))
                return
            match = re.fullmatch(r"/api/v2/production-videos/([a-f0-9]+)/open-draft", path)
            if match:
                self._json(HTTPStatus.ACCEPTED, request_open_finished_video_draft(match.group(1)))
                return
            match = re.fullmatch(r"/api/v2/production-tasks/([a-f0-9]+)/template/open-draft", path)
            if match:
                self._json(HTTPStatus.ACCEPTED, request_open_template_draft(match.group(1)))
                return
            if path in {"/api/v2/task-center/pause", "/api/v2/task-center/resume"}:
                try:
                    from server.task_center_service import set_queue_paused, task_center_snapshot
                except ModuleNotFoundError:
                    from task_center_service import set_queue_paused, task_center_snapshot
                set_queue_paused(path.endswith("/pause"))
                self._json(HTTPStatus.OK, task_center_snapshot())
                return
            match = re.fullmatch(r"/api/v2/task-center/executors/([a-z_]+)/(?P<action>pause|resume)", path)
            if match:
                try:
                    from server.task_center_service import set_executor_paused, task_center_snapshot
                except ModuleNotFoundError:
                    from task_center_service import set_executor_paused, task_center_snapshot
                set_executor_paused(match.group(1), match.group("action") == "pause")
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
            match = re.fullmatch(r"/api/v2/wechat-index/keywords/([a-f0-9]+)", urlparse(self.path).path)
            if match:
                self._json(HTTPStatus.OK, update_wechat_index_keyword(match.group(1), payload)); return
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


def create_v2_server(host: str = HOST, port: int = PORT) -> ThreadingHTTPServer:
    """Initialize V2 background services and return its local HTTP server."""
    if WORKSPACE is not None:
        ensure_v2_root_layout()
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        from server.task_center_service import start_scheduler
    except ModuleNotFoundError:
        from task_center_service import start_scheduler
    try:
        from server.revenue_auto_scheduler import start_revenue_auto_scheduler
    except ModuleNotFoundError:
        from revenue_auto_scheduler import start_revenue_auto_scheduler
    try:
        start_scheduler()
        start_revenue_auto_scheduler()
    except Exception:
        server.server_close()
        raise
    return server


def main() -> None:
    server = create_v2_server()
    state = "V2 文件服务已启动" if WORKSPACE is not None else "V2 文件服务已启动：需要配置数据盘"
    print(f"{state}，http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
