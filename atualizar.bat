@echo off
REM Atualiza esta pasta com a versao mais nova do GitHub (mairams07/editais-monitor, ramo main).
REM Nao mexe nas pastas entrada, saida e estado (planilhas, resultados e cache ficam como estao).
cd /d "%~dp0"
set TMPZIP=%TEMP%\editais-monitor-main.zip
set TMPDIR=%TEMP%\editais-monitor-main
echo Baixando a versao mais nova...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://github.com/mairams07/editais-monitor/archive/refs/heads/main.zip' -OutFile '%TMPZIP%'"
if errorlevel 1 (
  echo.
  echo Nao foi possivel baixar. Se o repositorio for privado, baixe pelo navegador:
  echo github.com/mairams07/editais-monitor  ^> botao verde Code ^> Download ZIP
  echo e extraia POR CIMA desta pasta: %~dp0
  pause
  exit /b 1
)
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
powershell -NoProfile -Command "Expand-Archive -Force '%TMPZIP%' '%TMPDIR%'"
robocopy "%TMPDIR%\editais-monitor-main" "%~dp0." /E /XD entrada saida estado /NFL /NDL /NJH /NJS
echo.
python -c "from versao import VERSAO; print('Versao instalada:', VERSAO)"
pause
