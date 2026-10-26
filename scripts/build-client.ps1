$ErrorActionPreference = 'Stop'
$campusRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $campusRoot
$campusCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $campusCompiler)) { throw 'The Windows .NET Framework C# compiler is unavailable.' }
New-Item -ItemType Directory -Force -Path dist | Out-Null
& $campusCompiler /nologo /codepage:65001 /target:winexe /platform:x64 /optimize+ /debug- /out:dist\CampusLinkClient.exe /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll client\*.cs
if ($LASTEXITCODE -ne 0) { throw 'Client build failed.' }
if ((Get-Item -LiteralPath 'dist\CampusLinkClient.exe').Length -ge 10000000) { throw 'Client exceeds the 10 MB size budget.' }
Get-Item -LiteralPath 'dist\CampusLinkClient.exe' | Select-Object Name,Length
