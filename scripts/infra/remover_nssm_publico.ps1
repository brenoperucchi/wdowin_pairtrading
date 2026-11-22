# ==============================================================================
# Para e remove o servico MagicWalls_Publico (NSSM) e limpa logs rotacionados
# ==============================================================================

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[*] Solicitando privilegios de Administrador para remover o servico Windows (NSSM)..." -ForegroundColor Yellow
    $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process powershell -Verb RunAs -ArgumentList $argList
    exit 0
}

$BASE_DIR = "c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
$LOG_DIR  = "$BASE_DIR\logs"
$SVC_PUB  = "MagicWalls_Publico"

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
        Write-Host "ERRO: nssm.exe nao encontrado." -ForegroundColor Red
        try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch {}
        exit 1
    }
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  MAGIC WALLS - Remocao do Servico $SVC_PUB (NSSM)" -ForegroundColor Cyan
Write-Host "  Diretorio: $BASE_DIR" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Parar e remover servico MagicWalls_Publico
$existingPub = & $NSSM status $SVC_PUB 2>&1
if ($existingPub -notmatch "Can't open service") {
    Write-Host "[1/2] Parando servico $SVC_PUB..." -ForegroundColor Yellow
    & $NSSM stop $SVC_PUB 2>&1
    Start-Sleep -Seconds 1
    Write-Host "[1/2] Removendo servico $SVC_PUB..." -ForegroundColor Yellow
    & $NSSM remove $SVC_PUB confirm 2>&1
    Start-Sleep -Seconds 1
} else {
    Write-Host "[1/2] Servico $SVC_PUB nao encontrado (ja removido)." -ForegroundColor Cyan
}

# 2. Remover logs nssm_publico_5199*.log
Write-Host "[2/2] Removendo logs nssm_publico_5199*.log..." -ForegroundColor Yellow
$logFiles = Get-ChildItem -Path $LOG_DIR -Filter "nssm_publico_5199*.log" -ErrorAction SilentlyContinue
$removedCount = 0
$failedCount = 0
foreach ($lf in $logFiles) {
    try {
        Remove-Item -Path $lf.FullName -Force -ErrorAction Stop
        $removedCount++
    } catch {
        $failedCount++
    }
}
Write-Host "[OK] Logs removidos: $removedCount (restantes/em uso: $failedCount)" -ForegroundColor Green

$stAfter = & $NSSM status $SVC_PUB 2>&1
if ($stAfter -match "Can't open service") {
    Write-Host "[OK] Servico $SVC_PUB removido com sucesso." -ForegroundColor Green
} else {
    Write-Host "[AVISO] Status atual de ${SVC_PUB}: $stAfter" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Concluido! Pressione qualquer tecla para fechar..." -ForegroundColor Cyan
try { $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") } catch {}
