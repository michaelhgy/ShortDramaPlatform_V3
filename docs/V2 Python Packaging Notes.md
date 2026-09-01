# V2 Python Packaging Notes

`requirements-runtime.txt` is the Windows production-runtime dependency lock.
It was derived from the V2 desktop launch path and its reachable runtime imports,
then pinned to the versions verified with CPython 3.12.10. It intentionally
excludes test-only packages such as `pytest`.

## PyInstaller validation points

- `numpy`, `opencv-python`, `onnxruntime`, `pywin32`, and `pythonnet` carry
  native `.pyd` and/or `.dll` binaries. A future PyInstaller build must verify
  their collected binaries on a clean Windows computer.
- The desktop launcher dynamically imports `webview`; its Windows
  `edgechromium` backend reaches `pythonnet` and Windows WebView2 at runtime.
- OCR reaches `rapidocr_onnxruntime` and ONNX Runtime; final-engine and draft
  flows reach `pyJianYingDraft`, `uiautomation`, OpenCV, NumPy, and Pillow.
- The V2 exporter uses the V2-owned `server/windows_automation` package for
  its Windows/Jianying 5.9 low-level runtime. No adjacent V1 repository is a
  production runtime prerequisite.
- FFmpeg is not a Python package. Its controlled Windows x64 bundle candidate
  is recorded in `packaging/ffmpeg-runtime.json`; the future installer must
  stage its executable files together with the required GPL notice files.
  Jianying/CapCut, Ollama, and WebView2 remain external software or system
  runtime dependencies.
