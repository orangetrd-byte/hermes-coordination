@echo off
echo Adding firewall rule for Hermes Channel on 3444...
netsh advfirewall firewall add rule name="Hermes Channel Port 3444" dir=in action=allow protocol=TCP localport=3444 profile=private description="Allow inbound for Hermes Coordination Channel relay"
pause
