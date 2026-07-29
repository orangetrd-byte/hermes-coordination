$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

if (-not $env:HERMES_CHANNEL_PIN) {
    [System.Windows.MessageBox]::Show('Set $env:HERMES_CHANNEL_PIN before starting Hermes Channel.', 'Hermes Channel') | Out-Null
    exit 1
}

$port = 3444
$hostBind = '0.0.0.0'
$lan = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Ethernet' -ErrorAction SilentlyContinue).IPAddress
if (-not $lan) { $lan = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi' -ErrorAction SilentlyContinue).IPAddress }
if (-not $lan) { $lan = '127.0.0.1' }

$relay = Join-Path $dir 'relay.py'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python -or -not (Test-Path $relay)) {
    [System.Windows.MessageBox]::Show('Missing python or relay.py', 'Hermes Channel') | Out-Null
    exit 1
}

$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $trusted = $false
    foreach ($c in $existing) {
        try {
            $p = Get-Process -Id $c.OwningProcess -ErrorAction Stop
            $cmd = $p.Path
            if ($cmd -match 'python' -or $cmd -match 'relay.py') {
                $trusted = $true
                break
            }
        } catch {}
    }
    if ($trusted) {
        Start-Process "https://$($lan):$port"
        exit 0
    }
    foreach ($c in $existing) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python.Source
$psi.Arguments = "`"$relay`""
$psi.WorkingDirectory = $dir
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $false
$psi.EnvironmentVariables['HERMES_CHANNEL_HOST'] = $hostBind
$psi.EnvironmentVariables['HERMES_CHANNEL_PORT'] = [string]$port
$psi.EnvironmentVariables['HERMES_CHANNEL_PIN'] = $env:HERMES_CHANNEL_PIN

$proc = [System.Diagnostics.Process]::Start($psi)
if (-not $proc) {
    [System.Windows.MessageBox]::Show('Failed to start relay.', 'Hermes Channel') | Out-Null
    exit 1
}

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "https://127.0.0.1:$port/api/health" -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 250
}

if (-not $ready) {
    [System.Windows.MessageBox]::Show('Relay did not become ready on port {0}.' -f $port, 'Hermes Channel') | Out-Null
    exit 1
}

Start-Process "https://$($lan):$port"
