from __future__ import annotations

import base64
import itertools
import json
import os
import socket
import struct
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse


class CDPError(RuntimeError):
    """Chrome DevTools Protocol connection or command error."""


@dataclass(frozen=True)
class Target:
    id: str
    type: str
    title: str
    url: str
    websocket_url: str


def list_targets(endpoint: str = "http://127.0.0.1:9222") -> list[Target]:
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/json/list", timeout=3) as response:
            raw = json.load(response)
    except Exception as exc:  # pragma: no cover - exercised on Windows runtime
        raise CDPError(f"无法连接小V猫远程调试端口：{exc}") from exc
    return [
        Target(
            id=str(item.get("id") or ""),
            type=str(item.get("type") or ""),
            title=str(item.get("title") or ""),
            url=str(item.get("url") or ""),
            websocket_url=str(item.get("webSocketDebuggerUrl") or ""),
        )
        for item in raw
        if item.get("id") and item.get("webSocketDebuggerUrl")
    ]


class CDPConnection:
    """Small standard-library CDP client.

    V3 queries the running Xiao V Cat through this local standard-library client;
    no separate browser installation or automation package is required at runtime.
    """

    def __init__(self, websocket_url: str, timeout: float = 5.0) -> None:
        parsed = urlparse(websocket_url)
        if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
            raise CDPError(f"无效的 CDP WebSocket 地址：{websocket_url}")
        self._socket = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        self._socket.settimeout(timeout)
        self._buffer = bytearray()
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")
        self._socket.sendall(request)
        response = self._read_until(b"\r\n\r\n")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            self.close()
            raise CDPError("CDP WebSocket 握手失败")
        header_end = response.index(b"\r\n\r\n") + 4
        self._buffer.extend(response[header_end:])
        self._next_id = itertools.count(1)

    def _read_until(self, marker: bytes) -> bytes:
        data = b""
        while marker not in data:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise CDPError("CDP 连接提前关闭")
            data += chunk
        return data

    def _read_exact(self, size: int) -> bytes:
        data = bytes(self._buffer[:size])
        del self._buffer[:len(data)]
        while len(data) < size:
            chunk = self._socket.recv(size - len(data))
            if not chunk:
                raise CDPError("CDP 连接提前关闭")
            data += chunk
        return data

    def _send_frame(self, payload: bytes, opcode: int = 1) -> None:
        mask = os.urandom(4)
        size = len(payload)
        if size < 126:
            header = bytes((0x80 | opcode, 0x80 | size))
        elif size < 65536:
            header = bytes((0x80 | opcode, 0x80 | 126)) + struct.pack("!H", size)
        else:
            header = bytes((0x80 | opcode, 0x80 | 127)) + struct.pack("!Q", size)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self._socket.sendall(header + mask + masked)

    def _read_frame(self) -> tuple[int, bytes]:
        first, second = self._read_exact(2)
        opcode = first & 0x0F
        size = second & 0x7F
        if size == 126:
            size = struct.unpack("!H", self._read_exact(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", self._read_exact(8))[0]
        masked = bool(second & 0x80)
        mask = self._read_exact(4) if masked else b""
        payload = self._read_exact(size)
        if masked:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, payload

    def send(self, method: str, params: dict[str, Any] | None = None) -> int:
        command_id = next(self._next_id)
        self._send_frame(
            json.dumps(
                {"id": command_id, "method": method, "params": params or {}},
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return command_id

    def receive(self) -> dict[str, Any] | None:
        try:
            opcode, payload = self._read_frame()
        except socket.timeout:
            return None
        if opcode == 9:  # ping
            self._send_frame(payload, opcode=10)
            return None
        if opcode in {8, 10}:
            if opcode == 8: raise CDPError('小V猫连接已关闭')
            return None
        if opcode != 1:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
        command_id = self.send(method, params)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive()
            if message is None:
                continue
            if message.get("id") == command_id:
                if "error" in message:
                    raise CDPError(f"CDP {method} 失败：{message['error']}")
                return message
        raise CDPError(f"CDP {method} 超时")

    def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        timeout: float = 10.0,
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive()
            if message is not None and predicate(message):
                return message
        return None

    def close(self) -> None:
        try:
            self._socket.close()
        except Exception:
            pass
