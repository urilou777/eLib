@echo off
chcp 65001 > nul
title Atelier de Scission des Ventes - Librairi-E
echo.
echo ========================================================================
echo   LIBRAIRI-E : ATELIER EPHEMERE DE SCISSION DES VENTES HISTORIQUES
echo   Outil autonome et jetable (n'affecte pas le code de production)
echo ========================================================================
echo.
echo Lancement du serveur local sur http://127.0.0.1:8769 ...
python tools\repair_sales_gui.py
pause
