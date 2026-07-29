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
$loop = Join-Path $dir 'agent_loop.py'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python -or -not (Test-Path $relay) -or -not (Test-Path $loop)) {
    [System.Windows.MessageBox]::Show('Missing python, relay.py, or agent_loop.py', 'Hermes Channel') | Out-Null
    exit 1
}

$relayRunning = $false
$loopRunning = $false

# Detect exact Hermes relay via command line
try {
    $cmds = Get-CimInstance Win32_Process -Filter "Name='python.exe' AND CommandLine LIKE '%relay.py%'" -ErrorAction Stop
    if ($cmds) {
        foreach ($c in $cmds) {
            $plist = Get-Process -Id $c.ProcessId -ErrorAction SilentlyContinue
            if ($plist -and (Get-NetTCPConnection -OwningProcess $plist.Id -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
                $relayRunning = $true
                break
            }
        }
    }
} catch {}

if (-not $relayRunning) {
    $existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        foreach ($c in $existing) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 300
    }

    $psiR = New-Object System.Diagnostics.ProcessStartInfo
    $psiR.FileName = $python.Source
    $psiR.Arguments = "`"$relay`""
    $psiR.WorkingDirectory = $dir
    $psiR.UseShellExecute = $false
    $psiR.CreateNoWindow = $false
    $psiR.EnvironmentVariables['HERMES_CHANNEL_HOST'] = $hostBind
    $psiR.EnvironmentVariables['HERMES_CHANNEL_PORT'] = [string]$port
    $psiR.EnvironmentVariables['HERMES_CHANNEL_PIN'] = $env:HERMES_CHANNEL_PIN
    [System.Diagnostics.Process]::Start($psiR) | Out-Null
}

# Detect exact Hermes agent loop via command line
try {
    $loopCmds = Get-CimInstance Win32_Process -Filter "Name='python.exe' AND CommandLine LIKE '%agent_loop.py%'" -ErrorAction Stop
    if ($loopCmds) { $loopRunning = $true }
} catch {}

if (-not $loopRunning) {
    $psiL = New-Object System.Diagnostics.ProcessStartInfo
    $psiL.FileName = $python.Source
    $psiL.Arguments = "`"$loop`""
    $psiL.WorkingDirectory = $dir
    $psiL.UseShellExecute = $false
    $psiL.CreateNoWindow = $false
    $psiL.EnvironmentVariables['HERMES_CHANNEL_HOST'] = '127.0.0.1'
    $psiL.EnvironmentVariables['HERMES_CHANNEL_PORT'] = [string]$port
    $psiL.EnvironmentVariables['HERMES_CHANNEL_PIN'] = $env:HERMES_CHANNEL_PIN
    $loopProc = [System.Diagnostics.Process]::Start($psiL)
} else {
    $loopProc = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
        try { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id) AND CommandLine LIKE '%agent_loop.py%'" -ErrorAction Stop) }
        catch { $false }
    } | Select-Object -First 1
}

# Health check relay
$ready = $false
for ($i = 0; $i -lt 50; $i++) {
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

# Confirm agent loop still alive before browser
if ($loopProc -and -not $loopProc.HasExited) {
    Start-Process "https://$($lan):$port"
} else {
    [System.Windows.MessageBox]::Show('Agent loop failed to stay running.', 'Hermes Channel') | Out-Null
    exit 1
}
