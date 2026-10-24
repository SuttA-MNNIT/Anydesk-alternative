@echo off
cd /d "%~dp0"
set "CAMPUSLINK_CONFIG_DIR=%~dp0config"
if exist "dist\CampusLinkHost.exe" (
  start "" "dist\CampusLinkHost.exe"
) else (
  if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "host\app.py"
  ) else (
    echo Run INSTALL.cmd first.
    pause
    exit /b 1
  )
)
