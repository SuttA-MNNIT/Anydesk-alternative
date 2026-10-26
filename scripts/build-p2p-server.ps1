$ErrorActionPreference='Stop'
$campusRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $campusRoot
$campusNode=(Get-Command node.exe -ErrorAction Stop).Source
& .venv\Scripts\python.exe scripts/collect-desktop-notices.py $campusNode
if($LASTEXITCODE -ne 0){throw 'Could not collect server dependency notices.'}
& .venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name CampusLinkP2PServer --add-binary ($campusNode+';runtime') --add-binary 'tools\cloudflared.exe;tools' --add-data 'server;server' --add-data 'web;web' --add-data 'node_modules\ws;node_modules\ws' --add-data 'build\desktop-notices;licenses' p2p_server.py
if($LASTEXITCODE -ne 0){throw 'P2P server build failed.'}
Get-Item -LiteralPath 'dist\CampusLinkP2PServer.exe' | Select-Object Name,Length
