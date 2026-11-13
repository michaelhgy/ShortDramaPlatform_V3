"""Start the V2 development dependencies and open its pywebview test window.

This launcher is intentionally V2-only. It may start V2's local frontend and
data service, but never starts or changes V1 services, data, or behavior.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import ProxyHandler, build_opener


DEFAULT_URL = "http://127.0.0.1:3000/"
DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 920
MIN_WIDTH = 1100
MIN_HEIGHT = 720
PROJECT_ROOT = Path(__file__).resolve().parents[1]
V2_API_URL = "http://127.0.0.1:8782/api/v2/health"


def is_reachable(url: str) -> bool:
    try:
        # The desktop test page and its V2 data service are both local. Do not
        # send those requests through a machine-wide HTTP proxy.
        with build_opener(ProxyHandler({})).open(url, timeout=5) as response:
            if not 200 <= response.status < 400:
                return False
        return True
    except (OSError, URLError):
        return False


def wait_until_reachable(url: str, label: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if is_reachable(url):
            return
        time.sleep(0.5)
    raise SystemExit(f"自动启动后仍无法连接{label}：{url}")


def _stop_process_tree(process: subprocess.Popen[object]) -> None:
    """Stop one child process and its Windows descendants."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _stop_started_dependencies(processes: list[subprocess.Popen[object]]) -> None:
    """Stop only the V2 processes started by this desktop invocation."""
    for process in reversed(processes):
        _stop_process_tree(process)


def start_v2_dependencies(v2_url: str) -> list[subprocess.Popen[object]]:
    """Start missing local V2 development processes and return owned children."""
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    started: list[subprocess.Popen[object]] = []
    try:
        if not is_reachable(V2_API_URL):
            service = subprocess.Popen(
                [sys.executable, str(PROJECT_ROOT / "tools" / "run_v2_file_service.py")],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            started.append(service)
            wait_until_reachable(V2_API_URL, "V2 本地数据服务")

        if not is_reachable(v2_url):
            npm_command = shutil.which("npm.cmd") or shutil.which("npm")
            if not npm_command:
                raise SystemExit("找不到 npm，无法启动 V2 前端开发服务。")
            frontend = subprocess.Popen(
                [npm_command, "run", "dev"],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            started.append(frontend)
            wait_until_reachable(v2_url, "V2 前端开发服务")
    except BaseException:
        _stop_started_dependencies(started)
        raise
    return started


def main() -> None:
    parser = argparse.ArgumentParser(description="在 pywebview 中打开 V2 开发页面")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"V2 开发服务器地址，默认 {DEFAULT_URL}")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--debug", action="store_true", help="启用 pywebview 调试模式")
    parser.add_argument("--no-autostart", action="store_true", help="不自动启动缺失的 V2 后台服务")
    args = parser.parse_args()

    if args.width < MIN_WIDTH or args.height < MIN_HEIGHT:
        raise SystemExit(f"窗口尺寸不得小于 {MIN_WIDTH}x{MIN_HEIGHT}。")

    v2_url = args.url.rstrip("/") + "/"
    started: list[subprocess.Popen[object]] = []
    try:
        if not args.no_autostart and v2_url == DEFAULT_URL:
            started = start_v2_dependencies(v2_url)
        wait_until_reachable(v2_url, "V2 前端开发服务")
        wait_until_reachable(urljoin(v2_url, "/api/v2/health"), "V2 本地数据服务")

        try:
            import webview
        except ImportError as error:
            raise SystemExit("当前 Python 环境未安装 pywebview，无法启动桌面测试窗口。") from error

        window = webview.create_window(
            "短剧推广运营系统 V2 - 桌面测试",
            v2_url,
            width=args.width,
            height=args.height,
            maximized=True,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
        )
        print(f"V2 桌面测试窗口已打开：{v2_url}", flush=True)
        webview.start(gui="edgechromium", debug=args.debug)
        del window
    finally:
        _stop_started_dependencies(started)


if __name__ == "__main__":
    main()
