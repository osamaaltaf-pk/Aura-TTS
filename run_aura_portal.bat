@echo off
title Aura TTS Portal Launcher
echo ==========================================================
echo               AURA TTS PORTAL LAUNCHER
echo ==========================================================
echo.
echo [INFO] Opening Aura TTS Dashboard in your browser...
start http://127.0.0.1:5000/
echo.
echo [INFO] Starting Central Orchestrator Service...
echo [INFO] Press Ctrl+C in this window to stop all services.
echo.
venv\Scripts\python.exe central_server.py
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start Aura Central Server.
    echo Make sure you have run the setup and installed all requirements!
    echo.
    pause
)
