# -*- coding: utf-8 -*-
"""ASCII launcher for the Chinese-named downloader module."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("批量解析下载.py")), run_name="__main__")
