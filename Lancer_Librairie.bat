@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Librairi-E - Caisse Principale

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
    echo  1. Téléchargez Python 3.13 32-bit (x86) sur python.org
    echo     (Lien direct : https://www.python.org/ftp/python/3.13.2/python-3.13.2.exe)
    echo     IMPORTANT : Cochez 'Add python.exe to PATH' lors de l'installation !
    echo  2. OU copiez le dossier autonome 'runtime_win32' a la racine du projet.
    echo.
    pause
    exit /b 1
)

"%PY_EXE%" run.py
if errorlevel 1 pause

