@echo off
title EnTrus  Web Products Check
powershell -ExecutionPolicy Bypass -NoLogo -NoProfile -File "C:\EnTrusWeb\scripts\entrus_web_products_check.ps1"
echo.
echo -----------------------------------
echo Press any key to close this window.
pause >nul
