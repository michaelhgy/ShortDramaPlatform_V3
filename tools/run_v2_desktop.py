"""Launch the V2 production desktop runtime from built frontend assets."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from server import v2_file_service as service  # noqa: E402


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


def start_production_server() -> tuple[object, str]:
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
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    args = parser.parse_args()
    if args.width < MIN_WIDTH or args.height < MIN_HEIGHT:
        raise SystemExit(f"窗口尺寸不得小于 {MIN_WIDTH}x{MIN_HEIGHT}。")

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
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"V2 正式启动失败：{exc}") from exc
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
