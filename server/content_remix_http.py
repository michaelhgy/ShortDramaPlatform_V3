from __future__ import annotations

import re
import threading
from http import HTTPStatus
from pathlib import Path

from . import v2_file_service
from .content_highlight_library import ensure_preview, get_library, list_libraries
from .content_remix_service import get_run, list_runs, start_run


BASE = "/api/v3/content-remix"


def _data_root() -> Path:
    if v2_file_service.DATA_ROOT is None:
        raise RuntimeError("需要先配置数据盘")
    return Path(str(v2_file_service.DATA_ROOT))


def find_source_folder(candidates: list[Path]) -> tuple[Path | None, int, int]:
    """返回 (直接存放 MP4 的目录, MP4 数量, 总字节)。只看目录本身和下一层子目录，不递归整棵树，
    避免网络盘上扫描过慢导致界面超时。"""
    for candidate in candidates:
        try:
            if not candidate.is_dir():
                continue
            folders = [candidate] + sorted(p for p in candidate.iterdir() if p.is_dir())
        except OSError:
            continue
        for folder in folders:
            try:
                files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"]
            except OSError:
                continue
            if files:
                size = 0
                for file in files:
                    try:
                        size += file.stat().st_size
                    except OSError:
                        pass
                return folder, len(files), size
    return None, 0, 0


ROOT_CHECK_TIMEOUT_S = 30.0


def _is_dir_within(path: Path, timeout_s: float) -> bool:
    """网络盘断开时 is_dir 会卡一分钟以上；超过时限就当作访问不到，让界面尽快给出提示。"""
    result: list[bool] = []

    def check() -> None:
        try:
            result.append(path.is_dir())
        except OSError:
            result.append(False)

    worker = threading.Thread(target=check, daemon=True)
    worker.start()
    worker.join(timeout_s)
    return bool(result and result[0])


def list_source_dramas() -> dict:
    """二创制作页的原剧下拉：所有剧集 + 实际找到的原片目录。剧集没有资料记录也能被找到。"""
    from . import v2_file_service as v2
    root = Path(str(v2.get_v2_settings().get("drama_download_root") or "")).expanduser()
    root_ok = bool(str(root).strip()) and _is_dir_within(root, ROOT_CHECK_TIMEOUT_S)
    conn = v2.connection()
    try:
        rows = conn.execute("""SELECT d.id, d.current_name, t.name AS theater_name,
                COALESCE(p.master_path, '') AS master_path
            FROM dramas d JOIN theaters t ON t.id=d.theater_id
            LEFT JOIN drama_profiles p ON p.drama_id=d.id""").fetchall()
    finally:
        conn.close()
    items = []
    for row in rows:
        name, theater = str(row["current_name"]), str(row["theater_name"])
        candidates = [root / theater / name, root / name] if root_ok else []
        if row["master_path"]:
            candidates.append(Path(str(row["master_path"])))
        folder, count, size = find_source_folder(candidates)
        items.append({
            "drama_id": row["id"], "drama_title": name, "theater_name": theater,
            "directory": str(folder) if folder else "", "mp4_count": count,
            "size_gb": round(size / 1024 ** 3, 2),
        })
    return {"download_root": str(root), "download_root_ok": root_ok, "items": items}


def handle(handler, method: str, path: str, payload: dict | None = None) -> bool:
    if not path.startswith(BASE):
        return False
    try:
        if method == "GET" and path == BASE + "/source-dramas":
            handler._json(HTTPStatus.OK, list_source_dramas())
            return True
        if method == "GET" and path == BASE + "/runs":
            handler._json(HTTPStatus.OK, {"items": list_runs()})
            return True
        match = re.fullmatch(re.escape(BASE) + r"/highlights/([A-Za-z0-9_-]+)", path)
        if method == "GET" and match:
            drama_id = match.group(1)
            libraries = list_libraries(_data_root(), drama_id)
            latest = get_library(_data_root(), drama_id)
            handler._json(HTTPStatus.OK, {"libraries": libraries, "latest": latest})
            return True
        match = re.fullmatch(re.escape(BASE) + r"/highlights/([A-Za-z0-9_-]+)/items/([A-Za-z0-9_-]+)/preview", path)
        if method == "GET" and match:
            drama_id, highlight_id = match.group(1), match.group(2)
            preview = ensure_preview(_data_root(), drama_id, highlight_id)
            handler._binary(preview, "video/mp4", cache_control="private, max-age=3600")
            return True
        match = re.fullmatch(re.escape(BASE) + r"/highlights/([A-Za-z0-9_-]+)/versions/([A-Za-z0-9_-]+)", path)
        if method == "GET" and match:
            drama_id, version_id = match.group(1), match.group(2)
            library = get_library(_data_root(), drama_id, version_id)
            if library is None:
                handler._json(HTTPStatus.NOT_FOUND, {"error": "高光资料版本不存在"})
            else:
                handler._json(HTTPStatus.OK, library)
            return True
        match = re.fullmatch(re.escape(BASE) + r"/runs/([a-f0-9]{32})", path)
        if method == "GET" and match:
            handler._json(HTTPStatus.OK, get_run(match.group(1)))
            return True
        if method == "POST" and path == BASE + "/runs":
            handler._json(HTTPStatus.ACCEPTED, start_run(payload or {}))
            return True
        handler._json(HTTPStatus.NOT_FOUND, {"error": "内容生产接口不存在"})
    except ValueError as exc:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        handler._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
    return True
