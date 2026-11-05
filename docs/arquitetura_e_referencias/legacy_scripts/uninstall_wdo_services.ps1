# uninstall_wdo_services.ps1
# Script para desinstalar os serviços do WDO-WIN Pair Trading

# 1. Verificar Privilégios de Administrador
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Este script deve ser executado como Administrador! Abra o PowerShell como Administrador e execute-o novamente."
    Exit
}

# 2. Obter o caminho do NSSM dinamicamente
$nssmPath = (Get-ItemProperty -Path HKLM:\System\CurrentControlSet\Services\RegimeLiveMonitor -ErrorAction SilentlyContinue).ImagePath
if ($nssmPath) {
    $nssmPath = $nssmPath -replace '"', ''
} else {
    $nssmPath = "C:\Users\ryzen\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
}

if (-not (Test-Path $nssmPath)) {
    Write-Error "NSSM não encontrado em: $nssmPath."
    Exit
}

$services = @("WDOWIN_Backend", "WDOWIN_Bridge", "WDOWIN_Frontend")

foreach ($name in $services) {
    Write-Host "Removendo serviço: $name" -ForegroundColor Yellow
    & $nssmPath stop $name 2>$null | Out-Null
    & $nssmPath remove $name confirm 2>$null | Out-Null
    Write-Host "Serviço $name removido!" -ForegroundColor Green
}

Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "Desinstalação concluída com sucesso!" -ForegroundColor Green
