"""Small HTTP adapter for the public-template UI; no producer or scheduler."""

from __future__ import annotations

import os
import re
import sqlite3
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from server.template_library import TemplateLibrary


def stream_video(handler, path) -> None:
    size = path.stat().st_size
    start, end, status = 0, size - 1, HTTPStatus.OK
    requested = handler.headers.get("Range")
    if requested:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
        valid = match is not None and bool(match[1] or match[2])
        if valid:
            if match[1]:
                start = int(match[1])
                end = min(size - 1, int(match[2])) if match[2] else size - 1
            else:
                valid = int(match[2]) > 0
                start = max(0, size - int(match[2]))
            valid = valid and 0 <= start <= end < size
        if not valid:
            handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        status = HTTPStatus.PARTIAL_CONTENT
    handler.send_response(status)
    handler.send_header("Content-Type", "video/mp4")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    if status == HTTPStatus.PARTIAL_CONTENT:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()
    try:
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = stream.read(min(1024 * 256, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


def handle_template_library(handler, method: str, path: str, payload: dict | None = None) -> bool:
    if not path.startswith("/api/v2/template-library"):
        return False
    from server import v2_file_service as service

    try:
        workspace, data_root = service.require_configured_paths()
        library = TemplateLibrary(workspace, data_root, service.connection, service.probe_resource_metadata)
        if method == "GET":
            if path == "/api/v2/template-library":
                task_id = parse_qs(urlparse(handler.path).query).get("task_id", [""])[0]
                handler._json(HTTPStatus.OK, library.catalogue(task_id))
                return True
            match = re.fullmatch(r"/api/v2/template-library/([a-f0-9]{64})/(media|thumbnail)", path)
            if match:
                media = library.media(match[1], thumbnail=match[2] == "thumbnail")
                if match[2] == "thumbnail":
                    handler._binary(media, "image/jpeg")
                else:
                    stream_video(handler, media)
                return True
        elif method == "POST":
            payload = payload or {}
            if not isinstance(payload, dict):
                raise ValueError("模板操作内容无效")
            task_id = str(payload.get("task_id") or "")
            if path == "/api/v2/template-library/refresh":
                library.task(task_id)
                result = library.refresh()
                handler._json(HTTPStatus.OK, {**library.catalogue(task_id), **result})
                return True
            if path == "/api/v2/template-library/select":
                value = payload.get("template_id")
                if value is not None and not isinstance(value, str):
                    raise ValueError("模板编号无效")
                handler._json(HTTPStatus.OK, library.select(task_id, value))
                return True
            if path == "/api/v2/template-library/delete":
                library.task(task_id)
                result = library.delete(str(payload.get('template_id') or ''))
                handler._json(HTTPStatus.OK, {**library.catalogue(task_id), **result})
                return True
            if path == "/api/v2/template-library/open-folder":
                library.directory.mkdir(parents=True, exist_ok=True)
                os.startfile(str(library.directory))
                handler._json(HTTPStatus.OK, {"opened": True})
                return True
        handler._json(HTTPStatus.NOT_FOUND, {"error": "模板操作不存在"})
    except (ValueError, RuntimeError, OSError) as exc:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
    except sqlite3.Error:
        handler._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "模板记录暂时不可用，请稍后重试"})
    return True
