#!/usr/bin/env python3
"""Check or install the local OCR runtime required by drama-title detection."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys


PACKAGE = "rapidocr-onnxruntime==1.4.4"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local OCR runtime for short-drama title detection")
    parser.add_argument("--install", action="store_true", help="Install the pinned local OCR package when absent")
    args = parser.parse_args()
    installed = importlib.util.find_spec("rapidocr_onnxruntime") is not None
    result = {"package": PACKAGE, "installed": installed, "action": "STATUS"}
    if not installed and args.install:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", PACKAGE], check=True)
        installed = importlib.util.find_spec("rapidocr_onnxruntime") is not None
        result.update({"installed": installed, "action": "PACKAGE_INSTALLED"})
    elif not installed:
        result["action"] = "PACKAGE_INSTALL_REQUIRED"
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if installed else 2


if __name__ == "__main__":
    raise SystemExit(main())
