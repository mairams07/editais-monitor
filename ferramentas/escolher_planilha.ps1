# Abre uma janela para escolher a planilha CONCORRENTES_FGV.xlsx e copia para entrada\ (o original nao e alterado).
param([string]$Destino)
Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Filter = 'Planilha Excel (*.xlsx)|*.xlsx'
$f.Title = 'Escolha a planilha CONCORRENTES_FGV (sera usada uma copia; o original nao e alterado)'
if ($f.ShowDialog() -ne 'OK') { exit 1 }
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$alvo = Join-Path $Destino ('CONCORRENTES_FGV_' + (Get-Date -Format 'yyyy-MM-dd_HHmmss') + '.xlsx')
Copy-Item -LiteralPath $f.FileName -Destination $alvo
Write-Output ('Copia criada: ' + $alvo)
