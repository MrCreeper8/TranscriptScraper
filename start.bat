@echo off
setlocal
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if %errorlevel% equ 0 (
  start "" pythonw.exe "%~dp0transcript_scraper.pyw"
) else (
  start "" pyw.exe -3 "%~dp0transcript_scraper.pyw"
)
