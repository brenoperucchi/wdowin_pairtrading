# install_wdo_services.ps1
# Script para instalar os serviços do WDO-WIN Pair Trading como Serviços do Windows usando o NSSM

# 1. Verificar Privilégios de Administrador
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Este script deve ser executado como Administrador! Abra o PowerShell como Administrador e execute-o novamente."
    Exit
}

# 2. Obter o caminho do NSSM dinamicamente a partir do registro do RegimeLiveMonitor
$nssmPath = (Get-ItemProperty -Path HKLM:\System\CurrentControlSet\Services\RegimeLiveMonitor -ErrorAction SilentlyContinue).ImagePath
if ($nssmPath) {
    $nssmPath = $nssmPath -replace '"', ''
} else {
    # Fallback para o caminho padrão conhecido
    $nssmPath = "C:\Users\ryzen\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
}

if (-not (Test-Path $nssmPath)) {
    Write-Error "NSSM não encontrado em: $nssmPath. Verifique se o NSSM está instalado no sistema."
    Exit
}

Write-Host "NSSM localizado em: $nssmPath" -ForegroundColor Green

# 3. Definir caminhos de execução do projeto
$workDir = $PSScriptRoot
$pythonExe = "$workDir\.venv\Scripts\python.exe"
$nodeExe = "C:\Program Files\nodejs\node.exe"
$logsDir = "$workDir\logs"

# Garantir que a pasta de logs existe
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
    Write-Host "Pasta de logs criada em: $logsDir"
}

# Verificar integridade do ambiente virtual
if (-not (Test-Path $pythonExe)) {
    Write-Error "Ambiente virtual (.venv) não encontrado na pasta raiz: $pythonExe"
    Exit
}

# 4. Configuração detalhada de cada serviço
$services = @(
    @{
        Name = "WDOWIN_Backend"
        App = $pythonExe
        Args = "server.py"
        Dir = $workDir
        Stdout = "$logsDir\nssm_backend_stdout.log"
        Stderr = "$logsDir\nssm_backend_stderr.log"
    },
    @{
        Name = "WDOWIN_Bridge"
        App = $pythonExe
        Args = "gex/engine/profit_csv_bridge.py"
        Dir = $workDir
        Stdout = "$logsDir\nssm_bridge_stdout.log"
        Stderr = "$logsDir\nssm_bridge_stderr.log"
    },
    @{
        Name = "WDOWIN_Frontend"
        App = $nodeExe
        Args = "node_modules\vite\bin\vite.js"
        Dir = "$workDir\regime-dashboard"
        Stdout = "$logsDir\nssm_frontend_stdout.log"
        Stderr = "$logsDir\nssm_frontend_stderr.log"
    }
)

# 5. Instalar e iniciar cada serviço
foreach ($svc in $services) {
    $name = $svc.Name
    Write-Host "--------------------------------------------------" -ForegroundColor Cyan
    Write-Host "Configurando serviço: $name" -ForegroundColor Cyan
    
    # Parar e remover qualquer versão antiga que possa estar rodando
    & $nssmPath stop $name 2>$null | Out-Null
    & $nssmPath remove $name confirm 2>$null | Out-Null
    
    # Instalar serviço
    & $nssmPath install $name $svc.App $svc.Args
    
    # Configurar parâmetros essenciais
    & $nssmPath set $name AppDirectory $svc.Dir
    & $nssmPath set $name AppStdout $svc.Stdout
    & $nssmPath set $name AppStderr $svc.Stderr
    & $nssmPath set $name AppRotateFiles 1
    & $nssmPath set $name AppRotateOnline 1
    & $nssmPath set $name AppRotateBytes 5242880
    & $nssmPath set $name AppRestartDelay 10000
    
    # Configurar encoding para o Python lidar com emojis/acentuação nos logs e desabilitar buffer de saída
    if ($name -eq "WDOWIN_Backend" -or $name -eq "WDOWIN_Bridge") {
        & $nssmPath set $name AppEnvironmentExtra "PYTHONIOENCODING=utf-8`nPYTHONUNBUFFERED=1"
    }
    
    # Iniciar o serviço
    & $nssmPath start $name
    
    Write-Host "Serviço $name instalado e iniciado com sucesso!" -ForegroundColor Green
}

Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "Todos os serviços foram criados e iniciados com sucesso!" -ForegroundColor Green
Write-Host "Backend rodando em: http://localhost:8080"
Write-Host "Frontend rodando em: http://localhost:5174"
Write-Host "Logs salvos na pasta: $logsDir"
