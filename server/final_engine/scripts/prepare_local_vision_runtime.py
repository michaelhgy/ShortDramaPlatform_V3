#!/usr/bin/env python3
"""Check or install the local Ollama vision runtime required by cover detection."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


DEFAULT_MODEL = "qwen2.5vl:7b"


def find_ollama() -> str | None:
    located = shutil.which("ollama")
    if located:
        return located
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def installed_models() -> list[str]:
    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [str(item.get("name", "")) for item in payload.get("models", [])]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local vision runtime for short-drama cover detection")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--install", action="store_true", help="Pull the model when it is absent (one-time ~6GB download)")
    args = parser.parse_args()
    ollama = find_ollama()
    result = {"model": args.model, "ollama_path": ollama, "installed": False, "action": "STATUS"}
    if not ollama:
        result["action"] = "OLLAMA_INSTALL_REQUIRED"
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2
    try:
        models = installed_models()
    except Exception as exc:
        result["action"] = "OLLAMA_SERVICE_REQUIRED"
        result["error"] = str(exc)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2
    if args.model not in models:
        if not args.install:
            result["action"] = "MODEL_PULL_REQUIRED"
            result["available_models"] = models
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 2
        subprocess.run([ollama, "pull", args.model], check=True)
        models = installed_models()
        result["action"] = "MODEL_PULLED"
    result["installed"] = args.model in models
    if not result["installed"]:
        result["action"] = "MODEL_VERIFY_FAILED"
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
