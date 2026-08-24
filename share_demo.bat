@echo off
REM Double-click this to put the demo on a public link your teammates can open
REM from anywhere. Starts the server, then opens a free Cloudflare quick tunnel.
REM
REM The link only works while this window and the server window stay open, and
REM you get a NEW link every time you run this. Share the link, not this file.

cd /d "%~dp0"

if not exist "procurement.db" (
    echo No database found. Creating demo data, this takes a few seconds...
    python seed.py
    echo.
)

REM cloudflared is installed per-user by winget; use the full path so this
REM works even in a shell that has not picked up the PATH change yet.
set "CFD=%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe"
if not exist "%CFD%" set "CFD=cloudflared"

echo Starting the portal server...
start "Procurement Portal Server" /min cmd /c "python app.py"

REM Give Flask a moment to bind port 5000 before the tunnel connects.
timeout /t 4 /nobreak >nul

echo.
echo ==========================================================
echo   Opening a public tunnel. Watch for the line that says
echo   "Your quick Tunnel has been created!" - the
echo   https://....trycloudflare.com address below it is the
echo   link to send your teammates.
echo.
echo   Logins to send with it:
echo     Farmer  9000000001  or  9000000002   OTP 123456
echo     Staff   ADMIN / demo123
echo.
echo   Closing this window takes the link down.
echo ==========================================================
echo.

"%CFD%" tunnel --url http://localhost:5000

echo.
echo Tunnel closed. The server window may still be running - close it too.
pause
