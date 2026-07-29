$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'Hermes Coordination Channel.lnk'
$s = New-Object -ComObject WScript.Shell
$shortcut = $s.CreateShortcut($lnk)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\Dad\Documents\HermesCoordination\Start-HermesChannel.ps1"'
$shortcut.WorkingDirectory = 'C:\Users\Dad\Documents\HermesCoordination'
$shortcut.WindowStyle = 1
$shortcut.IconLocation = 'C:\Windows\System32\shell32.dll,44'
$shortcut.Save()
Write-Output "Created: $lnk"
