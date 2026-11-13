"""运行期护栏：单实例守卫 + 写锁监视器。

两件护栏都来自 2026-09-17 / 09-18 的故障复盘（见 `docs/决策日志.md`）：

1. **单实例守卫**——打包版与源码版**共用同一个数据库**。Windows 上第二个实例抢同一个
   端口**不会报错**（Python 的 `HTTPServer` 默认 `allow_reuse_address = 1`，已实测：
   第二个进程 `bind + listen` 同一个端口成功），结果是两个后端同时写同一个 SQLite。
   → `assert_port_available()` 在启动前用**连接探测**判断端口是否已被占用，占用就明确拒绝。
   **不能用 bind 探测**：Windows 上 bind 会假成功，这正是问题本身。

2. **写锁监视器**——曾经出现"一个写事务开了头、不推进、也不提交"，把数据库写操作卡住
   （WAL 已让读取不受影响，但根因未定位）。
   → 监视器平时**零输出**；只有当写锁**连续**被占超过阈值时，才把当时所有线程的调用栈
   和"最近一次数据库变更的类型"写进日志，下次再现时直接点名是哪段代码，不靠猜。
"""

from __future__ import annotations

import os
import socket
import sqlite3
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

# 端口被占用时给用户看的原话：不要出现"端口""进程"以外的术语，要说清怎么办。
PORT_BUSY_MESSAGE = (
    "已经有一个「短剧推广运营系统 V2」在运行（本机 127.0.0.1:{port} 已被占用）。\n"
    "请先关掉那个软件窗口，再启动这一个。\n"
    "两个软件同时打开会同时读写同一份数据，可能导致界面卡住或数据出错，所以只允许开一个。"
)

WATCHDOG_ENV = "V2_WRITE_LOCK_WATCHDOG"
WATCHDOG_INTERVAL_ENV = "V2_WRITE_LOCK_WATCHDOG_INTERVAL"
WATCHDOG_STRIKES_ENV = "V2_WRITE_LOCK_WATCHDOG_STRIKES"
DEFAULT_INTERVAL_SECONDS = 2.0
DEFAULT_STRIKES = 3
LOG_LIMIT_BYTES = 1_000_000
LOG_KEEP_BYTES = 250_000

# 变更日志里的类型 → 大白话（判断"最后在写库的是谁"用）
CHANGE_TYPE_LABELS = {
    "material_changed": "生产文件素材（扫描素材 / 素材改动）",
    "production_task_changed": "生产任务（含后台定时清理）",
    "template_changed": "模板草稿生成",
    "video_changed": "成片生成",
    "video_export_changed": "视频导出",
    "task_changed": "任务中心派发",
    "resource_changed": "生成资源扫描（风景视频 / 图片 / 引流视频）",
    "settings_changed": "设置",
    "revenue_changed": "收益采集",
    "account_changed": "账号资料",
    "drama_changed": "剧集资料",
    "theater_changed": "剧场资料",
    "sub_theater_changed": "子剧场资料",
}


