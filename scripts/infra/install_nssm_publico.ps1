# ==============================================================================
# Instala MagicWalls_Publico (porta 5199) e MagicWalls_Cloudflared (opcional)
# como servicos nativos do Windows via NSSM (reinicio automatico 24/7).
# ==============================================================================

param(
    [string]$TunnelToken = ""
)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[*] Solicitando privilegios de Administrador para instalar os servicos Windows (NSSM)..." -ForegroundColor Yellow
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($TunnelToken) { $argList += " -TunnelToken `"$TunnelToken`"" }
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit 0
}

$BASE_DIR    = "c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
$LOG_DIR     = "$BASE_DIR\logs"
$CONFIG_DIR  = "$BASE_DIR\config"
$TOKEN_FILE  = "$CONFIG_DIR\cloudflared_tunnel_token.txt"
$PYTHON      = "$BASE_DIR\.venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON)) { $PYTHON = "C:\Python313\python.exe" }
$SCRIPT_PUB  = "$BASE_DIR\scripts\painel_publico.py"
$CF_EXE      = "C:\Program Files (x86)\cloudflared\cloudflared.exe"

New-Item -ItemType Directory -Force -Path $LOG_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $CONFIG_DIR | Out-Null

# Localizar NSSM
$nssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
$NSSM = ""
if ($nssmCmd) {
    $NSSM = "nssm"
} else {
    $candidate = "C:\Users\ryzen\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
    if (Test-Path $candidate) {
        $NSSM = $candidate
    } else {
        Write-Host "ERRO: nssm.exe nao encontrado. Instale via: winget install nssm" -ForegroundColor Red
        pause
        exit 1
    }
}

if ($TunnelToken) {
    Set-Content -Path $TOKEN_FILE -Value $TunnelToken.Trim() -Encoding UTF8 -NoNewline
}
$savedToken = ""
if (Test-Path $TOKEN_FILE) {
    $savedToken = (Get-Content $TOKEN_FILE -Raw -ErrorAction SilentlyContinue).Trim()
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  MAGIC WALLS - Instalacao de Servicos Windows via NSSM" -ForegroundColor Cyan
Write-Host "  Diretorio: $BASE_DIR" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Finalizar processos manuais na porta 5199 antes de registrar o servico
$conns5199 = Get-NetTCPConnection -LocalPort 5199 -State Listen -ErrorAction SilentlyContinue
if ($conns5199) {
    foreach ($c in $conns5199) {
        if ($c.OwningProcess -gt 0) {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

# 2. Instalar/atualizar servico MagicWalls_Publico (Porta 5199)
$SVC_PUB = "MagicWalls_Publico"
$existingPub = & $NSSM status $SVC_PUB 2>&1
if ($existingPub -notmatch "Can't open service") {
    & $NSSM stop $SVC_PUB 2>&1 | Out-Null
    Start-Sleep -Seconds 1
    & $NSSM remove $SVC_PUB confirm 2>&1 | Out-Null
    Start-Sleep -Seconds 1
}

Write-Host "[1/2] Instalando servico $SVC_PUB (Proxy Somente-Leitura 127.0.0.1:5199)..." -ForegroundColor Green
& $NSSM install $SVC_PUB $PYTHON "`"$SCRIPT_PUB`" 5199"
& $NSSM set $SVC_PUB AppDirectory $BASE_DIR
& $NSSM set $SVC_PUB AppEnvironmentExtra "PYTHONIOENCODING=utf-8" "PYTHONUTF8=1"
& $NSSM set $SVC_PUB DisplayName "Magic Walls Painel Publico (Porta 5199)"
& $NSSM set $SVC_PUB Description "Servidor web somente-leitura do painel Magic Walls WIN x WDO (porta 5199 -> backend 8080)."
& $NSSM set $SVC_PUB AppStdout "$LOG_DIR\nssm_publico_5199.log"
& $NSSM set $SVC_PUB AppStderr "$LOG_DIR\nssm_publico_5199.log"
& $NSSM set $SVC_PUB AppRotateFiles 1
& $NSSM set $SVC_PUB AppRotateBytes 10485760
& $NSSM set $SVC_PUB AppExit Default Restart
& $NSSM set $SVC_PUB AppRestartDelay 3000
& $NSSM set $SVC_PUB Start SERVICE_AUTO_START
& $NSSM start $SVC_PUB

# 3. Instalar/atualizar servico MagicWalls_Cloudflared (se houver token fixo configurado)
$SVC_CF = "MagicWalls_Cloudflared"
$existingCf = & $NSSM status $SVC_CF 2>&1
if ($savedToken -and (Test-Path $CF_EXE)) {
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" | Where-Object {
        $_.CommandLine -match "5199|cloudflared_5199"
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($existingCf -notmatch "Can't open service") {
        & $NSSM stop $SVC_CF 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        & $NSSM remove $SVC_CF confirm 2>&1 | Out-Null
        Start-Sleep -Seconds 1
    }
    Write-Host "[2/2] Instalando servico $SVC_CF (Tunel Cloudflare Fixo)..." -ForegroundColor Green
    $cfLog = "$LOG_DIR\nssm_cloudflared_5199.log"
    & $NSSM install $SVC_CF $CF_EXE "tunnel --no-autoupdate run --token $savedToken"
    & $NSSM set $SVC_CF AppDirectory $BASE_DIR
    & $NSSM set $SVC_CF DisplayName "Magic Walls Cloudflare Tunnel (URL Fixa)"
    & $NSSM set $SVC_CF Description "Tunel Cloudflare dedicado com URL fixa apontando para http://127.0.0.1:5199."
    & $NSSM set $SVC_CF AppStdout $cfLog
    & $NSSM set $SVC_CF AppStderr $cfLog
    & $NSSM set $SVC_CF AppRotateFiles 1
    & $NSSM set $SVC_CF AppRotateBytes 10485760
    & $NSSM set $SVC_CF AppExit Default Restart
    & $NSSM set $SVC_CF AppRestartDelay 5000
    & $NSSM set $SVC_CF Start SERVICE_AUTO_START
    & $NSSM set $SVC_CF DependOnService $SVC_PUB
    & $NSSM start $SVC_CF
} else {
    Write-Host "[2/2] config\cloudflared_tunnel_token.txt ainda vazio — usando tunel compartilhado/watchdog." -ForegroundColor Yellow
}

# 4. Garantir trigger AtLogon + repeticao a cada 2 min na tarefa JumbaDashboardsWatchdog (Backend 8080 MT5/Profit)
try {
    $wdTask = Get-ScheduledTask -TaskName "JumbaDashboardsWatchdog" -ErrorAction SilentlyContinue
    if ($wdTask) {
        $triggers = @(
            (New-ScheduledTaskTrigger -AtLogon),
            (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2))
        )
        Set-ScheduledTask -TaskName "JumbaDashboardsWatchdog" -Trigger $triggers | Out-Null
        Write-Host "[OK] Gatilho AtLogon configurado em JumbaDashboardsWatchdog (Backend 8080)." -ForegroundColor Green
    }
} catch {
    Write-Host "[AVISO] Nao foi possivel atualizar JumbaDashboardsWatchdog: $($_.Exception.Message)" -ForegroundColor Yellow
}

Start-Sleep -Seconds 3
$stPub = & $NSSM status $SVC_PUB 2>&1
Write-Host ""
Write-Host "Status $SVC_PUB : $stPub" -ForegroundColor Green
if ($savedToken) {
    $stCf = & $NSSM status $SVC_CF 2>&1
    Write-Host "Status $SVC_CF : $stCf" -ForegroundColor Green
}
Write-Host ""
Write-Host "Concluido! Pressione qualquer tecla para fechar..." -ForegroundColor Cyan
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
