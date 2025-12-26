@echo off
title EnTrus Local Dev Server (http://localhost:8080)
cd /d C:\EnTrusWeb

echo Checking for Python...
where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python was not detected on this system.
  echo Please install Python 3.x, then run this file again.
  echo.
  pause
  exit /b 1
)

echo.
echo Starting local server on http://localhost:8080
echo (Press CTRL + C in this window to stop the server.)
echo.

python -m http.server 8080
