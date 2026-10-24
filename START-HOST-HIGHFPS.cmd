@echo off
cd /d "%~dp0"
set "CAMPUSLINK_CONFIG_DIR=%~dp0config"
if exist "dist\CampusLinkHost-HighFPS.exe" (
  start "" "dist\CampusLinkHost-HighFPS.exe"
) else (
  echo Build the High FPS executable using scripts\build-host.ps1 first.
  pause
  exit /b 1
)
