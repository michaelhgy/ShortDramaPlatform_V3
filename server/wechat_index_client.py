"""Local, Windows-user-bound client for an already authorized WeChat Index session.

This module never discovers, logs, or uploads a WeChat session.  The desktop
application receives a user-approved captured *index request* during local
initialization, encrypts it with Windows DPAPI, and reuses it only from the
same Windows account.  A different computer or Windows account must initialize
again.
"""

from __future__ import annotations

import ctypes
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import time_ns
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


WECHAT_INDEX_HOST = "search.weixin.qq.com"
WECHAT_INDEX_PATH = "/cgi-bin/wxaweb/wxindex"
_BLOCKED_HEADERS = {"content-length", "content-type", "host", "connection", "proxy-connection", "accept-encoding"}


class WechatIndexConnectionError(RuntimeError):
    """A local connection profile is absent, invalid, expired, or rejected."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, object]:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _crypt_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise WechatIndexConnectionError("微信指数连接仅支持 Windows 本地桌面软件")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise WechatIndexConnectionError("无法使用当前 Windows 用户加密微信指数连接")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        del source_buffer


def _crypt_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise WechatIndexConnectionError("微信指数连接仅支持 Windows 本地桌面软件")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise WechatIndexConnectionError("本机微信指数连接已不可用，请重新初始化")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)
        del source_buffer


def _profile_paths(data_root: Path) -> tuple[Path, Path]:
    root = data_root.resolve() / "connections" / "wechat-index"
    return root / "session.bin", root / "status.json"


def capture_inbox_path(data_root: Path) -> Path:
    return data_root.resolve() / "connections" / "wechat-index" / "capture-inbox"


def save_captured_response(data_root: Path, kind: str, query: str, response: object) -> None:
    """Persist a non-secret response atomically for the V2 service to ingest."""
    if kind not in {"history", "suggestions"} or not isinstance(response, dict) or not query.strip():
        return
    _reject = {"openid", "search_key", "cookie", "authorization", "token"}
    if _reject.intersection(str(key).casefold() for key in response):
        return
    root = capture_inbox_path(data_root); root.mkdir(parents=True, exist_ok=True)
    item = {"kind": kind, "query": query, "response": response, "received_at": datetime.now().isoformat(timespec="seconds")}
    target = root / f"{time_ns()}-{uuid.uuid4().hex}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(item, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)


def _validate_template(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("连接初始化数据必须是对象")
    url = str(payload.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != WECHAT_INDEX_HOST or parsed.path != WECHAT_INDEX_PATH:
        raise ValueError("只接受微信指数 wxindex 的 HTTPS 请求")
    headers = payload.get("headers")
    body = payload.get("body")
    if not isinstance(headers, dict) or not isinstance(body, dict):
        raise ValueError("连接初始化需要请求头和请求体")
    if not str(body.get("openid") or "").strip() or not str(body.get("search_key") or "").strip():
        raise ValueError("请求体缺少当前微信指数会话参数")
    query = body.get("query")
    if not isinstance(query, list) or not query or not str(query[0]).strip():
        raise ValueError("请先在微信指数手动查询一个关键词，再导入该 wxindex 请求")
    cleaned_headers = {
        str(key): str(value)
        for key, value in headers.items()
        if str(key).strip() and str(key).casefold() not in _BLOCKED_HEADERS and len(str(value)) <= 16_000
    }
    if not cleaned_headers:
        raise ValueError("请求头不能为空")
    return {"url": url, "headers": cleaned_headers, "body": body}


def save_connection_template(data_root: Path, payload: object) -> dict[str, object]:
    template = _validate_template(payload)
    session_path, status_path = _profile_paths(data_root)
    session_path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = _crypt_protect(json.dumps(template, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    temporary = session_path.with_name(f".{session_path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(session_path)
    stamp = datetime.now().isoformat(timespec="seconds")
    status_path.write_text(json.dumps({"initialized_at": stamp, "endpoint": WECHAT_INDEX_PATH}, ensure_ascii=False), encoding="utf-8")
    return {"status": "connected", "initialized_at": stamp, "stores_session_in_database": False}


def connection_status(data_root: Path) -> dict[str, object]:
    session_path, status_path = _profile_paths(data_root)
    if not session_path.is_file():
        return {"status": "not_connected", "message": "尚未连接本机微信指数。请先在微信中手动查询一个关键词。", "stores_session_in_database": False}
    try:
        _validate_template(json.loads(_crypt_unprotect(session_path.read_bytes()).decode("utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, WechatIndexConnectionError):
        return {"status": "needs_reconnect", "message": "本机微信指数连接已不可用，请重新初始化。", "stores_session_in_database": False}
    initialized_at = ""
    try:
        initialized_at = str(json.loads(status_path.read_text(encoding="utf-8")).get("initialized_at") or "")
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {"status": "connected", "initialized_at": initialized_at, "stores_session_in_database": False}


@dataclass(frozen=True)
class WechatIndexClient:
    data_root: Path

    def _template(self) -> dict[str, object]:
        session_path, _ = _profile_paths(self.data_root)
        if not session_path.is_file():
            raise WechatIndexConnectionError("尚未连接本机微信指数")
        try:
            return _validate_template(json.loads(_crypt_unprotect(session_path.read_bytes()).decode("utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, WechatIndexConnectionError) as exc:
            raise WechatIndexConnectionError("本机微信指数连接已不可用，请重新初始化") from exc

    def fetch_history(self, keyword: str) -> dict[str, object]:
        template = self._template()
        body = dict(template["body"])
        body["query"] = [keyword]
        request = Request(
            str(template["url"]),
            data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={**template["headers"], "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=25) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            raise WechatIndexConnectionError(f"微信指数请求被拒绝（HTTP {exc.code}），请重新初始化连接") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise WechatIndexConnectionError(f"微信指数请求失败：{exc.reason if isinstance(exc, URLError) else exc}") from exc
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WechatIndexConnectionError("微信指数返回的不是可识别 JSON 数据") from exc
        if not isinstance(parsed, dict):
            raise WechatIndexConnectionError("微信指数返回的数据结构无效")
        return parsed
