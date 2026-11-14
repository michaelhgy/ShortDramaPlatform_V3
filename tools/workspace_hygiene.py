"""Fast, read-only hygiene checks for the V3 development workspace.

The default path deliberately avoids recursive scans of media, installers,
Git objects, dependency caches, and the reusable overlay library.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ROOT_DIRS = {
    ".git",
    ".pytest_cache",
    "artifacts",
    "dist",
    "docs",
    "local-test-output",
    "node_modules",
    "packaging",
    "public",
    "server",
    "src",
    "tools",
    "诊断输出",
}

HEAVY_DIRS = {
    ".git",
    "node_modules",
    "local-test-output",
    "artifacts",
    "dist",
    "诊断输出",
    "packaging/releases",
    "packaging/build-tools",
    "packaging/updates",
    "tools/ffmpeg_overlay_lab",
}

ROOT_FILES = {
    ".env.example",
    ".gitignore",
    "@AutomationLog.txt",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "bun.lock",
    "index.html",
    "metadata.json",
    "package-lock.json",
    "package.json",
    "requirements-build.txt",
    "requirements-dev.txt",
    "requirements-runtime.txt",
    "tsconfig.json",
    "tsconfig.release.json",
    "vite.config.ts",
    "启动V3开发版.bat",
    "项目控制台.md",
}


def relative_children(path: Path) -> Iterable[str]:
    for child in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
        yield child.name


def root_report() -> dict:
    unexpected_dirs: list[str] = []
    unexpected_files: list[str] = []
    directories: list[str] = []
    files: list[str] = []

    for name in relative_children(ROOT):
        path = ROOT / name
        if path.is_dir():
            directories.append(name)
            if name not in ALLOWED_ROOT_DIRS:
                unexpected_dirs.append(name)
        else:
            files.append(name)
            if name not in ROOT_FILES:
                unexpected_files.append(name)

    heavy_present = [name for name in sorted(HEAVY_DIRS) if (ROOT / name).exists()]
    return {
        "root": str(ROOT),
        "directories": directories,
        "files": files,
        "unexpected_directories": unexpected_dirs,
        "unexpected_files": unexpected_files,
        "heavy_paths_skipped": heavy_present,
        "recursive_scan": False,
    }


def print_report(report: dict) -> None:
    print(f"workspace: {report['root']}")
    print("recursive_scan: false")
    print(f"root directories: {len(report['directories'])}")
    print(f"root files: {len(report['files'])}")
    print("heavy paths skipped:")
    for path in report["heavy_paths_skipped"]:
        print(f"  - {path}")
    if report["unexpected_directories"]:
        print("unexpected root directories:")
        for path in report["unexpected_directories"]:
            print(f"  - {path}")
    else:
        print("unexpected root directories: none")
    if report["unexpected_files"]:
        print("unexpected root files:")
        for path in report["unexpected_files"]:
            print(f"  - {path}")
    else:
        print("unexpected root files: none")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail on unexpected root entries")
    parser.add_argument("--json", type=Path, help="write the small root report to this path")
    args = parser.parse_args()

    report = root_report()
    print_report(report)
    if args.json:
        output = args.json if args.json.is_absolute() else ROOT / args.json
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report: {output}")

    if args.check and (report["unexpected_directories"] or report["unexpected_files"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
