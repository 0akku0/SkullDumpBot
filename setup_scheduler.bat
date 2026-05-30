@echo off
chcp 65001 >nul
echo Setting up daily auto-organize at midnight...

schtasks /create ^
  /tn "SkullDump Daily Organizer" ^
  /tr "python \"%~dp0organizer.py\"" ^
  /sc DAILY ^
  /st 00:00 ^
  /f

if %ERRORLEVEL% == 0 (
    echo.
    echo Done! SkullDump will auto-organize your Inbox every day at midnight.
    echo To change the time, edit this file and update /st 00:00
    echo To remove: schtasks /delete /tn "SkullDump Daily Organizer" /f
) else (
    echo Failed to create scheduled task. Try running as Administrator.
)
pause
