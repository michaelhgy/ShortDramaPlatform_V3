# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir definition for the V2 Windows Portable build."""

from __future__ import annotations

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


PROJECT_ROOT = Path(SPECPATH).parent
FFMPEG_ROOT = Path(os.environ["V2_FFMPEG_EXPANDED_ROOT"])
APPLICATION_ICON = PROJECT_ROOT / "packaging" / "assets" / "v2-application-icon.ico"

datas = [
    (str(PROJECT_ROOT / "dist"), "dist"),
    (str(FFMPEG_ROOT / "bin" / "ffmpeg.exe"), "tools/ffmpeg/bin"),
    (str(FFMPEG_ROOT / "bin" / "ffprobe.exe"), "tools/ffmpeg/bin"),
    (str(FFMPEG_ROOT / "LICENSE"), "tools/ffmpeg"),
    (str(FFMPEG_ROOT / "README.txt"), "tools/ffmpeg"),
]
binaries = []

# These packages use dynamic backends, data files or native binaries.  This is
# intentionally limited to V2's declared runtime dependencies, not all of site-packages.
hiddenimports = [
    "webview.platforms.edgechromium", "webview.platforms.winforms", "clr",
    "pythonnet", "clr_loader", "rapidocr_onnxruntime", "onnxruntime.capi._pybind_state",
]
# NumPy, OpenCV, Pillow, ONNX Runtime and pywebview each publish a PyInstaller
# hook.  Do not recursively collect them: that would pull their test/tooling
# trees into the Portable package.  Only V2's dynamic automation packages need
# a complete module collection.
for package in ("uiautomation", "pyJianYingDraft", "rapidocr_onnxruntime"):
    hiddenimports += collect_submodules(package)
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)

# These V2 modules are reached from task-boundary imports instead of the
# desktop launcher's import graph.
for package in ("server.template_engine", "server.final_engine", "server.v2_exporter", "server.windows_automation"):
    hiddenimports += collect_submodules(package)

a = Analysis(
    [str(PROJECT_ROOT / "tools" / "run_v2_desktop.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="ShortDramaPlatform",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    icon=str(APPLICATION_ICON),
    # Release builds are windowed; diagnostics may opt in without changing
    # the packaged application code or its default output.
    console=bool(os.environ.get("V2_PORTABLE_CONSOLE")),
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ShortDramaPlatform",
)
