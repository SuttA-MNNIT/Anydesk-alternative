@echo off
cd /d "%~dp0"
call npm.cmd ci
if errorlevel 1 goto failed
call npm.cmd run setup
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r host\requirements.lock.txt
if errorlevel 1 goto failed
echo Installation complete. Start START-RELAY.cmd and START-HOST.cmd.
pause
exit /b 0
:failed
echo Installation failed. See the error above.
pause
exit /b 1
