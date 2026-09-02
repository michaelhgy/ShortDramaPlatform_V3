import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from server.runtime_process import no_window_kwargs, worker_command


class RuntimeProcessTests(unittest.TestCase):
    def test_source_worker_uses_script_path(self):
        command = worker_command("server.example.worker", Path("worker.py"), ["--help"])
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], "worker.py")

    def test_frozen_worker_uses_exe_dispatch_marker(self):
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", "V2.exe"):
            command = worker_command("server.example.worker", Path("missing.py"), ["--help"])
        self.assertEqual(command, ["V2.exe", "--v2-worker", "server.example.worker", "--help"])
        self.assertNotIn("missing.py", command)

    def test_windows_no_window_flag(self):
        with patch("server.runtime_process.os.name", "nt"), patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            self.assertEqual(no_window_kwargs()["creationflags"], 0x08000000)

