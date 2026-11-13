import importlib.util
import subprocess
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


LAUNCHER_PATH = Path(__file__).resolve().parents[2] / "tools" / "run_v2_desktop_test.py"
SPEC = importlib.util.spec_from_file_location("v2_desktop_test_launcher_for_test", LAUNCHER_PATH)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class V2DesktopTestLauncherTests(TestCase):
    def test_start_only_returns_processes_started_by_this_invocation(self) -> None:
        service = Mock(spec=subprocess.Popen)
        frontend = Mock(spec=subprocess.Popen)
        service.poll.return_value = None
        frontend.poll.return_value = None
        service.pid = 101
        frontend.pid = 102

        with patch.object(launcher, "is_reachable", side_effect=[False, False]), \
             patch.object(launcher, "wait_until_reachable"), \
             patch.object(launcher.shutil, "which", return_value="npm.cmd"), \
             patch.object(launcher.subprocess, "Popen", side_effect=[service, frontend]):
            started = launcher.start_v2_dependencies("http://127.0.0.1:3000/")

        self.assertEqual([service, frontend], started)

    def test_close_stops_only_owned_process_trees(self) -> None:
        service = Mock(spec=subprocess.Popen)
        frontend = Mock(spec=subprocess.Popen)
        service.poll.return_value = None
        frontend.poll.return_value = None
        service.pid = 101
        frontend.pid = 102

        with patch.object(launcher.os, "name", "nt"), \
             patch.object(launcher.subprocess, "run") as run:
            launcher._stop_started_dependencies([service, frontend])

        self.assertEqual(
            ["taskkill", "/PID", "102", "/T", "/F"],
            run.call_args_list[0].args[0],
        )
        self.assertEqual(
            ["taskkill", "/PID", "101", "/T", "/F"],
            run.call_args_list[1].args[0],
        )
        frontend.wait.assert_called_once_with(timeout=5)
        service.wait.assert_called_once_with(timeout=5)
