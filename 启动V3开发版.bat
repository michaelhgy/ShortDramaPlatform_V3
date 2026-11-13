@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "V2_DESKTOP_TITLE=短剧推广运营系统 V3（开发版）"

echo 检查上一次 V3 后台。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\stop_v3_dev_backend.ps1"
if errorlevel 2 goto failed

if not exist "node_modules\.bin\vite.cmd" (
    echo 正在安装 V3 的界面依赖，首次启动需要一些时间。
    call npm ci
    if errorlevel 1 goto failed
)

echo 正在构建 V3 界面。
call npm run build
if errorlevel 1 goto failed

py -3.12 tools\run_v2_desktop.py
if errorlevel 1 goto failed
exit /b 0

:failed
echo V3 未能启动，请查看上方提示。若仍有其他 V3 实例运行，请先关闭它。
pause
exit /b 1
