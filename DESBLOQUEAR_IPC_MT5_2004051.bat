@echo off
setlocal
chcp 65001 >nul

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando elevacao UAC para limpar o terminal fantasma na Sessao 0...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ============================================================================
echo  Desbloqueio IPC MT5 - Conta 2004051 (Sessao 1 intacta)
echo ============================================================================
echo.

echo [1/3] Reiniciando servico IRAI_Collector...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Restart-Service -Name 'IRAI_Collector' -Force; Start-Sleep -Seconds 2; Write-Host ('      IRAI_Collector status: ' + (Get-Service -Name 'IRAI_Collector').Status)"

echo [2/3] Buscando terminal64.exe fantasma na Sessao 0...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$target = 'C:\Program Files\MetaTrader 5 Terminal\terminal64.exe'; $zombies = Get-CimInstance Win32_Process -Filter 'Name=''terminal64.exe''' | Where-Object { $_.SessionId -eq 0 -and $_.ExecutablePath -and ($_.ExecutablePath -ieq $target) }; if (-not $zombies) { Write-Host ('      Nenhum processo fantasma na Sessao 0 encontrado para ' + $target) } else { foreach ($z in $zombies) { Write-Host ('      Encerrando PID ' + $z.ProcessId + ' (SessionId=0): ' + $z.ExecutablePath); Stop-Process -Id $z.ProcessId -Force } }"

echo [3/3] Testando conexao IPC com MetaTrader 5 Terminal...
"C:\Python313\python.exe" -c "import MetaTrader5 as mt5; p = r'C:\Program Files\MetaTrader 5 Terminal\terminal64.exe'; ok = mt5.initialize(path=p, timeout=8000); ai = mt5.account_info() if ok else None; print('OK -> login=' + str(ai.login) if ok and ai else 'FALHA -> ' + str(mt5.last_error())); mt5.shutdown() if ok else None"

echo.
pause
