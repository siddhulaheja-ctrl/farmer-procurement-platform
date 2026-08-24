@echo off
REM Wipes the database and regenerates fresh demo data.
REM Run this before a presentation so the demo starts from a known state.
cd /d "%~dp0"
python seed.py
echo.
pause
