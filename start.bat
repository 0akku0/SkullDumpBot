@echo off
title SkullDump Bot
cd /d "%~dp0"

echo.
echo  ============================
echo    SkullDump Bot  ^|  Starting
echo  ============================
echo.

REM Check if Ollama is already running
echo [1/2] Checking Ollama...
curl -s http://localhost:11434 > nul 2>&1
if %errorlevel% == 0 (
    echo       Ollama already running. Good to go.
) else (
    echo       Starting Ollama in background...
    start /min "Ollama" ollama serve
    timeout /t 4 /nobreak > nul
    echo       Ollama started.
)

echo.
echo [2/2] Launching SkullDump Bot...
echo       You'll get a greeting on Telegram in a moment.
echo.
echo       Press Ctrl+C to stop.
echo.

python listener.py

echo.
echo SkullDump Bot has stopped.
pause
