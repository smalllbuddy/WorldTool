@echo off
cd /d "%~dp0"
py WorldTool_Combined.py
if errorlevel 1 python WorldTool_Combined.py
pause
