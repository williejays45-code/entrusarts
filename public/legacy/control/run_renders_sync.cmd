@echo off
title EnTrus  Phase 1 Renders Sync
powershell -ExecutionPolicy Bypass -NoLogo -NoProfile -File "C:\EnTrusWeb\scripts\entrus_phase1_renders_sync.ps1"
echo.
echo -----------------------------------
echo Press any key to close this window.
pause >nul
