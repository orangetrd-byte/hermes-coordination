[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$scriptPath = [IO.Path]::GetFullPath($MyInvocation.MyCommand.Path)
$dir = Split-Path -Parent $scriptPath
Set-Location $dir

Add-Type -AssemblyName PresentationFramework

function Show-HermesError([string]$Message) {
    [System.Windows.MessageBox]::Show($Message, 'Hermes Channel', 'OK', 'Error') | Out-Null
}

function ConvertTo-PlainText([Security.SecureString]$SecureValue) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Get-HermesPin {
    if ($env:HERMES_CHANNEL_PIN) { return $env:HERMES_CHANNEL_PIN }

    $stateDir = Join-Path $dir '.hermes'
    $pinFile = Join-Path $stateDir 'channel-pin.clixml'
    if (Test-Path -LiteralPath $pinFile) {
        try {
            return ConvertTo-PlainText (Import-Clixml -LiteralPath $pinFile)
        } catch {
            throw "The saved Hermes PIN could not be decrypted. Remove $pinFile and run the launcher again."
        }
    }

    if (-not (Test-Path -LiteralPath $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir | Out-Null
    }
    $securePin = Read-Host 'Create a Hermes Channel PIN' -AsSecureString
    $plainPin = ConvertTo-PlainText $securePin
    if ([string]::IsNullOrWhiteSpace($plainPin) -or $plainPin.Length -lt 6) {
        throw 'Hermes Channel PIN must contain at least 6 characters.'
    }
    $securePin | Export-Clixml -LiteralPath $pinFile
    [System.Windows.MessageBox]::Show(
        'Hermes saved this PIN with Windows user encryption. Enter the same PIN in the browser.',
        'Hermes Channel'
    ) | Out-Null
    return $plainPin
}

function Get-HermesScriptProcesses([string]$ScriptPath) {
    $exactPath = [IO.Path]::GetFullPath($ScriptPath)
    $escapedPath = [regex]::Escape($exactPath)
    $pattern = '(?i)(?:^|[\s"])' + $escapedPath + '(?:["\s]|$)'
    return @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and $_.CommandLine -match $pattern
        })
}

$pin = Get-HermesPin
$port = 3444
if ($env:HERMES_CHANNEL_PORT) {
    $parsedPort = 0
    if (-not [int]::TryParse($env:HERMES_CHANNEL_PORT, [ref]$parsedPort) -or
        $parsedPort -lt 1 -or $parsedPort -gt 65535) {
        Show-HermesError 'HERMES_CHANNEL_PORT must be a number from 1 through 65535.'
        exit 1
    }
    $port = $parsedPort
}
$hostBind = '0.0.0.0'
$lan = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Ethernet' -ErrorAction SilentlyContinue).IPAddress
if (-not $lan) { $lan = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi' -ErrorAction SilentlyContinue).IPAddress }
if (-not $lan) { $lan = '127.0.0.1' }

$relay = Join-Path $dir 'relay.py'
$loop = Join-Path $dir 'agent_loop.py'
$cert = Join-Path $dir 'server.crt'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python -or -not (Test-Path -LiteralPath $relay) -or
    -not (Test-Path -LiteralPath $loop) -or -not (Test-Path -LiteralPath $cert)) {
    Show-HermesError 'Missing Python, relay.py, agent_loop.py, or server.crt.'
    exit 1
}

$relayProcesses = @(Get-HermesScriptProcesses $relay)
$loopProcesses = @(Get-HermesScriptProcesses $loop)

if ($Restart) {
    @($loopProcesses + $relayProcesses) | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 300
    $relayProcesses = @()
    $loopProcesses = @()
}

$relayProcess = $relayProcesses | Where-Object {
    Get-NetTCPConnection -OwningProcess $_.ProcessId -LocalPort $port -State Listen -ErrorAction SilentlyContinue
} | Select-Object -First 1
$startedRelay = $false

if (-not $relayProcess) {
    $existing = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($existing) {
        $owners = ($existing | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
        Show-HermesError "Port $port is owned by an unrecognized process ($owners). Hermes will not terminate it."
        exit 1
    }

    $psiR = New-Object System.Diagnostics.ProcessStartInfo
    $psiR.FileName = $python.Source
    $psiR.Arguments = "`"$relay`""
    $psiR.WorkingDirectory = $dir
    $psiR.UseShellExecute = $false
    $psiR.CreateNoWindow = $false
    $psiR.EnvironmentVariables['HERMES_CHANNEL_HOST'] = $hostBind
    $psiR.EnvironmentVariables['HERMES_CHANNEL_PORT'] = [string]$port
    $psiR.EnvironmentVariables['HERMES_CHANNEL_PIN'] = $pin
    $relayProcess = [System.Diagnostics.Process]::Start($psiR)
    if (-not $relayProcess) {
        Show-HermesError 'Failed to start the Hermes relay.'
        exit 1
    }
    $startedRelay = $true
}

$ready = $false
for ($i = 0; $i -lt 50; $i++) {
    $health = & curl.exe --silent --show-error --fail --cacert $cert --noproxy '*' `
        --resolve "$($lan):$port`:127.0.0.1" "https://$($lan):$port/api/health" 2>$null
    if ($LASTEXITCODE -eq 0 -and $health -match '"ok"\s*:\s*true') {
        $ready = $true
        break
    }
    if ($relayProcess -is [Diagnostics.Process] -and $relayProcess.HasExited) { break }
    Start-Sleep -Milliseconds 250
}

if (-not $ready) {
    Show-HermesError ('Relay did not become ready on port {0} with the expected certificate.' -f $port)
    exit 1
}

if ($startedRelay -and $loopProcesses) {
    $loopProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    $loopProcesses = @()
}
if ($loopProcesses.Count -gt 1) {
    $loopProcesses | Select-Object -Skip 1 | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

$loopProcess = $loopProcesses | Select-Object -First 1
if (-not $loopProcess) {
    $psiL = New-Object System.Diagnostics.ProcessStartInfo
    $psiL.FileName = $python.Source
    $psiL.Arguments = "`"$loop`""
    $psiL.WorkingDirectory = $dir
    $psiL.UseShellExecute = $false
    $psiL.CreateNoWindow = $false
    $psiL.EnvironmentVariables['HERMES_CHANNEL_HOST'] = '127.0.0.1'
    $psiL.EnvironmentVariables['HERMES_CHANNEL_PORT'] = [string]$port
    $psiL.EnvironmentVariables['HERMES_CHANNEL_PIN'] = $pin
    $loopProcess = [System.Diagnostics.Process]::Start($psiL)
}

Start-Sleep -Milliseconds 500
$loopAlive = if ($loopProcess -is [Diagnostics.Process]) {
    -not $loopProcess.HasExited
} else {
    [bool](Get-Process -Id $loopProcess.ProcessId -ErrorAction SilentlyContinue)
}
if (-not $loopAlive) {
    Show-HermesError 'Agent loop failed to stay running.'
    exit 1
}

if (-not $NoBrowser) {
    Start-Process "https://$($lan):$port"
}
