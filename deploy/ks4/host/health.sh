#!/usr/bin/env bash
# Resumo de saude do Magic Walls no ks4. Somente leitura. Uso: ssh <usuario>@<host> /home/app/magicwalls-ops/health.sh
export XDG_RUNTIME_DIR=/run/user/$(id -u)
echo "== $(date "+%F %T %Z") (BRT = UTC-3)"
echo "-- units"
for u in mt5-a profit-wine magicwalls-cloud magicwalls-server magicwalls-publisher; do printf "%-26s %s\n" "$u" "$(systemctl --user is-active $u.service)"; done
for t in magicwalls-sync-native magicwalls-gex; do printf "%-26s %s | proximo: %s\n" "$t.timer" "$(systemctl --user is-active $t.timer)" "$(systemctl --user list-timers $t.timer --no-legend | awk '{print $1,$2,$3}')"; done
echo "-- arquivos nativos do Profit (origem) x copia no mt5-a"
python3 - <<'PY'
import os, struct, glob, time, datetime
SRC = "/home/app/profit-wine/prefix/drive_c/users/mt5/AppData/Roaming/Nelogica/Scalper/database/assets"
DST = "/home/app/mt5-wine-lab/prefix-a/drive_c/users/mt5/AppData/Roaming/Nelogica/Scalper/database/assets"
for f in sorted(glob.glob(SRC + "/W*/*_0_1_1_1_0_20*.trd")):
    name = os.path.basename(f); sz = os.path.getsize(f); age = int(time.time() - os.path.getmtime(f))
    last = ""
    if sz >= 45:
        with open(f, "rb") as fh:
            fh.seek((sz // 45 - 1) * 45); rec = fh.read(45)
        dt, tr, px, qty = struct.unpack("<dIdQ", rec[:28])
        last = (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=dt)).strftime("%d/%m %H:%M:%S") + " px=%.1f negocio#%d" % (px, tr // 10)
    cp = f.replace(SRC, DST); csz = os.path.getsize(cp) if os.path.exists(cp) else -1
    ok = "OK" if csz == sz else str(csz)
    print("%-34s %8.1fMB  gravado ha %6ds  ultimo trade: %s  copia=%s" % (name[:34], sz / 1e6, age, last, ok))
for f in sorted(glob.glob(SRC + "/W*/*_1_1_1_1_0_2026.min")):
    print("%-34s .min mtime ha %ds" % (os.path.basename(f)[:34], int(time.time() - os.path.getmtime(f))))
PY
echo "-- rtdmw (cliente RTD unico: minuto + Times and Trades)"
python3 - <<'PY'
import json
try:
    d = json.load(open("/home/app/rtd-csv/status.json"))
    print("batches", d["batches"])
    for k, v in d["assets"].items():
        print(k, v["hor"], "lines", v["lines"], "gaps", v["gaps"], "resets", v["resets"], "last_written", v["last_written"])
    for k, v in d.get("tt", {}).items():
        print("T&T", k, v["asset"], "rows", v["rows"], "trades", v["trades"], "neg_delta", v["neg_delta"], "cobertura", v["coverage"], "gaps", v["gaps"])
except Exception as e:
    print("sem status:", e)
PY
echo "-- memoria dos containers"; podman stats --no-stream --format "{{.Name}} {{.MemUsage}} {{.CPUPerc}}" 2>/dev/null
echo "-- server.py: ultimos avisos"; podman exec mt5-a bash -c "grep -i -E 'setups_live|error|traceback|exception' /home/mt5/.mt5/drive_c/magicwalls/server.log | tail -3 | cut -c1-220" 2>/dev/null
echo "-- publisher.log (ultimas 3)"; podman exec mt5-a bash -c "tail -3 /home/mt5/.mt5/drive_c/magicwalls/publisher.log | cut -c1-200" 2>/dev/null
echo "-- ultimo GEX"; journalctl --user -u magicwalls-gex.service --no-pager 2>/dev/null | grep -E "GEX:|FALHOU" | tail -2 | cut -c1-200
