"""Launch the V2 production desktop runtime from built frontend assets."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import runpy
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


if getattr(sys, "frozen", False):
    # PyInstaller has already loaded application modules.  Its resource root
    # is used by the service; do not derive a source-checkout path here.
    PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 920
MIN_WIDTH = 1100
MIN_HEIGHT = 720


def wait_until_reachable(url: str, label: str) -> None:
    deadline = time.monotonic() + 20
    opener = build_opener(ProxyHandler({}))
    while time.monotonic() < deadline:
        try:
            with opener.open(url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"启动后无法连接{label}：{url}")


def startup_diagnostic_log_path() -> Path:
    """Keep desktop-start failures outside the install folder for remote support."""
    local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    base = Path(local_app_data).expanduser() if local_app_data else Path.home()
    return base / "ShortDramaPlatformV2" / "logs" / "desktop-startup.log"


def report_startup_failure(exc: BaseException) -> None:
    """Show and persist the real cause when a windowed Portable exits early."""
    log_path = startup_diagnostic_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "\n\n".join((
                f"[{datetime.now().isoformat(timespec='seconds')}] V2 desktop startup failed",
                f"executable={sys.executable}",
                f"frozen={bool(getattr(sys, 'frozen', False))}",
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            )),
            encoding="utf-8",
        )
    except OSError:
        # A visible dialog remains useful even if a restrictive machine policy
        # prevents writing the optional local diagnostic log.
        log_path = None
    message = "短剧推广运营系统 V2 启动失败。\n\n"
    message += f"原因：{exc}\n"
    if log_path is not None:
        message += f"\n完整错误日志：\n{log_path}"
    try:
        ctypes.windll.user32.MessageBoxW(None, message, "V2 启动失败", 0x10)
    except Exception:
        # Source/console launchers still receive the traceback from the caller.
        print(message, file=sys.stderr, flush=True)


def start_production_server() -> tuple[object, str]:
    # Keep this import inside the protected desktop boundary. A missing native
    # dependency on another PC must show a useful error instead of silently
    # exiting before main() begins.
    from server import v2_file_service as service
    service.frontend_dist_root()
    server = service.create_v2_server()
    try:
        address = f"http://{service.HOST}:{server.server_address[1]}/"
        threading.Thread(target=server.serve_forever, name="v2-production-server", daemon=True).start()
        wait_until_reachable(f"{address}api/v2/health", "V2 本地服务")
        wait_until_reachable(address, "V2 正式前端")
        return server, address
    except Exception:
        server.shutdown()
        server.server_close()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 V2 正式桌面运行环境（不使用 Vite）")
    parser.add_argument("--debug", action="store_true", help="启用 pywebview 调试模式")
    parser.add_argument("--runtime-probe", action="store_true", help="仅检查冻结运行时依赖，不启动窗口")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    args = parser.parse_args()
    if args.runtime_probe:
        from server.final_engine.jianying59_final.visual_layers import GLOBAL_EFFECT_POOL, REAL_PHOTO_EFFECT_POOL
        from server.tool_resolver import resolve_ffmpeg, resolve_ffprobe
        from server.windows_automation.jianying59_exporter.upstream_adapter import PyJianyingUpstreamAdapter  # noqa: F401
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import pyJianYingDraft  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
        import tkinter  # noqa: F401
        import uiautomation  # noqa: F401
        import webview  # noqa: F401
        import win32api  # noqa: F401
        resources = (GLOBAL_EFFECT_POOL, REAL_PHOTO_EFFECT_POOL)
        for resource in resources:
            json.loads(resource.read_text(encoding="utf-8"))
        print(json.dumps({
            "status": "ok",
            "ffmpeg": str(resolve_ffmpeg()),
            "ffprobe": str(resolve_ffprobe()),
            "runtime_resources": [str(resource) for resource in resources],
        }, ensure_ascii=False), flush=True)
        return
    if args.width < MIN_WIDTH or args.height < MIN_HEIGHT:
        raise RuntimeError(f"窗口尺寸不得小于 {MIN_WIDTH}x{MIN_HEIGHT}。")

    server = None
    try:
        server, address = start_production_server()
        try:
            import webview
        except ImportError as exc:
            raise RuntimeError("当前 Python 环境未安装 pywebview，无法启动 V2 桌面窗口") from exc
        webview.create_window(
            "短剧推广运营系统 V2",
            address,
            width=args.width,
            height=args.height,
            maximized=True,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
        )
        print(f"V2 正式桌面窗口已打开：{address}", flush=True)
        webview.start(gui="edgechromium", debug=args.debug)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


def _run_worker_if_requested() -> bool:
    if "--v2-worker" not in sys.argv:
        return False
    index = sys.argv.index("--v2-worker")
    if index + 1 >= len(sys.argv):
        raise SystemExit("缺少 V2 worker 模块名")
    module = sys.argv[index + 1]
    sys.argv[:] = [module, *sys.argv[index + 2:]]
    runpy.run_module(module, run_name="__main__")
    return True


if __name__ == "__main__":
    if not _run_worker_if_requested():
        try:
            main()
        except Exception as exc:  # noqa: BLE001
            report_startup_failure(exc)
            raise SystemExit(1) from exc
