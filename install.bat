@echo off
setlocal
cd /d "%~dp0"
where python.exe >nul 2>nul
if %errorlevel% equ 0 (
  python.exe -m pip install --upgrade --target "%~dp0vendor" yt-dlp
) else (
  py.exe -3 -m pip install --upgrade --target "%~dp0vendor" yt-dlp
)
pause
