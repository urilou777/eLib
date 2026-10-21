@echo off
chcp 65001 > nul
cd /d "%~dp0"
title eLib - Caisse Principale

set "PY_EXE="
if exist "%~dp0runtime_win32\python.exe" set "PY_EXE=%~dp0runtime_win32\python.exe"
if not defined PY_EXE if exist "%~dp0runtime\python.exe" set "PY_EXE=%~dp0runtime\python.exe"
if not defined PY_EXE (
    where python >nul 2>nul
    if %errorlevel% equ 0 set "PY_EXE=python"
)

if not defined PY_EXE (
    echo ========================================================
    echo  ERREUR : Python n'a pas ete detecte sur ce PC !
    echo ========================================================
    echo.
    echo  Sur un PC Windows 10 32-bit :
    echo  1. Téléchargez Python 3.10 32-bit (x86) sur python.org
    echo     (Lien direct : https://www.python.org/downloads/release/python-31011/)
    echo     IMPORTANT : Cochez 'Add python.exe to PATH' lors de l'installation !
    echo  2. OU copiez le dossier autonome 'runtime_win32' a la racine du projet.
    echo.
    pause
    exit /b 1
)

"%PY_EXE%" -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 4 else 1)"
if errorlevel 1 (
    echo ========================================================
    echo  ERREUR : Cette application necessite Python 32-bit x86.
    echo ========================================================
    echo Installez Python 3.10 32-bit ou utilisez runtime_win32.
    pause
    exit /b 1
)

"%PY_EXE%" run.py
if errorlevel 1 pause
