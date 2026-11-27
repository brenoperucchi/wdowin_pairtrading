#!/usr/bin/env python3
"""Compara os sinais registrados AO VIVO (signals-recorder.py) com o recalculo final do dia. Somente leitura.

Uso: signals-report.py [AAAA-MM-DD]   (padrao: hoje, horario de Brasilia)
Para cada ativo informa: sinais vistos ao vivo, sinais do recalculo, quais sumiram, quais so apareceram depois,
quais mudaram de identidade (horario, direcao, entrada, stop) e a defasagem entre a hora da barra e a primeira vez
que o sinal apareceu ao vivo. Campos de saida (exit_*) sao informados a parte, porque so se resolvem depois.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
OUT = os.environ.get("MW_SIGNALS_OUT", os.path.expanduser("~/signals-live"))
IDENT = ("time", "direction", "entry_price", "stop_price")
OUTCOME = ("exit_time", "exit_price", "exit_reason")


def recalculated(day):
    code = ("import urllib.request;print(urllib.request.urlopen("
            "'http://127.0.0.1:8080/api/compass/etapa1?lite=1&date_str=%s',timeout=120).read().decode())" % day)
    env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/%d" % os.getuid())
    r = subprocess.run(["podman", "exec", "mt5-a", "python3", "-c", code], capture_output=True, text=True,
                       timeout=180, env=env)
    if r.returncode != 0:
        raise SystemExit("falha ao buscar o recalculo: " + r.stderr[-200:])
    return json.loads(r.stdout)


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(timezone.utc).astimezone(BRT).strftime("%Y-%m-%d")
    path = os.path.join(OUT, day + ".jsonl")
    if not os.path.exists(path):
        raise SystemExit("sem registro ao vivo em " + path)
    live = {}     # asset -> id -> {"first": ts_brt, "first_sig": sinal, "last_sig": sinal}
    hb = errs = snaps = 0
    first_ts = last_ts = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            first_ts = first_ts or d["ts_brt"]
            last_ts = d["ts_brt"]
            if d["k"] == "hb":
                hb += 1
            elif d["k"] == "erro":
                errs += 1
            elif d["k"] == "snap":
                snaps += 1
                m = live.setdefault(d["asset"], {})
                for s in d["signals"]:
                    e = m.setdefault(s["id"], {"first": d["ts_brt"], "first_sig": s})
                    e["last_sig"] = s
    print("registro: %s a %s | snapshots=%d heartbeats=%d erros=%d" % (first_ts, last_ts, snaps, hb, errs))
    final = recalculated(day)
    for a in ("WIN", "WDO"):
        fin = {s["id"]: s for s in ((final.get(a) or {}).get("caminho_a") or {}).get("signals_log") or []}
        lv = live.get(a, {})
        gone = sorted(set(lv) - set(fin))
        late = sorted(set(fin) - set(lv))
        both = sorted(set(lv) & set(fin))
        print("\n== %s: ao vivo=%d recalculo=%d | em ambos=%d" % (a, len(lv), len(fin), len(both)))
        print("  vistos ao vivo e SUMIDOS no recalculo: %s" % (gone or "nenhum"))
        print("  so no recalculo (nunca vistos ao vivo): %s" % (late or "nenhum"))
        changed = []
        for i in both:
            diff = {k: (lv[i]["last_sig"].get(k), fin[i].get(k)) for k in IDENT
                    if lv[i]["last_sig"].get(k) != fin[i].get(k)}
            if diff:
                changed.append((i, diff))
        print("  identidade mudou (horario, direcao, entrada, stop): %s" % (changed or "nenhum"))
        out_changed = [(i, {k: (lv[i]["last_sig"].get(k), fin[i].get(k)) for k in OUTCOME
                            if lv[i]["last_sig"].get(k) != fin[i].get(k)}) for i in both]
        out_changed = [(i, d) for i, d in out_changed if d]
        print("  resultado (saida) resolvido depois do ultimo registro: %d sinais" % len(out_changed))
        for i in both:
            bar_time = fin[i].get("time")
            seen = lv[i]["first"][11:16]
            print("    %s barra %s vista ao vivo pela 1a vez as %s" % (i, bar_time, seen))


if __name__ == "__main__":
    main()
