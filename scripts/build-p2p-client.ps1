param([string]$TestSource='', [string]$Output='dist\p2p_Remote_Desktop.exe', [string]$Main='CampusLink.Client.P2PProgram')
$ErrorActionPreference='Stop'
$campusRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $campusRoot
& .venv\Scripts\python.exe scripts/prepare-p2p.py
if($LASTEXITCODE -ne 0){throw 'Dependency verification failed.'}
$campusCompiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Output) | Out-Null
$campusArgs=@('/nologo','/codepage:65001','/target:winexe','/platform:x64','/optimize+','/debug-',('/out:'+$Output),('/main:'+$Main))
if($TestSource){$campusArgs=$campusArgs | Where-Object {$_ -ne '/target:winexe'};$campusArgs+='/target:exe';$campusArgs+='/define:CAMPUSLINK_TESTS';$campusArgs+=[System.IO.Path]::GetFullPath($TestSource)}
foreach($campusReference in @('System.dll','System.Core.dll','System.Security.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll')){$campusArgs+=('/reference:'+$campusReference)}
$campusArgs+='/reference:build\p2p-ref\netstandard.dll'
foreach($campusDll in Get-ChildItem -LiteralPath 'build\p2p' -Filter *.dll){$campusArgs+=('/reference:'+$campusDll.FullName);$campusArgs+=('/resource:'+$campusDll.FullName+'.gz,libraries.'+$campusDll.Name+'.gz')}
$campusArgs+='/resource:build\p2p\THIRD-PARTY-NOTICES.txt,THIRD-PARTY-NOTICES.txt'
foreach($campusSource in Get-ChildItem -LiteralPath client -Filter *.cs | Where-Object {$_.Name -notin @('Program.cs','AssemblyInfo.cs')}){$campusArgs+=$campusSource.FullName}
foreach($campusSource in Get-ChildItem -LiteralPath p2p-client -Filter *.cs){$campusArgs+=$campusSource.FullName}
& $campusCompiler $campusArgs
if($LASTEXITCODE -ne 0){throw 'P2P client build failed.'}
if((Get-Item -LiteralPath $Output).Length -ge 10000000){throw 'Client exceeds 10 MB.'}
Get-Item -LiteralPath $Output | Select-Object Name,Length
