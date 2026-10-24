$ErrorActionPreference = 'Stop'
$campusRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $campusRoot
$campusPython = Join-Path $campusRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $campusPython)) { throw 'Run INSTALL.cmd first.' }
& $campusPython -m pip install pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { throw 'Could not install PyInstaller.' }
& $campusPython -m PyInstaller --noconfirm --onefile --windowed --name CampusLinkHost-HighFPS --paths host --collect-submodules dxcam --hidden-import comtypes.client host\app.py
if ($LASTEXITCODE -ne 0) { throw 'Host build failed.' }
Write-Host 'Built dist\CampusLinkHost-HighFPS.exe. Original CampusLinkHost.exe preserved.'
