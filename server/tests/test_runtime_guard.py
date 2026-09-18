"""单实例守卫 + 写锁监视器的测试（隔离环境，不碰真实业务数据）。"""

from __future__ import annotations

import sqlite3
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from server.runtime_guard import (
    append_bounded,
    assert_port_available,
    port_is_in_use,
    start_write_lock_watchdog,
    write_lock_is_busy,
    write_lock_report,
)


def _listening_socket() -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    return listener, int(listener.getsockname()[1])


class PortGuardTests(unittest.TestCase):
    def test_detects_a_listening_port(self):
        listener, port = _listening_socket()
        try:
            self.assertTrue(port_is_in_use("127.0.0.1", port))
        finally:
            listener.close()

    def test_free_port_is_available(self):
        listener, port = _listening_socket()
        listener.close()  # 端口已释放
        self.assertFalse(port_is_in_use("127.0.0.1", port))
        self.assertIsNone(assert_port_available("127.0.0.1", port))

    def test_refuses_to_start_when_port_is_taken(self):
        listener, port = _listening_socket()
        try:
            with self.assertRaises(RuntimeError) as caught:
                assert_port_available("127.0.0.1", port)
        finally:
            listener.close()
        message = str(caught.exception)
        self.assertIn(str(port), message)
        self.assertIn("只允许开一个", message)


class WriteLockWatchdogTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.db = Path(self._temp.name) / "probe.db"
        self.connection = sqlite3.connect(self.db, isolation_level=None, timeout=5)
        self.connection.execute("CREATE TABLE IF NOT EXISTS demo(id INTEGER PRIMARY KEY)")
        self.connection.execute("INSERT INTO demo(id) VALUES (1)")

    def tearDown(self):
        try:
            self.connection.close()
        finally:
            self._temp.cleanup()

    def test_busy_while_a_writer_holds_the_lock(self):
        self.connection.execute("BEGIN IMMEDIATE")
        self.connection.execute("INSERT INTO demo(id) VALUES (2)")
        try:
            self.assertTrue(write_lock_is_busy(self.db, timeout=0.1))
        finally:
            self.connection.execute("ROLLBACK")
        self.assertFalse(write_lock_is_busy(self.db, timeout=0.1))

    def test_report_names_the_threads_and_the_last_change(self):
        self.connection.execute("CREATE TABLE IF NOT EXISTS v2_change_events(id INTEGER PRIMARY KEY, change_type TEXT, updated_at TEXT)")
        self.connection.execute("INSERT INTO v2_change_events(change_type, updated_at) VALUES ('material_changed','2026-09-18T12:00:00')")
        report = write_lock_report(self.db, strikes=3, interval=2.0)
        self.assertIn("写锁连续被占 3 次", report)
        self.assertIn("material_changed", report)
        self.assertIn("线程", report)

    def test_watchdog_writes_a_report_only_after_consecutive_strikes(self):
        log = Path(self._temp.name) / "watchdog.log"
        stop = threading.Event()
        # 门槛 2 次 × 50ms、每次探测最多等 20ms：写锁一直被占 → 应该写报告
        self.connection.execute("BEGIN IMMEDIATE")
        self.connection.execute("INSERT INTO demo(id) VALUES (3)")
        try:
            start_write_lock_watchdog(
                self.db, log_path=log, interval=0.05, strikes_needed=2,
                probe_timeout=0.02, stop_event=stop,
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not log.is_file():
                time.sleep(0.02)
        finally:
            self.connection.execute("ROLLBACK")
            stop.set()
        self.assertTrue(log.is_file(), "写锁被占住时应当写出报告")
        self.assertIn("写锁连续被占", log.read_text(encoding="utf-8"))

    def test_watchdog_does_not_report_a_single_transient_strike(self):
        """一次瞬时抢不到锁（别的写入正在提交）不应该留下任何日志。"""
        log = Path(self._temp.name) / "transient.log"
        stop = threading.Event()
        start_write_lock_watchdog(
            self.db, log_path=log, interval=0.05, strikes_needed=3,
            probe_timeout=0.02, stop_event=stop,
        )
        self.connection.execute("BEGIN IMMEDIATE")
        time.sleep(0.06)  # 只占一小会儿，达不到连续 3 次
        self.connection.execute("ROLLBACK")
        time.sleep(0.4)
        stop.set()
        self.assertFalse(log.is_file(), "瞬时占锁不应触发报告")

    def test_watchdog_stays_silent_while_the_lock_is_free(self):
        log = Path(self._temp.name) / "silent.log"
        stop = threading.Event()
        start_write_lock_watchdog(self.db, log_path=log, interval=0.05, strikes_needed=2, probe_timeout=0.02, stop_event=stop)
        time.sleep(0.5)
        stop.set()
        self.assertFalse(log.is_file(), "写锁空闲时监视器不应产生任何输出")

    def test_watchdog_can_be_switched_off(self):
        import os

        previous = os.environ.get("V2_WRITE_LOCK_WATCHDOG")
        os.environ["V2_WRITE_LOCK_WATCHDOG"] = "0"
        try:
            self.assertIsNone(start_write_lock_watchdog(self.db, log_path=Path(self._temp.name) / "off.log"))
        finally:
            if previous is None:
                os.environ.pop("V2_WRITE_LOCK_WATCHDOG", None)
            else:
                os.environ["V2_WRITE_LOCK_WATCHDOG"] = previous

    def test_bounded_log_keeps_the_tail(self):
        log = Path(self._temp.name) / "big.log"
        log.write_text("a" * 300, encoding="utf-8")
        append_bounded(log, "TAIL", limit=200, keep=100)
        content = log.read_text(encoding="utf-8")
        self.assertLessEqual(len(content), 200)
        self.assertTrue(content.endswith("TAIL\n"))


if __name__ == "__main__":
    unittest.main()
