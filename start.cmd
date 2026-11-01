@echo off
cd /d "%~dp0"
pwsh -NoProfile -File "%~dp0start.ps1"
if errorlevel 1 pause
