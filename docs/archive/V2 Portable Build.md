> 🗄 **2026-09-19 已归档**：不再维护，仅供追溯。打包笔记；真要重新打包时再启用。

# V2 Portable Build

使用 CPython 3.12.10 的干净构建虚拟环境安装 `requirements-runtime.txt` 与
`requirements-build.txt`，随后执行：

```powershell
python packaging/build_portable.py
```

该入口只接受已验证的 `D:\V2_PackagingCache\ffmpeg\8.1`（或
`V2_FFMPEG_CACHE_ROOT`）内容；它会校验 manifest 的 archive、`ffmpeg.exe` 和
`ffprobe.exe` SHA-256，绝不下载替代文件。输出位于 `packaging/output/`，不应提交。

Portable 是 PyInstaller `onedir` 包，包含前端 `dist`、受控 FFmpeg/FFprobe 及其
LICENSE/README notice。用户数据库、素材、日志和剪映草稿仍位于用户数据目录或所选
数据盘，不能放入 Portable 目录。
