$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$port = 3444
$all = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($all) {
  foreach ($c in $all) {
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Milliseconds 300
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'C:\Python314\python.exe'
$psi.Arguments = 'C:\Users\Dad\Documents\HermesCoordination\relay.py'
$psi.WorkingDirectory = 'C:\Users\Dad\Documents\HermesCoordination'
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $false
$psi.EnvironmentVariables['HERMES_CHANNEL_HOST'] = '0.0.0.0'
$psi.EnvironmentVariables['HERMES_CHANNEL_PORT'] = [string]$port
$psi.EnvironmentVariables['HERMES_CHANNEL_PIN'] = $env:HERMES_CHANNEL_PIN
$p = [System.Diagnostics.Process]::Start($psi)
if (-not $p) {
  [System.Windows.MessageBox]::Show('Failed to start relay.', 'Hermes Channel') | Out-Null
  exit 1
}
Start-Sleep -Seconds 1
Get-NetTCPConnection -LocalPort $port -State Listen | Select-Object LocalAddress,LocalPort,State | Format-Table -AutoSize | Out-String
