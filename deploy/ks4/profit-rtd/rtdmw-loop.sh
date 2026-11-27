#!/bin/bash
# Cliente RTD unico (substitui o rtdmin-loop.sh). O servidor RTD do Profit so aceita uma sessao: nao rode outro cliente RTD junto.
# Reabre se o Profit ainda nao estiver pronto, se o cliente cair ou se o watchdog (sem dados por 60 s em pregao) sair.
# O fd 9 (lock) NAO pode vazar para o wine: o wineserver/explorer.exe o herdaria e o lock ficaria preso ate o container reiniciar.
exec 9>/tmp/rtdmw.lock; flock -n 9 || exit 0
export DISPLAY=:99
cd /home/mt5/.mt5/rtd
LOG=/home/mt5/.mt5/rtd/mw-live.log
while true; do
  [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 5000000 ] && : > "$LOG"
  echo "$(date '+%F %T') iniciando rtdmw" >> "$LOG"
  wine rtdmw.exe 'Z:\home\mt5\.mt5\rtd-csv' 'WINZ26=WINZ26' 'WDOZ26=WDOZ26' '--tt=T&T0:WINZ26:500' '--tt=T&T1:WDOZ26:500' >> "$LOG" 2>&1 9>&-
  echo "$(date '+%F %T') rtdmw saiu ($?), nova tentativa em 20s" >> "$LOG"
  sleep 20
done
