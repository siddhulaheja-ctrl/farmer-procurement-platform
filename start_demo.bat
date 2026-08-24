@echo off
REM Double-click this file to start the procurement portal demo.
REM Seeds the database on first run, then starts the server and opens a browser.

cd /d "%~dp0"

if not exist "procurement.db" (
    echo No database found. Creating demo data, this takes a few seconds...
    python seed.py
    echo.
)

echo ==========================================================
echo   Smart Farmer Procurement Portal
echo ==========================================================
echo.
echo   On this computer:   http://localhost:5000
echo   On the same wifi:   http://%COMPUTERNAME%:5000
echo.
echo   Farmer login: 9000000001  or  9000000002    OTP: 123456
echo   Staff login:  ADMIN / demo123
echo.
echo   Close this window to stop the server.
echo ==========================================================
echo.

start "" http://localhost:5000
python app.py
pause
