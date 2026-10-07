@echo off
REM Rodada completa: baixa a versao mais nova, usa uma COPIA da planilha CONCORRENTES_FGV e gera a planilha atualizada.
REM Pode ser executado de qualquer lugar. O original da planilha nunca e alterado.
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
echo Escolha na janela que vai abrir a planilha CONCORRENTES_FGV.xlsx (sera usada uma copia).
powershell -NoProfile -ExecutionPolicy Bypass -File ferramentas\escolher_planilha.ps1 -Destino "%DESTINO%\entrada"
if errorlevel 1 (
  echo Nenhuma planilha escolhida. Encerrando.
  pause
  exit /b 1
)
python -m pip install --quiet -r requirements.txt
echo.
echo Rodando todas as bancas. Pode levar de 1 a 2 horas; nao feche esta janela.
python run.py
echo.
echo Resultado na pasta que vai abrir: CONCORRENTES_FGV_atualizado_*.xlsx, ALTERACOES_*.xlsx e RELATORIO_*.md
explorer "%DESTINO%\saida"
pause
