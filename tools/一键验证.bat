@echo off
chcp 65001 >nul
cd /d "%~dp0.."
py -3.12 "tools\verify_v2.py" %*
echo.
pause
