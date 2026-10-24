# Read-only: no port scanning, firewall changes, router login or throughput tests.
$ErrorActionPreference = 'Continue'
$campusRoot = Split-Path -Parent $PSScriptRoot
$campusReport = [ordered]@{ capturedAt = (Get-Date -Format o); adapters = @(); ipv4 = @(); defaultRoutes = @(); globalIPv6 = @(); publicEgressIP = $null; notes = @() }
$campusReport.adapters = @(Get-NetAdapter | Select-Object Name, Status, LinkSpeed, InterfaceDescription)
$campusReport.ipv4 = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object InterfaceAlias, IPAddress, PrefixLength)
$campusReport.defaultRoutes = @(Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Select-Object InterfaceAlias, NextHop, RouteMetric)
$campusReport.globalIPv6 = @(Get-NetIPAddress -AddressFamily IPv6 | Where-Object { $_.IPAddress -notmatch '^(fe80|::1|fd|fc)' } | Select-Object InterfaceAlias, IPAddress, PrefixLength)
try { $campusReport.publicEgressIP = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=json' -TimeoutSec 10).ip }
catch { $campusReport.notes += 'Public egress lookup was unavailable.' }
$campusReport.notes += 'Link speed is not measured Internet upload/download throughput.'
$campusReport.notes += 'An egress IP does not establish that the router accepts inbound connections.'
$campusReport.notes += 'No external reachability test, firewall changes or campus network scan performed.'
$campusReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $campusRoot 'docs\network-inspection.json') -Encoding utf8
$campusReport | ConvertTo-Json -Depth 6
