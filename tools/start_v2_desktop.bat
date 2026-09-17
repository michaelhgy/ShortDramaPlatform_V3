@echo off
cd /d "%~dp0.."
py -3.12 "%~dp0run_v2_desktop_restart.py"
if errorlevel 1 pause
