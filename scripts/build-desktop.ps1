$ErrorActionPreference = 'Stop'
$campusRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $campusRoot
$campusPython = Join-Path $campusRoot '.venv\Scripts\python.exe'
$campusNode = (Get-Command node.exe -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath 'tools\cloudflared.exe')) { throw 'The official cloudflared connector is missing.' }
& $campusPython scripts/collect-desktop-notices.py $campusNode
if ($LASTEXITCODE -ne 0) { throw 'Could not collect dependency notices.' }
& $campusPython -m PyInstaller --noconfirm --onefile --windowed --name CampusLink --collect-submodules dxcam --hidden-import comtypes.client --add-binary ($campusNode + ';runtime') --add-binary 'tools\cloudflared.exe;tools' --add-data 'server;server' --add-data 'web;web' --add-data 'node_modules\ws;node_modules\ws' --add-data 'build\desktop-notices;licenses' run_desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Unified desktop build failed.' }
Write-Host 'Built dist\CampusLink.exe. Copy this one file to both Windows PCs.'
