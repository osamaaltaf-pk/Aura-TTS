@echo off
title Aura TTS Portal — Offline Assets Warm-Up
cd /d "%~dp0"

echo ==========================================================
echo         AURA TTS MULTI-ENGINE ASSETS WARM-UP
echo ==========================================================
echo.

:: Ensure virtual environment is present
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment 'venv' not found.
    echo Please run 'install_all.py' first!
    pause
    exit /b 1
)

echo [INFO] Initializing download script in virtual environment...
echo [INFO] This might take a few minutes depending on your internet speed.
echo.

venv\Scripts\python.exe download_models.py
echo.
echo ==========================================================
echo                  ASSETS WARM-UP COMPLETE
echo ==========================================================
echo.
pause
