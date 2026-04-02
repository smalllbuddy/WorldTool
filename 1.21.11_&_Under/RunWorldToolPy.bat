@echo off
setlocal
cd /d "%~dp0"

echo === WorldTool Runner ===
echo Folder: %CD%
echo.

REM Optional: backup location override
REM set MC_BACKUP_DIR=D:\MinecraftBackups\WorldTool

REM Prefer py launcher, fall back to python
set PY=py
%PY% -V >nul 2>nul
if errorlevel 1 (
  set PY=python
)

echo Using Python command: %PY%
%PY% -V
if errorlevel 1 (
  echo [ERROR] Python not found. Install Python or ensure it's in PATH.
  pause
  exit /b 1
)

REM Create venv if missing
if not exist "venv\Scripts\python.exe" (
  echo.
  echo [INFO] Creating venv...
  %PY% -m venv venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
)

echo.
echo [INFO] Checking dependency: nbtlib
venv\Scripts\python.exe -c "import nbtlib" >nul 2>nul
if errorlevel 1 (
  echo [INFO] nbtlib not found in venv. Installing...
  venv\Scripts\python.exe -m pip install --upgrade pip
  if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    pause
    exit /b 1
  )
  venv\Scripts\python.exe -m pip install nbtlib
  if errorlevel 1 (
    echo [ERROR] Failed to install nbtlib. Check internet or pip settings.
    pause
    exit /b 1
  )
)

echo.
echo [INFO] Running WorldTool.py...
venv\Scripts\python.exe WorldTool.py
set EC=%ERRORLEVEL%

echo.
echo [INFO] WorldTool.py exited with code %EC%
echo Press any key to close.
pause >nul
endlocal