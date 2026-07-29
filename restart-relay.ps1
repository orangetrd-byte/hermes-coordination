$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $dir 'Start-HermesChannel.ps1') -Restart
exit $LASTEXITCODE
