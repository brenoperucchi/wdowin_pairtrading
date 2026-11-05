# Gera o perfil "Jumba_11_CARTEIRA_ALINHADA" no terminal MT5 "milhao"
# a partir do perfil Jumba_18_WF_MONITOR_V2 (mesmos inputs), mantendo apenas
# as EAs aprovadas na comparação Python x MT5 (05/11/2026):
#   WIN: EST-01, 04, 07, 13, 14, 15, 16  |  WDO: WDO-02, 07, 09, 10  | + Monitor
param(
    [string]$DataDir = "$env:APPDATA\MetaQuotes\Terminal\84C7E99445FB5608A3EF549AD3602AC1",
    [string]$Source  = "Jumba_18_WF_MONITOR_V2",
    [string]$Target  = "Jumba_11_CARTEIRA_ALINHADA"
)
$src = Join-Path $DataDir "MQL5\Profiles\Charts\$Source"
$dst = Join-Path $DataDir "MQL5\Profiles\Charts\$Target"
# chartNN do perfil origem -> ordem no novo perfil
$keep = @("chart01","chart03","chart05","chart08","chart09","chart10","chart11",   # EST-01,04,07,13,14,15,16
          "chart12","chart14","chart15","chart16",                                 # WDO-02,07,09,10
          "chart19")                                                               # Monitor
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Force $dst | Out-Null
$i = 0
foreach ($c in $keep) {
    $i++
    $txt = Get-Content (Join-Path $src "$c.chr") -Encoding Unicode
    $txt = $txt -replace '^id=\d+$', ("id=1460000000000007{0:D2}" -f $i)
    $txt = $txt -replace '\(18 ROBOS\)', '(11 ROBOS - CARTEIRA ALINHADA)'
    # janelas em cascata simples (4 colunas x 3 linhas)
    $col = ($i - 1) % 4; $row = [math]::Floor(($i - 1) / 4)
    $txt = $txt -replace '^window_left=\d+$',   ("window_left={0}"   -f ($col * 240))
    $txt = $txt -replace '^window_top=\d+$',    ("window_top={0}"    -f ($row * 210))
    $txt = $txt -replace '^window_right=\d+$',  ("window_right={0}"  -f ($col * 240 + 240))
    $txt = $txt -replace '^window_bottom=\d+$', ("window_bottom={0}" -f ($row * 210 + 210))
    Set-Content -Path (Join-Path $dst ("chart{0:D2}.chr" -f $i)) -Value $txt -Encoding Unicode
}
Get-ChildItem $dst | ForEach-Object {
    $l = Get-Content $_.FullName -Encoding Unicode | Where-Object { $_ -match '^(symbol|description)=' }
    "{0}: {1}" -f $_.Name, ($l -join ' | ')
}

