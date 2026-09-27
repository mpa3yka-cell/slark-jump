@echo off
rem Allows the network duel through Windows Firewall on PRIVATE networks:
rem   TCP 50505 - the game itself, UDP 50506 - finding games in the lobby.
rem Run it once on every computer that will play. It asks for administrator rights by itself.
rem To remove the rules later:
rem   netsh advfirewall firewall delete rule name="Slark Duel TCP"
rem   netsh advfirewall firewall delete rule name="Slark Duel UDP"

net session >nul 2>&1
if errorlevel 1 (
    echo Asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

netsh advfirewall firewall delete rule name="Slark Duel TCP" >nul 2>&1
netsh advfirewall firewall delete rule name="Slark Duel UDP" >nul 2>&1
netsh advfirewall firewall add rule name="Slark Duel TCP" dir=in action=allow protocol=TCP localport=50505 profile=private
netsh advfirewall firewall add rule name="Slark Duel UDP" dir=in action=allow protocol=UDP localport=50506 profile=private
echo.
echo Done: the duel is allowed on private networks.
timeout /t 5
