@echo off
REM Baixa a versao mais nova do GitHub numa pasta nova e roda o teste de Cesgranrio e AOCP dali.
REM Pode ser executado de qualquer lugar (ex.: direto da pasta Downloads). Nao usa nenhuma pasta antiga.
setlocal
set DESTINO=%USERPROFILE%\editais-monitor-v5
set TMPZIP=%TEMP%\editais-monitor-main.zip
echo Baixando a versao mais nova do GitHub...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://github.com/mairams07/editais-monitor/archive/refs/heads/main.zip' -OutFile '%TMPZIP%'"
if errorlevel 1 (
  echo Falha no download. Verifique a internet e tente de novo.
  pause
  exit /b 1
)
if exist "%TEMP%\editais-monitor-unzip" rmdir /s /q "%TEMP%\editais-monitor-unzip"
powershell -NoProfile -Command "Expand-Archive -Force '%TMPZIP%' '%TEMP%\editais-monitor-unzip'"
robocopy "%TEMP%\editais-monitor-unzip\editais-monitor-main" "%DESTINO%" /E /XD entrada saida estado /NFL /NDL /NJH /NJS >nul
cd /d "%DESTINO%"
echo.
echo Pasta usada: %DESTINO%
python -c "from versao import VERSAO; print('Versao do codigo:', VERSAO)"
echo.
python -m pip install --quiet -r requirements.txt
python ferramentas\testar_bancas_locais.py
echo.
echo O arquivo para enviar ao Claude esta na pasta que vai abrir agora (TESTE_BANCAS_....zip).
explorer "%DESTINO%\saida"
pause
