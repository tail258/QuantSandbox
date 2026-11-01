@echo off
cd /d "%~dp0"
pwsh -NoProfile -File "%~dp0scripts\setup.ps1" -MarketData
if errorlevel 1 goto fail
call npm.cmd run build --prefix frontend
if errorlevel 1 goto fail
echo Ready. Run start.cmd.
exit /b 0
:fail
echo Setup failed. Review the error above.
pause
exit /b 1
