@echo off
chcp 65001 > nul
cd /d "%~dp0"
title Installation Scanner Mobile - Librairie ICC Rennes
echo ========================================================
echo  Configuration du Scanner Mobile et Securite TLS
echo ========================================================
echo.
python setup_mobile.py
pause
