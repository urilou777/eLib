@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Installation Scanner Mobile - Librairie ICC Rennes

set "PY_EXE="
if exist "%~dp0runtime_win32\python.exe" set "PY_EXE=%~dp0runtime_win32\python.exe"
if not defined PY_EXE if exist "%~dp0runtime\python.exe" set "PY_EXE=%~dp0runtime\python.exe"
if not defined PY_EXE (
    where python >nul 2>nul
    if %errorlevel% equ 0 set "PY_EXE=python"
)

if not defined PY_EXE (
    echo ERREUR : Python non detecte.
    pause
    exit /b 1
)

echo ========================================================
echo  Configuration du Scanner Mobile et Securite TLS
echo ========================================================
echo.
"%PY_EXE%" setup_mobile.py
pause
