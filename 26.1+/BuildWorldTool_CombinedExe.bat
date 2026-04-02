@echo off
setlocal
cd /d "%~dp0"

py -m pip install --upgrade pyinstaller
if errorlevel 1 python -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo Failed to install PyInstaller.
  pause
  exit /b 1
)

py -m PyInstaller --onefile --name WorldConverterTool WorldTool_Combined.py
if errorlevel 1 python -m PyInstaller --onefile --name WorldConverterTool WorldTool_Combined.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo Built EXE:
echo %CD%\dist\WorldConverterTool.exe
pause
endlocal
