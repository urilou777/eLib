@echo off
chcp 65001 > nul
title Atelier de Scission des Ventes - eLib
cd /d "%~dp0"

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

echo.
echo ========================================================================
echo   eLIB : ATELIER EPHEMERE DE SCISSION DES VENTES HISTORIQUES
echo   Outil autonome et jetable (n'affecte pas le code de production)
echo ========================================================================
echo.
echo Lancement du serveur local sur http://127.0.0.1:8769 ...
"%PY_EXE%" tools\repair_sales_gui.py
pause
