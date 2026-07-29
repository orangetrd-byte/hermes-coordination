$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    [System.Windows.MessageBox]::Show('Python not found in PATH.', 'Hermes Channel') | Out-Null
    exit 1
}

$relay = Join-Path $dir 'relay.py'
if (-not (Test-Path $relay)) {
    [System.Windows.MessageBox]::Show("Missing $relay", 'Hermes Channel') | Out-Null
    exit 1
}

$port = 3444
$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python.Source
$psi.Arguments = "`"$relay`""
$psi.WorkingDirectory = $dir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $false

if (-not $existing) {
    $psi.EnvironmentVariables['HERMES_CHANNEL_HOST'] = '0.0.0.0'
}

$proc = [System.Diagnostics.Process]::Start($psi)

if ($proc -eq $null) {
    [System.Windows.MessageBox]::Show('Failed to start relay.', 'Hermes Channel') | Out-Null
    exit 1
}

Start-Sleep -Milliseconds 700
$lan = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Ethernet' -ErrorAction SilentlyContinue).IPAddress
if (-not $lan) { $lan = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi' -ErrorAction SilentlyContinue).IPAddress }
if (-not $lan) { $lan = '127.0.0.1' }
Start-Process "https://$($lan):$port"
