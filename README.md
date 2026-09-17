# 短剧推广运营系统 V2

自用的短剧推广效率工具（Windows 本地单机软件）。架构：Python 本地服务（127.0.0.1:8782）+ React/Vite 前端 + pywebview 桌面窗口 + SQLite，集成剪映（CapCut）自动化导出。

> 上一版 V1（`D:\ShortDramaPlatform`）**已停用**，业务已全部迁移到本仓库。不要引用或修改 V1。

## 快速开始（开发运行）

前置：Node.js 20+、Python 3.12.10（打包也要求这个版本）。

```bat
npm install
npm run build
py -3.12 tools\run_v2_desktop.py
```

开发调试（前端热更新，服务 8782 + 前端 3000）：

```bat
tools\start_v2_desktop.bat
```

## 改完代码先跑验证

双击 **`tools\一键验证.bat`**（或 `py -3.12 tools\verify_v2.py`）：跑后端测试 + 前端类型检查，**自带隔离**，不会碰真实业务数据。

当前基线与已知失败见 `docs\验证基线.md`。

## 数据在哪

| 项 | 位置 |
|---|---|
| 引导设置（只记数据盘符） | `%LOCALAPPDATA%\ShortDramaPlatformV2\bootstrap-settings.json` |
| 业务数据根目录 | `<数据盘>:\短剧推广运营系统\`（生产文件/内容资产/生成资源/剧集资料/系统数据） |
| 数据库 | `<数据盘>:\短剧推广运营系统\系统数据\database\v2_system.db` |

⚠️ **业务数据是真实生产数据**。测试或脚本必须把 `V2_WORKSPACE_ROOT` 指向临时目录，否则可能误写生产库（2026-09-17 曾发生一次，详见 `docs\决策日志.md`）。

## 打包（便携版）

```bat
py -3.12 packaging\build_portable.py
```

要求 CPython 3.12.10、已执行 `npm run build`；产物在 `packaging\output\`。依赖受控 FFmpeg 包（见 `packaging\ffmpeg-runtime.json`）。

## 文档

- 先读项目根 `AGENTS.md`（工作约定与安全边界）
- 全部文档导航：`docs\文档索引.md`
- 最核心的业务规则：`docs\V2数据与刷新规则.md`

## 目录速览

| 目录 | 内容 |
|---|---|
| `server/` | Python 后端（本地 HTTP 服务、SQLite、模板/成片/导出引擎、收益采集） |
| `src/` | React 前端（工作台、生产中心、任务中心、资料中心、分析页、设置） |
| `tools/` | 启动脚本、诊断脚本、一键验证 |
| `packaging/` | PyInstaller 打包脚本与产物 |
| `docs/` | 业务规则、决策、现状、术语、文件地图 |
