@echo off
REM Teste dos adaptadores oficiais de Cesgranrio e Instituto AOCP (rodar no computador da FGV).
cd /d "%~dp0\.."
python -m pip install --quiet -r requirements.txt
python ferramentas\testar_bancas_locais.py
pause
