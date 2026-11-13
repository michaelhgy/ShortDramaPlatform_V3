"""Reproducible V3-only onedir release, including the verified media libraries."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from build_portable import verified_ffmpeg_root
from v3_resources import collect
from versioning import release_identity, write_installer_identity

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    identity = release_identity()
    parser.add_argument("--version", default=identity["release_id"])
    parser.add_argument("--incremental",action="store_true",help="Reuse PyInstaller analysis cache; use clean build when dependencies change")
    parser.add_argument("--release-root",type=Path,help="Canonical output root; avoids copying a complete snapshot build again")
    args = parser.parse_args()
    try:
        components = list(map(int, args.version.split(".")))
        if len(components) not in (3, 4) or any(not 0 <= n <= 65535 for n in components):
            raise ValueError
    except ValueError:
        parser.error("--version must contain three or four integers in 0..65535")
    version = tuple(components + [0] * (4 - len(components)))
    identity["release_id"] = args.version
    product_version = tuple(map(int, identity["product_version"].split("."))) + (0,)
    write_installer_identity(identity)
    if sys.version_info[:3] != (3, 12, 10):
        raise RuntimeError("Use the verified CPython 3.12.10 Windows runtime")
    if not (ROOT / "dist/index.html").is_file():
        raise RuntimeError("Build the production frontend before packaging")
    release_root = args.release_root.resolve() if args.release_root else ROOT / "packaging/releases"
    out = release_root / args.version
    out.mkdir(parents=True, exist_ok=False)
    work = release_root.parent / "work/v3-program" if args.incremental else out / "build"
    work.mkdir(parents=True, exist_ok=args.incremental)
    manifest = collect(ROOT)
    manifest_path = work / "v3-resource-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    version_file = work / "version-info.txt"
    version_file.write_text(f"""VSVersionInfo(
      ffi=FixedFileInfo(filevers={version!r}, prodvers={product_version!r}, mask=0x3f, flags=0x0,
      OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
      kids=[StringFileInfo([StringTable('080404B0',[
      StringStruct('FileDescription','短剧推广运营系统 V3'),
      StringStruct('FileVersion','{args.version}'),
      StringStruct('ProductName','短剧推广运营系统 V3'),
      StringStruct('ProductVersion','{identity['product_version']}'),
      StringStruct('OriginalFilename','ShortDramaPlatformV3.exe')])]),
      VarFileInfo([VarStruct('Translation',[2052,1200])])])""", encoding="utf-8")
    environment = dict(os.environ, V3_FFMPEG_EXPANDED_ROOT=str(verified_ffmpeg_root()),
                       V3_RESOURCE_MANIFEST=str(manifest_path), V3_VERSION_FILE=str(version_file),
                       PYTHONPATH=str(ROOT))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", *([] if args.incremental else ["--clean"]),
                    "--distpath", str(out), "--workpath", str(work),
                    str(ROOT / "packaging/v3_portable.spec")],
                   cwd=ROOT, env=environment, check=True)
    package = out / "ShortDramaPlatformV3"
    from render_manual import publish
    publish(ROOT, package)
    source_hashes = {}
    for base in ("server", "src", "tools/ffmpeg_overlay_lab", "packaging"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix not in {".py", ".ts", ".tsx", ".spec", ".iss"} or any(
                    x in p.parts for x in ("__pycache__", "releases", "updates", "work", "output", "experiments")):
                continue
            source_hashes[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ('tools/release_v3_probe.py','tools/release_v3_scenery_probe.py','tools/run_v2_desktop.py'):
        source_hashes[name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    from release_v3 import inputs
    metadata = {"release_input_hashes": inputs(ROOT), "product": "ShortDramaPlatform V3", "version": args.version, "release_id": args.version, "product_version": identity["product_version"], "channel": identity["channel"],
                "built_at_utc": datetime.now(timezone.utc).isoformat(),
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "working_tree_changes_included": True, "python": sys.version,
                "pyinstaller": importlib.metadata.version("pyinstaller"),
                "runtime_library": {"counts": manifest["counts"], "files": len(manifest["files"]),
                                    "bytes": manifest["total_bytes"]},
                "source_hashes": source_hashes}
    (package / "build-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "packaging/ffmpeg-runtime.json", package / "ffmpeg-runtime.json")
    print(json.dumps({"package": str(package), "library_counts": manifest["counts"],
                      "library_bytes": manifest["total_bytes"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
