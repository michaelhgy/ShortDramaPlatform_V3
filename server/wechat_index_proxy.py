"""Explicit, local-only WeChat Index capture proxy lifecycle for Windows.

The proxy is opt-in. Starting it temporarily changes only the current user's
Windows HTTP proxy and installs its generated CA in the *current-user* Root
store. Stopping it restores the prior proxy values and removes that exact CA.
Only the wxindex request is persisted, via the DPAPI-backed connection store.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import winreg
from pathlib import Path

from server.application_resources import application_resource_path
from server.runtime_process import no_window_kwargs


PROXY_HOST = "127.0.0.1"
PORT_START = 19090
PORT_END = 19110
_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_PROXY_VALUES = ("ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL")


class WechatIndexProxyError(RuntimeError):
    pass


def _root(data_root: Path) -> Path:
    return data_root.resolve() / "connections" / "wechat-index" / "capture-proxy"


def _state_path(data_root: Path) -> Path:
    return _root(data_root) / "state.json"


def _read_state(data_root: Path) -> dict[str, object]:
    try:
        value = json.loads(_state_path(data_root).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_state(data_root: Path, value: dict[str, object]) -> None:
    target = _state_path(data_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)


def _registry_snapshot() -> dict[str, object]:
    values: dict[str, object] = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH, 0, winreg.KEY_READ) as key:
        for name in _PROXY_VALUES:
            try:
                value, kind = winreg.QueryValueEx(key, name)
                values[name] = {"exists": True, "value": value, "kind": kind}
            except FileNotFoundError:
                values[name] = {"exists": False}
    return values


def _set_registry_value(key: object, name: str, saved: object) -> None:
    if not isinstance(saved, dict) or not saved.get("exists"):
        try: winreg.DeleteValue(key, name)
        except FileNotFoundError: pass
        return
    winreg.SetValueEx(key, name, 0, int(saved["kind"]), saved["value"])


def _notify_proxy_change() -> None:
    # INTERNET_OPTION_SETTINGS_CHANGED then INTERNET_OPTION_REFRESH.
    wininet = __import__("ctypes").windll.wininet
    wininet.InternetSetOptionW(0, 39, None, 0)
    wininet.InternetSetOptionW(0, 37, None, 0)


def _previous_proxy_server(snapshot: object) -> str:
    if not isinstance(snapshot, dict):
        return ""
    enabled = snapshot.get("ProxyEnable")
    server = snapshot.get("ProxyServer")
    if not isinstance(enabled, dict) or not enabled.get("exists") or int(enabled.get("value") or 0) != 1:
        return ""
    if not isinstance(server, dict) or not server.get("exists"):
        return ""
    value = str(server.get("value") or "").strip()
    return value if re.fullmatch(r"[A-Za-z0-9._-]+:\d{1,5}", value) else ""


def _apply_proxy(port: int, previous_proxy: object) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        # Use the capture proxy as the temporary front proxy, then route it to
        # the user's original proxy (for example mihomo). This is necessary
        # for WeChat, which does not reliably honor PAC rules. The addon still
        # decrypts and persists only the WeChat Index host.
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{PROXY_HOST}:{port}")
        if isinstance(previous_proxy, dict):
            _set_registry_value(key, "ProxyOverride", previous_proxy.get("ProxyOverride"))
        else:
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>;127.0.0.1;localhost")
        try: winreg.DeleteValue(key, "AutoConfigURL")
        except FileNotFoundError: pass
    _notify_proxy_change()


def _restore_proxy(snapshot: object, port: int) -> bool:
    current = _registry_snapshot()
    if current.get("ProxyEnable", {}).get("value") != 1 or current.get("ProxyServer", {}).get("value") != f"{PROXY_HOST}:{port}":
        return False
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        for name in _PROXY_VALUES:
            _set_registry_value(key, name, snapshot.get(name) if isinstance(snapshot, dict) else None)
    _notify_proxy_change()
    return True


def _free_port() -> int:
    for port in range(PORT_START, PORT_END):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((PROXY_HOST, port))
            except OSError:
                continue
            return port
    raise WechatIndexProxyError("没有可用的本机微信指数采集端口")


def _wait_for_proxy(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise WechatIndexProxyError("微信指数采集代理启动失败")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex((PROXY_HOST, port)) == 0:
                return
        time.sleep(0.2)
    raise WechatIndexProxyError("微信指数采集代理启动超时")


def _ca_fingerprint(certificate_path: Path) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
    return certificate.fingerprint(hashes.SHA1()).hex().upper()


def _install_current_user_ca(certificate_path: Path) -> str:
    result = subprocess.run(["certutil", "-user", "-addstore", "Root", str(certificate_path)], capture_output=True, text=True, **no_window_kwargs())
    if result.returncode:
        raise WechatIndexProxyError("无法安装本机微信指数采集证书")
    return _ca_fingerprint(certificate_path)


def _remove_current_user_ca(fingerprint: str) -> None:
    if not re.fullmatch(r"[A-F0-9]{40}", fingerprint):
        return
    subprocess.run(["certutil", "-user", "-delstore", "Root", fingerprint], capture_output=True, text=True, **no_window_kwargs())


def _addon_path() -> Path:
    return application_resource_path("server", "wechat_index_proxy_addon.py")


def _capture_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-wechat-index-capture"]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "run_v2_desktop.py"), "--run-wechat-index-capture"]


def start_capture(data_root: Path) -> dict[str, object]:
    state = _read_state(data_root)
    if state.get("status") == "running":
        raise WechatIndexProxyError("微信指数本机采集已在运行")
    root = _root(data_root); confdir = root / "mitmproxy"; root.mkdir(parents=True, exist_ok=True)
    port = _free_port(); previous_proxy = _registry_snapshot()
    environment = {**os.environ, "WECHAT_INDEX_DATA_ROOT": str(data_root.resolve())}
    command = [
        *_capture_command(),
        "--quiet", "--listen-host", PROXY_HOST, "--listen-port", str(port),
        "--set", f"confdir={confdir}", "--set", "block_global=true", "--set", "termlog_verbosity=error",
        "--ignore-hosts", r"^(?!search\.weixin\.qq\.com(?::\d+)?$).*", "-s", str(_addon_path()),
    ]
    upstream = _previous_proxy_server(previous_proxy)
    if upstream:
        command.extend(["--mode", f"upstream:http://{upstream}"])
    process = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window_kwargs())
    try:
        _wait_for_proxy(port, process)
        certificate = confdir / "mitmproxy-ca-cert.cer"
        deadline = time.monotonic() + 8
        while not certificate.is_file() and time.monotonic() < deadline: time.sleep(0.2)
        if not certificate.is_file():
            raise WechatIndexProxyError("采集证书生成超时")
        fingerprint = _install_current_user_ca(certificate)
        _apply_proxy(port, previous_proxy)
    except Exception:
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill()
        raise
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    state = {"status": "running", "pid": process.pid, "port": port, "previous_proxy": previous_proxy, "certificate_fingerprint": fingerprint, "started_at": started_at}
    _write_state(data_root, state)
    return {"status": "running", "port": port, "started_at": started_at, "message": "已开始本机连接初始化；请在微信指数手动查询一个关键词，完成后立即停止。"}


def stop_capture(data_root: Path) -> dict[str, object]:
    state = _read_state(data_root)
    if state.get("status") != "running":
        return {"status": "stopped", "restored_proxy": False, "removed_certificate": False}
    pid, port = int(state.get("pid") or 0), int(state.get("port") or 0)
    if pid > 0:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, **no_window_kwargs())
    restored = _restore_proxy(state.get("previous_proxy"), port)
    fingerprint = str(state.get("certificate_fingerprint") or "")
    _remove_current_user_ca(fingerprint)
    _write_state(data_root, {"status": "stopped", "stopped_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"status": "stopped", "restored_proxy": restored, "removed_certificate": bool(fingerprint)}


def capture_status(data_root: Path) -> dict[str, object]:
    state = _read_state(data_root)
    if state.get("status") != "running":
        return {"status": "stopped"}
    return {"status": "running", "port": state.get("port"), "started_at": state.get("started_at")}
