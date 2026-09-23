@echo off
REM Double-click this file to start the procurement portal demo.

cd /d "%~dp0"

if not exist "procurement.db" (
    echo procurement.db is missing. Put a copy of the database in this folder first.
    pause
    exit /b 1
)

echo ==========================================================
echo   Smart Farmer Procurement Portal
echo ==========================================================
echo.
echo   On this computer:   http://localhost:5000
echo   On the same wifi:   http://%COMPUTERNAME%:5000
echo.
echo   Farmer login: registered mobile number, OTP 123456
echo.
echo   Close this window to stop the server.
echo ==========================================================
echo.

start "" http://localhost:5000
python app.py
pause
