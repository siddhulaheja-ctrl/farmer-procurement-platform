@echo off
REM Double-click this to put the demo on a public link for your teammates.
REM The real work is in share_demo.ps1 alongside this file.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0share_demo.ps1"
