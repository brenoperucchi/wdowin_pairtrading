$ErrorActionPreference = "Stop"
$log = "C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\logs\install_magicwalls_cloudflared.log"
function Log($m) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; Add-Content -Path $log -Value $line -Encoding utf8; Write-Output $line }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Log "isAdmin=$isAdmin user=$([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"
if (-not $isAdmin) { Log "NOT ADMIN — abort"; exit 2 }

$NSSM = "C:\Users\ryzen\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
$CF_EXE = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$BASE = "C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
$SVC = "MagicWalls_Cloudflared"
$fso = New-Object -ComObject Scripting.FileSystemObject
$cfShort = $fso.GetFile($CF_EXE).ShortPath
$ymlShort = $fso.GetFile("$BASE\config\cloudflared-magicwalls.yml").ShortPath
$logShort = $fso.GetFolder("$BASE\logs").ShortPath + "\nssm_cloudflared_5199.log"
$dirShort = $fso.GetFolder($BASE).ShortPath
$params = "--config $ymlShort --logfile $logShort tunnel --no-autoupdate run magicwalls"
Log "cfShort=$cfShort"
Log "params=$params"

$existing = & $NSSM status $SVC 2>&1 | Out-String
Log "existing status: $existing"
if ($existing -notmatch "Can't open service") {
  & $NSSM stop $SVC 2>&1 | Out-String | ForEach-Object { Log $_ }
  Start-Sleep -Seconds 2
  & $NSSM remove $SVC confirm 2>&1 | Out-String | ForEach-Object { Log $_ }
  Start-Sleep -Seconds 1
}

& $NSSM install $SVC $cfShort $params
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { Log "install exit $LASTEXITCODE"; exit 3 }
& $NSSM set $SVC AppDirectory $dirShort
& $NSSM set $SVC DisplayName "Magic Walls Cloudflare Tunnel (URL Fixa)"
& $NSSM set $SVC Description "Tunel Cloudflare nomeado magicwalls: https://walls.css-pro.com.br -> 127.0.0.1:5199 e https://roboswalls.css-pro.com.br -> 127.0.0.1:5198."
& $NSSM set $SVC AppStdout "$BASE\logs\nssm_cloudflared_5199_svc_stdout.log"
& $NSSM set $SVC AppStderr "$BASE\logs\nssm_cloudflared_5199_svc_stderr.log"
& $NSSM set $SVC AppRotateFiles 1
& $NSSM set $SVC AppRotateBytes 10485760
& $NSSM set $SVC AppExit Default Restart
& $NSSM set $SVC AppRestartDelay 5000
& $NSSM set $SVC Start SERVICE_AUTO_START
# Do NOT depend on MagicWalls_Publico (that service is currently paused)
& $NSSM start $SVC
Start-Sleep -Seconds 4
$st = & $NSSM status $SVC 2>&1 | Out-String
Log "final status: $st"
if ($st -match "SERVICE_RUNNING") { exit 0 } else { exit 4 }
