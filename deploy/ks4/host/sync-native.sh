#!/usr/bin/env bash
# Copia os arquivos nativos do Profit (.min/.trd) para dentro do prefixo do mt5-a, onde roda o server.py.
# Somente leitura na origem. Pastas: contratos WIN/WDO/DOL/IND e DI1.
set -euo pipefail
SRC=/home/app/profit-wine/prefix/drive_c/users/mt5/AppData/Roaming/Nelogica
DST=/home/app/mt5-wine-lab/prefix-a/drive_c/users/mt5/AppData/Roaming/Nelogica
for app in Scalper Profit; do
  [ -d "$SRC/$app/database/assets" ] || continue
  mkdir -p "$DST/$app/database/assets"
  # .min: arquivos pequenos e regravados por inteiro
  rsync -a --inplace --prune-empty-dirs \
    --include="*/" --include="WIN*/*.min" --include="WDO*/*.min" --include="DI1*/*.min" --exclude="*" \
    "$SRC/$app/database/assets/" "$DST/$app/database/assets/"
  # .trd: arquivo do dia cresce so no fim, entao envia apenas o final (append)
  rsync -a --append --prune-empty-dirs \
    --include="*/" --include="WIN*/*.trd" --include="WDO*/*.trd" --exclude="*" \
    "$SRC/$app/database/assets/" "$DST/$app/database/assets/"
done

# Times & Trades ao vivo do rtdmw (CSV por negocio, cresce so no fim): mesma logica do .trd, para dentro do mt5-a.
RTD_SRC=/home/app/profit-wine/prefix/rtd-csv
if [ -d "$RTD_SRC" ]; then
  mkdir -p "$DST/rtd-csv"
  rsync -a --append --include="tt_*.csv" --exclude="*" "$RTD_SRC/" "$DST/rtd-csv/"
fi
