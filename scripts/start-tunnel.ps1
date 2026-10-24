param([string]$CloudflaredPath)
$ErrorActionPreference = 'Stop'
$campusRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $campusRoot
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/healthz' -TimeoutSec 3
    if ($health.status -ne 'ok') { throw 'Unexpected relay response.' }
} catch {
    throw 'Start START-RELAY.cmd first. The relay must be running on port 8787.'
}
if (-not $CloudflaredPath) {
    $candidate = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($candidate) { $CloudflaredPath = $candidate.Source }
    else { $CloudflaredPath = Join-Path $campusRoot 'tools\cloudflared.exe' }
}
if (-not (Test-Path -LiteralPath $CloudflaredPath -PathType Leaf)) {
    Write-Host 'cloudflared is not installed. Download cloudflared-windows-amd64.exe from:'
    Write-Host 'https://github.com/cloudflare/cloudflared/releases/latest'
    Write-Host 'Save it as tools\cloudflared.exe and run this launcher again.'
    Write-Host 'No public service was started.'
    exit 1
}
Write-Host ''
Write-Host 'Starting a temporary public HTTPS tunnel to CampusLink only.'
Write-Host 'The printed trycloudflare.com URL is your viewer URL and host relay URL.'
Write-Host 'Use the same URL on every host. Keep device IDs and access keys private.'
Write-Host 'This is a development tunnel; its address changes on restart.'
Write-Host 'Keep this window open; press Ctrl+C to remove public access.'
Write-Host ''
& $CloudflaredPath tunnel --protocol http2 --url http://127.0.0.1:8787 --no-autoupdate
exit $LASTEXITCODE
