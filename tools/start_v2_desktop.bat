@echo off
cd /d "%~dp0.."
python "%~dp0run_v2_desktop_restart.py"
if errorlevel 1 pause
