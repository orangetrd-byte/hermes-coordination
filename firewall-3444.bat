@echo off
set "PORT=%HERMES_CHANNEL_PORT%"
if not defined PORT set "PORT=3444"
echo Adding firewall rule for Hermes Channel on %PORT%...
netsh advfirewall firewall add rule name="Hermes Channel Port %PORT%" dir=in action=allow protocol=TCP localport=%PORT% profile=private description="Allow inbound for Hermes Coordination Channel relay"
pause
