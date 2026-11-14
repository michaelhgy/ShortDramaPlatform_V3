# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir definition for the V3 Windows Portable build."""

from __future__ import annotations

import os
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from server.worker_registry import PRODUCTION_WORKERS


PROJECT_ROOT = Path(SPECPATH).parent
FFMPEG_ROOT = Path(os.environ["V3_FFMPEG_EXPANDED_ROOT"])
APPLICATION_ICON = PROJECT_ROOT / "packaging" / "assets" / "v2-application-icon.ico"
MEDIAPIPE_ROOT = Path(importlib.util.find_spec("mediapipe").submodule_search_locations[0])

datas = [
    (str(PROJECT_ROOT / "dist"), "dist"),
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "track07_08_effect_pool_5_9.json"), "server/template_engine/jianying59_template/resources"),
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "sticker_skin_catalog.json"), "server/template_engine/jianying59_template/resources"),
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "flower_style_catalog.json"), "server/template_engine/jianying59_template/resources"),
    # 照片墙选人用的人脸检测模型（YuNet，MIT）。必须随包分发：目标机器可能长期离线，
    # 而缺了它只会退化成"按画面中心裁"，效果明显变差。
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "face_detection_yunet_2023mar.onnx"), "server/template_engine/jianying59_template/resources"),
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "face_landmarker.task"), "server/template_engine/jianying59_template/resources"),
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "arcface_w600k_mbf.onnx"), "server/template_engine/jianying59_template/resources"),
    (str(PROJECT_ROOT / "server" / "template_engine" / "jianying59_template" / "resources" / "YuNet-LICENSE.txt"), "server/template_engine/jianying59_template/resources"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "mumu-original.png"), "server/content_template_assets"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "mumu-blue.png"), "server/content_template_assets"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "mumu-cyan.png"), "server/content_template_assets"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "mumu-red.png"), "server/content_template_assets"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "references" / "mumu-original-reference.png"), "server/content_template_assets/references"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "references" / "mumu-blue-reference.png"), "server/content_template_assets/references"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "references" / "mumu-cyan-reference.png"), "server/content_template_assets/references"),
    (str(PROJECT_ROOT / "server" / "content_template_assets" / "references" / "mumu-red-reference.png"), "server/content_template_assets/references"),
    (str(PROJECT_ROOT / "server" / "final_engine" / "jianying59_final" / "resources" / "real_photo_effect_pool_5_9.json"), "server/final_engine/jianying59_final/resources"),
    (str(PROJECT_ROOT / "server" / "wechat_index_proxy_addon.py"), "server"),
    (str(FFMPEG_ROOT / "bin" / "ffmpeg.exe"), "tools/ffmpeg/bin"),
    (str(FFMPEG_ROOT / "bin" / "ffprobe.exe"), "tools/ffmpeg/bin"),
    (str(FFMPEG_ROOT / "LICENSE"), "tools/ffmpeg"),
    (str(FFMPEG_ROOT / "README.txt"), "tools/ffmpeg"),
]
# Only explicitly referenced, verified V3 libraries enter the release.
import json
manifest_path = Path(os.environ["V3_RESOURCE_MANIFEST"])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
for item in manifest["files"]:
    source = PROJECT_ROOT / item["path"]
    datas.append((str(source), str(Path(item["path"]).parent)))
datas += [(str(manifest_path), "."), (str(PROJECT_ROOT / "packaging/ffmpeg-runtime.json"), "tools/ffmpeg")]
binaries = []

# MediaPipe's top-level import eagerly imports optional matplotlib helpers.  The
# application provides a lightweight stub before importing MediaPipe, so collect
# the package by path instead of importing it during PyInstaller analysis.
for source in MEDIAPIPE_ROOT.rglob("*"):
    if source.is_file() and "__pycache__" not in source.parts:
        relative_parent = source.relative_to(MEDIAPIPE_ROOT).parent
        datas.append((str(source), str(Path("mediapipe") / relative_parent)))

# These packages use dynamic backends, data files or native binaries.  This is
# intentionally limited to V2's declared runtime dependencies, not all of site-packages.
hiddenimports = [
    "webview.platforms.edgechromium", "webview.platforms.winforms", "clr",
    "pythonnet", "clr_loader", "rapidocr_onnxruntime", "onnxruntime.capi._pybind_state",
]
for source in MEDIAPIPE_ROOT.rglob("*.py"):
    if "__pycache__" not in source.parts:
        module = ".".join(("mediapipe", *source.relative_to(MEDIAPIPE_ROOT).with_suffix("").parts))
        hiddenimports.append(module.removesuffix(".__init__"))
# NumPy, OpenCV, Pillow, ONNX Runtime and pywebview each publish a PyInstaller
# hook.  Do not recursively collect them: that would pull their test/tooling
# trees into the Portable package.  Only V2's dynamic automation packages need
# a complete module collection.
for package in ("uiautomation", "pyJianYingDraft", "rapidocr_onnxruntime", "mitmproxy", "aioquic", "mitmproxy_rs", "mitmproxy_windows"):
    hiddenimports += collect_submodules(package)
    datas += collect_data_files(package)
    binaries += collect_dynamic_libs(package)

# These V2 modules are reached from task-boundary imports instead of the
# desktop launcher's import graph.
for package in ("server.template_engine", "server.final_engine", "server.v2_exporter", "server.windows_automation"):
    hiddenimports += collect_submodules(package)
hiddenimports += list(PRODUCTION_WORKERS)
hiddenimports += ["tools.release_v3_probe", "server.release_runtime",
                  "tools.release_v3_publishing_probe",
                  "tools.ffmpeg_overlay_lab.sticker_layer",
                  "tools.ffmpeg_overlay_lab.sticker_library.library",
                  "tools.ffmpeg_overlay_lab.sticker_library.template_cache",
                  "tools.ffmpeg_overlay_lab.effect_library.library",
                  "tools.ffmpeg_overlay_lab.side_strip_library.library"]
for package in ("server.ffmpeg_templates", "server.ffmpeg_finals", "server.scenery", "server.publishing"):
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
    excludes=["pytest", "torch", "tensorflow", "tensorboard", "pandas", "matplotlib", "scipy", "IPython", "jupyter", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="ShortDramaPlatformV3",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    icon=str(APPLICATION_ICON),
    version=os.environ["V3_VERSION_FILE"],
    # Release builds are windowed; diagnostics may opt in without changing
    # the packaged application code or its default output.
    console=bool(os.environ.get("V3_PORTABLE_CONSOLE")),
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ShortDramaPlatformV3",
)
