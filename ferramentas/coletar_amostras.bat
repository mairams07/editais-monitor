@echo off
REM Coleta páginas de exemplo de Cesgranrio e Instituto AOCP (rodar no computador da FGV).
cd /d "%~dp0\.."
python ferramentas\coletar_amostras.py
pause
