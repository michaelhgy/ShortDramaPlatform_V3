"""Persistent public-template catalogue, separate from the legacy draft engine.

The template producer owns rendering. This module indexes finished MP4 files,
stores one selection per production task and records successful outputs only
when the future compositor explicitly reports them.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime
from contextlib import closing
from pathlib import Path
from typing import Callable


SCHEMA_VERSION = 2


class TemplateLibrary:
    def __init__(self, workspace: Path, data_root: Path, connection: Callable, probe: Callable) -> None:
        self.workspace = workspace.resolve()
        self.directory = self.workspace / "内容资产" / "公共模板"
        self.data_root = data_root.resolve()
        self.database = self.data_root / "database" / "v3_template_library.db"
        self.business_connection = connection
        self.probe = probe

    def connect(self) -> sqlite3.Connection:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database, timeout=15)
        conn.row_factory = sqlite3.Row
        version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            conn.close()
            raise ValueError("模板库来自更新版本，请使用对应的软件版本打开")
        if version != SCHEMA_VERSION:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, file_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL DEFAULT 0, resolution TEXT NOT NULL DEFAULT '',
                    thumbnail_path TEXT NOT NULL DEFAULT '', present INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS selections (
                    task_id TEXT PRIMARY KEY, template_id TEXT NOT NULL,
                    account_key TEXT NOT NULL, account_name TEXT NOT NULL,
                    drama_key TEXT NOT NULL, drama_name TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS selection_scope
                    ON selections(template_id, drama_key, account_key);
                CREATE TABLE IF NOT EXISTS outputs (
                    output_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, template_id TEXT NOT NULL,
                    account_key TEXT NOT NULL, account_name TEXT NOT NULL,
                    drama_key TEXT NOT NULL, drama_name TEXT NOT NULL,
                    output_path TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS output_template ON outputs(template_id);
            """)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS library_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS final_jobs(
                    id TEXT PRIMARY KEY,task_id TEXT NOT NULL,material_id TEXT NOT NULL,template_id TEXT NOT NULL,
                    status TEXT NOT NULL,plan TEXT NOT NULL,progress INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',attempt INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,started_at TEXT,completed_at TEXT,output_path TEXT,
                    output_sha256 TEXT,package_path TEXT,UNIQUE(task_id,material_id)
                );
                CREATE TABLE IF NOT EXISTS deleted_templates(id TEXT PRIMARY KEY,deleted_at TEXT NOT NULL,trash_path TEXT NOT NULL);
            """)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            conn.commit()
        # A business-data reset keeps the schema version but may clear settings.
        # Check first so ordinary catalogue reads do not acquire a write lock.
        if conn.execute("SELECT 1 FROM library_settings WHERE key='usage_limit'").fetchone() is None:
            conn.execute("INSERT OR IGNORE INTO library_settings VALUES('usage_limit','20')")
            conn.commit()
        return conn

    def set_usage_limit(self, limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 2**53-1:
            raise ValueError('每个模板使用上限必须为可精确表示的正整数')
        with closing(self.connect()) as conn:
            conn.execute("UPDATE library_settings SET value=? WHERE key='usage_limit'", (str(limit),))
            conn.commit()

    @staticmethod
    def usage_limit(conn) -> int:
        return int(conn.execute("SELECT value FROM library_settings WHERE key='usage_limit'").fetchone()[0])

    @staticmethod
    def active_count(conn, template_id: str) -> int:
        return conn.execute("SELECT COUNT(*) FROM final_jobs WHERE template_id=? AND status IN ('waiting','running')", (template_id,)).fetchone()[0]

    @staticmethod
    def used_drama_keys(conn, template_id: str) -> set[str]:
        return {r[0] for r in conn.execute('SELECT DISTINCT drama_key FROM outputs WHERE template_id=?', (template_id,))}

    @staticmethod
    def reserved_drama_keys(conn, template_id: str) -> set[str]:
        rows = conn.execute("""SELECT COALESCE(json_extract(j.plan,'$.drama_key'), s.drama_key,
            'name:' || json_extract(j.plan,'$.drama_name'), 'legacy-task:' || j.task_id)
            FROM final_jobs j LEFT JOIN selections s ON s.task_id=j.task_id
            WHERE j.template_id=? AND j.status IN ('waiting','running')""", (template_id,))
        return {r[0] for r in rows} - TemplateLibrary.used_drama_keys(conn, template_id)

    @staticmethod
    def reserved(conn, template_id: str) -> int:
        return len(TemplateLibrary.reserved_drama_keys(conn, template_id))

    @staticmethod
    def can_use(conn, template_id: str, drama_key: str) -> bool:
        claimed = TemplateLibrary.used_drama_keys(conn, template_id) | TemplateLibrary.reserved_drama_keys(conn, template_id)
        return drama_key in claimed or len(claimed) < TemplateLibrary.usage_limit(conn)

    @staticmethod
    def short_name(name: str) -> str:
        match = re.fullmatch(r'模板_(\d{4})-(\d{2})-(\d{2})_([a-f0-9]+)', name)
        return f'模板{match[2]}{match[3]}-{match[4][:4].upper()}' if match else name

    def task(self, task_id: str) -> dict:
        with closing(self.business_connection()) as conn:
            row = conn.execute("SELECT * FROM production_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("制作任务不存在，请刷新任务列表")
            task = dict(row)
            account = conn.execute("SELECT id FROM accounts WHERE nickname=?", (task["account_name"],)).fetchone()
            drama = conn.execute(
                "SELECT id FROM dramas WHERE current_name=? OR id IN "
                "(SELECT drama_id FROM drama_aliases WHERE alias_name=?) LIMIT 1",
                (task["drama_name"], task["drama_name"]),
            ).fetchone()
            task["account_key"] = "id:" + str(account[0]) if account else "name:" + task["account_name"]
            task["drama_key"] = "id:" + str(drama[0]) if drama else "name:" + task["drama_name"]
            return task

    def current_file(self, row: sqlite3.Row | dict) -> Path | None:
        path = Path(row["file_path"]).resolve()
        if not path.is_relative_to(self.directory.resolve()) or path.suffix.lower() != ".mp4":
            return None
        try:
            stat = path.stat()
            return path if path.is_file() and stat.st_size == row["size_bytes"] and stat.st_mtime_ns == row["mtime_ns"] else None
        except OSError:
            return None

    @staticmethod
    def conflict(conn: sqlite3.Connection, template_id: str, task: dict) -> str:
        row = conn.execute(
            "SELECT account_name FROM selections WHERE template_id=? AND drama_key=? AND account_key<>? "
            "UNION SELECT account_name FROM outputs WHERE template_id=? AND drama_key=? AND account_key<>? LIMIT 1",
            (template_id, task["drama_key"], task["account_key"], template_id, task["drama_key"], task["account_key"]),
        ).fetchone()
        return f"本剧已被 {row[0]} 选用或使用" if row else ""

    def refresh(self) -> dict:
        """Explicit refresh only; never consume, rename or delete source files."""
        warnings: list[str] = []
        with closing(self.connect()) as conn:
            seen: set[str] = set()
            records = []
            paths = sorted(path for path in self.directory.iterdir() if path.suffix.lower() == ".mp4") if self.directory.is_dir() else []
            for path in paths:
                try:
                    path = path.resolve()
                    if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
                        continue
                    stat = path.stat()
                    previous = conn.execute(
                        "SELECT * FROM templates WHERE file_path=? AND size_bytes=? AND mtime_ns=?",
                        (str(path), stat.st_size, stat.st_mtime_ns),
                    ).fetchone()
                    if previous:
                        seen.add(previous["id"])
                        continue
                    with path.open("rb") as stream:
                        template_id = hashlib.file_digest(stream, "sha256").hexdigest()
                    duration, resolution, thumbnail = self.probe(path, "public-template-" + template_id)
                    if duration <= 0 or not resolution:
                        warnings.append(f"{path.name}：未能读取有效视频信息")
                        continue
                    after = path.stat()
                    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                        warnings.append(f"{path.name}：文件仍在变化，请制作完成后再刷新")
                        continue
                    records.append((template_id, path.stem, str(path), stat.st_size, stat.st_mtime_ns, duration, resolution, thumbnail))
                    seen.add(template_id)
                except (OSError, ValueError, RuntimeError) as exc:
                    warnings.append(f"{path.name}：{exc}")
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                "INSERT INTO templates(id,name,file_path,size_bytes,mtime_ns,duration_seconds,resolution,thumbnail_path,present) "
                "VALUES (?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name,file_path=excluded.file_path,size_bytes=excluded.size_bytes,mtime_ns=excluded.mtime_ns,"
                "duration_seconds=excluded.duration_seconds,resolution=excluded.resolution,thumbnail_path=excluded.thumbnail_path,present=1",
                records,
            )
            rows = conn.execute("SELECT id FROM templates").fetchall()
            for row in rows:
                conn.execute("UPDATE templates SET present=? WHERE id=?", (int(row["id"] in seen), row["id"]))
            conn.commit()
        return {"indexed": len(seen), "warnings": warnings}

    def catalogue(self, task_id: str) -> dict:
        task = self.task(task_id)
        with closing(self.connect()) as conn:
            with closing(self.business_connection()) as business:
                task_ids = {row[0] for row in business.execute("SELECT id FROM production_tasks")}
            for selection in conn.execute("SELECT task_id FROM selections").fetchall():
                if selection[0] not in task_ids:
                    conn.execute("DELETE FROM selections WHERE task_id=?", (selection[0],))
            conn.commit()
            selected = conn.execute("SELECT template_id FROM selections WHERE task_id=?", (task_id,)).fetchone()
            used = bool(conn.execute("SELECT 1 FROM outputs WHERE task_id=? LIMIT 1", (task_id,)).fetchone())
            active = bool(conn.execute("SELECT 1 FROM final_jobs WHERE task_id=? AND status IN ('waiting','running')", (task_id,)).fetchone())
            locked = used or active or task.get("release_status") == "registered" or task.get("cleanup_status", "active") != "active"
            limit = self.usage_limit(conn)
            items = []
            for row in conn.execute(
                "SELECT t.*, (SELECT COUNT(DISTINCT drama_key) FROM outputs o WHERE o.template_id=t.id) AS usage_count "
                "FROM templates t WHERE present=1 AND NOT EXISTS(SELECT 1 FROM deleted_templates d WHERE d.id=t.id) ORDER BY name COLLATE NOCASE, id"
            ).fetchall():
                present = self.current_file(row) is not None
                if not present or (row['usage_count'] >= limit and task['drama_key'] not in self.used_drama_keys(conn, row['id'])):
                    continue
                reserved = self.reserved(conn, row['id'])
                reason = '剩余剧集名额已被占用' if not self.can_use(conn, row['id'], task['drama_key']) else ''
                reason = reason or self.conflict(conn, row["id"], task)
                preview = f"/api/v2/template-library/{row['id']}/media" if present else None
                thumbnail = Path(row["thumbnail_path"]) if row["thumbnail_path"] else None
                items.append({
                    "id": row["id"], "name": self.short_name(row["name"]), "file_name": Path(row['file_path']).name, "duration_seconds": row["duration_seconds"],
                    "usage_limit": limit, "reserved_count": reserved, "can_delete": self.active_count(conn, row["id"]) == 0,
                    "resolution": row["resolution"], "size_bytes": row["size_bytes"], "usage_count": row["usage_count"],
                    "preview_url": preview,
                    "thumbnail_url": f"/api/v2/template-library/{row['id']}/thumbnail" if thumbnail and thumbnail.is_file() else None,
                    "available": present and not reason, "unavailable_reason": reason,
                })
            visible = {item['id'] for item in items}
            return {"items": items, "selected_template_id": selected[0] if selected and selected[0] in visible else None,
                    "selection_locked": locked, "selection_lock_reason": "本任务已有成片、合成队列或已结束，不能直接更换模板" if locked else "",
                    "directory": str(self.directory)}

    def select(self, task_id: str, template_id: str | None) -> dict:
        from server.ffmpeg_finals.lifecycle import final_job_lock
        with final_job_lock(self.data_root):
            return self._select_locked(task_id, template_id)

    def _select_locked(self, task_id: str, template_id: str | None) -> dict:
        task = self.task(task_id)
        with closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            selected = conn.execute("SELECT template_id FROM selections WHERE task_id=?", (task_id,)).fetchone()
            unchanged = (selected[0] if selected else None) == template_id
            if not unchanged:
                has_outputs = conn.execute("SELECT 1 FROM outputs WHERE task_id=? LIMIT 1", (task_id,)).fetchone()
                active = conn.execute("SELECT 1 FROM final_jobs WHERE task_id=? AND status IN ('waiting','running')", (task_id,)).fetchone()
                if has_outputs or active or task.get("release_status") == "registered" or task.get("cleanup_status", "active") != "active":
                    raise ValueError("本任务已有成片记录或已结束，不能直接更换模板")
                if template_id is None:
                    conn.execute("DELETE FROM selections WHERE task_id=?", (task_id,))
                else:
                    row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
                    if row is None or self.current_file(row) is None:
                        raise ValueError("模板文件不可用，请刷新模板后重新选择")
                    if not self.can_use(conn, template_id, task['drama_key']):
                        raise ValueError('模板已达到使用上限或剩余次数已被占用')
                    if conn.execute('SELECT 1 FROM deleted_templates WHERE id=?', (template_id,)).fetchone():
                        raise ValueError('模板已删除')
                    reason = self.conflict(conn, template_id, task)
                    if reason:
                        raise ValueError(reason)
                    conn.execute(
                        "INSERT INTO selections(task_id,template_id,account_key,account_name,drama_key,drama_name) "
                        "VALUES (?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET template_id=excluded.template_id,"
                        "account_key=excluded.account_key,account_name=excluded.account_name,drama_key=excluded.drama_key,drama_name=excluded.drama_name",
                        (task_id, template_id, task["account_key"], task["account_name"], task["drama_key"], task["drama_name"]),
                    )
            conn.commit()
        return self.catalogue(task_id)

    def delete(self, template_id: str) -> dict:
        """Remove from the public pool; preserve dependent layers and success history."""
        with closing(self.connect()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM templates WHERE id=?', (template_id,)).fetchone()
            if not row:
                raise ValueError('模板不存在')
            if self.active_count(conn, template_id):
                raise ValueError('模板正在被排队或执行中的成片使用，请完成或取消这些任务后再删除')
            prior = conn.execute('SELECT trash_path FROM deleted_templates WHERE id=?', (template_id,)).fetchone()
            if prior:
                return {'deleted': True, 'trash_path': prior[0]}
            path = self.current_file(row)
            trash = self.data_root / 'template_trash' / (template_id[:12] + '_' + datetime.now().strftime('%Y%m%d%H%M%S%f'))
            moved = []
            try:
                if path:
                    trash.mkdir(parents=True)
                    for source in (path, path.with_suffix('.template.json')):
                        if source.is_file():
                            destination = trash / source.name
                            shutil.move(str(source), str(destination)); moved.append((source,destination))
                conn.execute('INSERT INTO deleted_templates VALUES(?,?,?)', (template_id,datetime.now().isoformat(),str(trash)))
                conn.execute('UPDATE templates SET present=0 WHERE id=?', (template_id,))
                conn.execute('DELETE FROM selections WHERE template_id=? AND task_id NOT IN (SELECT task_id FROM outputs)', (template_id,))
                conn.commit()
            except BaseException:
                conn.rollback()
                for source,destination in reversed(moved):
                    if destination.is_file() and not source.exists():shutil.move(str(destination),str(source))
                raise
        return {'deleted': True, 'trash_path': str(trash)}

    def record_output(self, task_id: str, output_id: str, output_path: Path) -> None:
        """Integration hook; selecting/previewing never calls this method."""
        output_path = output_path.resolve()
        if not output_path.is_relative_to(self.workspace) or not output_path.is_file() or output_path.stat().st_size <= 0:
            raise ValueError("只有实际成功生成的工作区成片可以计次")
        task = self.task(task_id)
        with closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            selected = conn.execute("SELECT template_id FROM selections WHERE task_id=?", (task_id,)).fetchone()
            if selected is None:
                raise ValueError("任务尚未选用模板")
            prior = conn.execute("SELECT task_id,template_id FROM outputs WHERE output_id=?", (output_id,)).fetchone()
            if prior and (prior["task_id"] != task_id or prior["template_id"] != selected[0]):
                raise ValueError("成片记录已归属其他任务或模板")
            conn.execute(
                "INSERT OR IGNORE INTO outputs(output_id,task_id,template_id,account_key,account_name,drama_key,drama_name,output_path) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (output_id, task_id, selected[0], task["account_key"], task["account_name"], task["drama_key"], task["drama_name"], str(output_path)),
            )
            conn.commit()

    def media(self, template_id: str, thumbnail: bool = False) -> Path:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
        current = self.current_file(row) if row else None
        if current is None:
            raise ValueError("模板文件不可用，请刷新模板")
        if thumbnail:
            path = Path(row["thumbnail_path"]).resolve() if row["thumbnail_path"] else None
            if path is None or not path.is_relative_to(self.data_root) or not path.is_file():
                raise ValueError("模板缩略图尚未就绪")
            return path
        return current
