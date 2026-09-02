"""Build the V2 Windows onedir Portable package from verified local inputs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "packaging" / "ffmpeg-runtime.json"
DEFAULT_CACHE = Path("D:/V2_PackagingCache/ffmpeg/8.1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verified_ffmpeg_root(*, cache_root: Path | None = None) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    cache = cache_root or Path(os.environ.get("V2_FFMPEG_CACHE_ROOT", DEFAULT_CACHE))
    archive = cache / str(manifest["archive"]["filename"])
    expanded = cache / "expanded" / str(manifest["archive"]["archive_root"])
    if not archive.is_file() or sha256(archive) != str(manifest["archive"]["sha256"]).upper():
        raise RuntimeError("受控 FFmpeg archive 缺失或 SHA-256 与 manifest 不符；不会下载替代文件")
    for relative, expected in dict(manifest["expected_sha256"]).items():
        target = expanded / relative
        if not target.is_file() or sha256(target) != str(expected).upper():
            raise RuntimeError(f"受控 FFmpeg 文件缺失或 SHA-256 不符：{relative}")
    for notice in manifest["bundle"]["required_notices"]:
        if not (expanded / str(notice)).is_file():
            raise RuntimeError(f"受控 FFmpeg notice 缺失：{notice}")
    return expanded


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()


def main() -> None:
    if sys.version_info[:3] != (3, 12, 10):
        raise SystemExit(f"Portable 构建要求 CPython 3.12.10；当前为 {sys.version.split()[0]}")
    if not (PROJECT_ROOT / "dist" / "index.html").is_file():
        raise SystemExit("缺少 dist/index.html；请先执行 npm run build")
    ffmpeg_root = verified_ffmpeg_root()
    output = PROJECT_ROOT / "packaging" / "output"
    work = PROJECT_ROOT / "packaging" / "work"
    environment = dict(os.environ, V2_FFMPEG_EXPANDED_ROOT=str(ffmpeg_root))
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(output), "--workpath", str(work),
        str(PROJECT_ROOT / "packaging" / "v2_portable.spec"),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True)
    package_root = output / "ShortDramaPlatform"
    metadata = {
        "product": "ShortDramaPlatform V2",
        "version": "V2",
        "git_commit": _git_commit(),
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "build_mode": "PyInstaller onedir",
    }
    (package_root / "build-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Portable build succeeded: {package_root}")


if __name__ == "__main__":
    main()
