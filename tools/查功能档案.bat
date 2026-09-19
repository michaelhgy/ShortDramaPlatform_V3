@echo off
chcp 65001 >nul
cd /d "%~dp0.."
py -3.12 "tools\check_feature_archive.py"
echo.
pause
