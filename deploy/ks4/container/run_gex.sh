#!/usr/bin/env bash
# Roda dentro do container mt5-a. Esteira diaria do GEX para WIN e WDO (mesmo codigo do Miqueias).
# - LC_ALL UTF-8: sem isso o Wine nao cria o arquivo "Posicoes em aberto-*.csv" baixado da B3.
# - A B3 so publica o OI completo do D-1 por volta das 10h. Antes disso o motor usa o ultimo arquivo
#   local valido (fallback do proprio motor). O marcador .gex_done_<data> so nasce quando o CSV do dia
#   esperado esta completo (>1 MB); ate la o timer tenta de novo.
export WINEPREFIX=/home/mt5/.mt5 WINEDEBUG=-all TZ=BRT3 PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8 LANG=C.UTF-8 GEX_SCHEDULED=1
export MW_MT5_PATH="C:/MT5-a/terminal64.exe"
cd /home/mt5/.mt5/drive_c/magicwalls || exit 1
mkdir -p gex/docs gex/data gex/data/bak
PY=(/opt/wine-staging/bin/wine "C:\\Program Files\\Python312\\python.exe")
EXP=$("${PY[@]}" -c "from gex.engine.main import get_expected_trading_day as g; print(g())" 2>/dev/null | tr -d "\r" | tail -1)
case "$EXP" in 20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;; *) echo "GEX: nao obtive a data esperada ($EXP)"; exit 1;; esac
MARK="gex/data/.gex_done_$EXP"
if [ -f "$MARK" ]; then echo "GEX de $EXP ja concluido"; exit 0; fi
cp -f gex/data/win_walls_cache.json gex/data/usd_brl_walls_cache.json gex/data/bak/ 2>/dev/null
rc=0
for mod in gex.engine.main gex.engine.main_dol; do
  echo "=== $(date "+%F %T") $mod (esperado $EXP)"
  timeout 900 "${PY[@]}" -u -m "$mod" || { echo "FALHOU $mod rc=$?"; rc=1; }
done
D="${EXP:8:2}-${EXP:5:2}-${EXP:0:4}"
CSV="gex/data/Posições em aberto-$D.csv"
if [ -f "$CSV" ] && [ "$(stat -c %s "$CSV")" -gt 1000000 ]; then
  touch "$MARK"; echo "GEX: OI de $EXP completo, dia concluido"
else
  echo "GEX: OI de $EXP ainda incompleto na B3; walls calculadas com o ultimo arquivo local. Nova tentativa pelo timer."
fi
exit $rc
