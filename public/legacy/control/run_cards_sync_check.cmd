@echo off
title EnTrus  Card Images Sync + Check
powershell -ExecutionPolicy Bypass -NoLogo -NoProfile -File "C:\EnTrusWeb\scripts\entrus_cards_sync_and_check.ps1"
echo.
echo -----------------------------------
echo Press any key to close this window.
pause >nul
