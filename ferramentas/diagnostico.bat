@echo off
REM Diagnóstico de acesso aos sites das bancas (rodar no computador da FGV).
cd /d "%~dp0\.."
python -m pip install --quiet requests playwright
python -m playwright install chromium
python ferramentas\diagnostico_acesso.py
pause