def port_is_in_use(host: str, port: int, *, timeout: float = 0.3) -> bool:
    """判断端口是否已经有人在监听（连接探测，不用 bind 探测）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        try:
            probe.connect((host, port))
        except OSError:
            return False
    return True


def assert_port_available(host: str, port: int) -> None:
    """端口已被占用就抛错，阻止第二个实例静默启动。"""
    if port_is_in_use(host, port):
        raise RuntimeError(PORT_BUSY_MESSAGE.format(port=port))


def watchdog_enabled() -> bool:
    return str(os.environ.get(WATCHDOG_ENV, "")).strip() != "0"


def watchdog_interval() -> float:
    try:
        value = float(str(os.environ.get(WATCHDOG_INTERVAL_ENV, "")).strip() or DEFAULT_INTERVAL_SECONDS)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    return max(0.05, value)


def watchdog_strikes() -> int:
    try:
        value = int(str(os.environ.get(WATCHDOG_STRIKES_ENV, "")).strip() or DEFAULT_STRIKES)
    except ValueError:
        return DEFAULT_STRIKES
    return max(1, value)


def watchdog_log_path() -> Path:
    """诊断日志放在用户目录，不写进软件文件夹、不写进业务数据目录。"""
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    base = Path(local).expanduser() if local else Path.home()
    return base / "ShortDramaPlatformV2" / "logs" / "write-lock-watchdog.log"


def write_lock_is_busy(db: Path, *, timeout: float = 0.3) -> bool:
    """True = 此刻拿不到数据库写锁（有别的连接正开着写事务）。"""
    if not db.is_file():
        return False
    try:
        conn = sqlite3.connect(str(db), timeout=timeout, isolation_level=None)
    except sqlite3.Error:
        return False
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            return "lock" in str(exc).lower() or "busy" in str(exc).lower()
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        return False
    except sqlite3.Error:
        return False
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def thread_stack_dump() -> str:
    """把当前所有 Python 线程的调用栈抓下来——这就是"点名"的那一步。"""
    names = {thread.ident: thread.name for thread in threading.enumerate()}
    chunks: list[str] = []
    for ident, frame in sys._current_frames().items():
        name = names.get(ident, "未知线程")
        stack = "".join(traceback.format_stack(frame))
        chunks.append(f"--- 线程 {name} (id={ident}) ---\n{stack}")
    return "\n".join(chunks) if chunks else "（取不到线程栈）\n"


def _recent_change(db: Path) -> str:
    """最近一次写入数据库的变更类型：触发器写在写者事务里，所以它能指认"是谁在写"。"""
    if not db.is_file():
        return "（数据库文件不存在）"
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=0.3)
    except sqlite3.Error as exc:
        return f"（读不到变更日志：{exc}）"
    try:
        row = conn.execute(
            "SELECT change_type, updated_at, id FROM v2_change_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.Error as exc:
        return f"（读不到变更日志：{exc}）"
    finally:
        conn.close()
    if row is None:
        return "（变更日志是空的）"
    change_type = str(row[0])
    return f"{change_type}（{CHANGE_TYPE_LABELS.get(change_type, '未知类型')}） at {row[1]}（id={row[2]}）"


def _journal_state(db: Path) -> str:
    parts = []
    for suffix in ("-wal", "-journal"):
        path = Path(str(db) + suffix)
        if path.is_file():
            try:
                stat = path.stat()
                parts.append(f"{suffix}={stat.st_size} 字节，最后修改 {datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}")
            except OSError:
                parts.append(f"{suffix}=（读不到）")
    return "；".join(parts) if parts else "（没有 -wal / -journal 文件）"


def write_lock_report(db: Path, strikes: int, *, interval: float | None = None) -> str:
    """生成一份"写锁卡住现场"报告。"""
    seconds = (interval if interval is not None else watchdog_interval()) * strikes
    lines = [
        "",
        "=" * 78,
        f"[{datetime.now().isoformat(timespec='seconds')}] 写锁连续被占 {strikes} 次（约 {seconds:.1f} 秒没放开）",
        f"数据库：{db}",
        f"最近一次数据库变更：{_recent_change(db)}",
        f"日志文件：{_journal_state(db)}",
        "各线程在做什么（最后一行是最内层调用）：",
        thread_stack_dump(),
        "=" * 78,
    ]
    return "\n".join(lines)


def append_bounded(log_path: Path, text: str, *, limit: int = LOG_LIMIT_BYTES, keep: int = LOG_KEEP_BYTES) -> None:
    """追加日志；超过上限就只保留尾部，避免监视器自己变成新的日志炸弹。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if log_path.is_file() and log_path.stat().st_size > limit:
            tail = log_path.read_bytes()[-keep:]
            log_path.write_bytes(tail)
    except OSError:
        pass
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")


def start_write_lock_watchdog(
    db_path: Path,
    *,
    log_path: Path | None = None,
    interval: float | None = None,
    strikes_needed: int | None = None,
    probe_timeout: float = 0.3,
    stop_event: threading.Event | None = None,
) -> threading.Thread | None:
    """启动写锁监视器（守护线程）。关闭方式：环境变量 V2_WRITE_LOCK_WATCHDOG=0。

    数据库路径在启动时取一次：进程存活期间数据盘不会变；变了也需要重启（连接本来就按路径重建）。
    默认参数下：每 2 秒探一次、每次最多等 0.3 秒、连续 3 次拿不到才写报告
    → 也就是**写锁被连续占住约 7 秒以上**才会留痕；正常的毫秒级写入不会触发。
    """
    if not watchdog_enabled():
        return None
    db = Path(db_path)
    target = log_path or watchdog_log_path()
    gap = watchdog_interval() if interval is None else max(0.05, interval)
    threshold = watchdog_strikes() if strikes_needed is None else max(1, strikes_needed)
    wait_for_lock = max(0.01, probe_timeout)
    stop = stop_event or threading.Event()

    def _loop() -> None:
        strikes = 0
        reported = False
        while not stop.wait(gap):
            try:
                if write_lock_is_busy(db, timeout=wait_for_lock):
                    strikes += 1
                    if strikes >= threshold and not reported:
                        append_bounded(target, write_lock_report(db, strikes, interval=gap))
                        reported = True
                    continue
            except Exception:  # 诊断线程绝不能影响服务本身
                continue
            strikes = 0
            reported = False

    thread = threading.Thread(target=_loop, name="V2WriteLockWatchdog", daemon=True)
    thread.start()
    return thread
