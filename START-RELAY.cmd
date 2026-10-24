@echo off
cd /d "%~dp0"
if not exist "node_modules\ws" (
  echo Run INSTALL.cmd first.
  pause
  exit /b 1
)
if not exist "config\relay.json" call npm.cmd run setup
node server\index.mjs
pause
