# Run once as Administrator (right-click PowerShell -> Run as administrator), then:
#   cd path\to\BarongClassifier
#   .\allow-mobile-firewall.ps1

$ErrorActionPreference = "Stop"

foreach ($port in 5000, 5001) {
  $name = "BarongClassifier Port $port"
  Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
  New-NetFirewallRule `
    -DisplayName $name `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort $port `
    -Profile Any | Out-Null
  Write-Host "Allowed inbound TCP $port ($name)"
}

Write-Host ""
Write-Host "On your phone (same Wi-Fi), open HTTPS (needed for live camera):"
Write-Host "  Customer  https://192.168.1.53:5000"
Write-Host "  Owner     https://192.168.1.53:5001"
Write-Host "Chrome will warn about the local certificate — tap Advanced → Proceed."
Write-Host ""
Write-Host "If the PC IP changed, run: ipconfig   and use the Wi-Fi IPv4 address."
