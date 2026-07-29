@echo off
echo Adding firewall rule for Hermes Channel on 8787...
netsh advfirewall firewall add rule name="Hermes Channel 8787" dir=in action=allow protocol=TCP localport=8787 profile=private description="Allow inbound for Hermes Coordination Channel relay"
pause
