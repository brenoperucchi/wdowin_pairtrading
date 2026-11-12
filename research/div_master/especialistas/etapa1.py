# -*- coding: utf-8 -*-
"""
Etapa 1 — contagens do módulo unificado em jan–jul/2026 (IS). Sem P&L, sem retorno à frente.
Mede por ativo × motor × especialista: candidatos/dia, gatilhos/dia, % que dispara, subcasos, atraso,
descartes (confirmação depois de j+3), super-confluência, duplicados, balde das 09h e aprovação do item 5.
Uso: python etapa1.py   → results/etapa1.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modulo as M  # noqa: E402
from research.div_wall.data import IS_END, load_asset  # noqa: E402


def pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def main():
    res = {}
    for a in ("WIN", "WDO"):
        data = {d: v for d, v in load_asset(a, "M5").items() if d <= IS_END}
        nd = len(data)
        acc = {e: dict(c=[], t=[], disc=[]) for e in M.ENGINES}
        for d in sorted(data):
            bars, walls, _ = data[d]
            _, R = M.run_day(a, bars, walls)
            for e in M.ENGINES:
                for x in R[e]["cands"]:
                    acc[e]["c"].append(dict(x, date=d))
                for x in R[e]["trig"]:
                    acc[e]["t"].append(dict(x, date=d))
                acc[e]["disc"] += R[e]["discard"]
        res[a] = {"days": nd}
        print(f"\n===== {a} · {nd} pregões jan–jul =====")
        for e in M.ENGINES:
            C, T, D = acc[e]["c"], acc[e]["t"], acc[e]["disc"]
            wall = [c for c in C if c["c1"] is not None or c["c2"] is not None]
            day = [c for c in C if c["day"] is not None]
            both = [c for c in wall if c["day"] is not None]
            r = dict(cands=len(C), cands_day=round(len(C) / nd, 2), wall=len(wall), extremo=len(day), both=len(both),
                     micro_ok=pct(sum(c["micro"] for c in C), len(C)),
                     src=dict(Counter(c.get("src", "-") for c in C)), esp={})
            print(f"\n[{e}] candidatos {len(C)} ({r['cands_day']}/dia) · âncora WALL {len(wall)} · EXTREMO {len(day)} "
                  f"· as duas {len(both)} · item 5 aprova {r['micro_ok']}%" + (f" · origem {r['src']}" if e == "v3.1" else ""))
            for esp, base in (("WALL", wall), ("EXTREMO", day)):
                tt = [x for x in T if x["esp"] == esp]
                dd = [x for x in D if x["esp"] == esp]
                lag = Counter(x["lag"] for x in tt)
                late = sum(1 for x in tt if M.hm(x["time"]) > M.hm("17:00"))
                h9 = sum(1 for x in tt if x["time"] < "10:00")
                s = dict(base=len(base), trig=len(tt), trig_day=round(len(tt) / nd, 2), fired=pct(len(tt), len(base)),
                         discard=len(dd), discard_pct=pct(len(dd), len(base)), sub=dict(Counter(x["sub"] for x in tt)),
                         lag={k: lag[k] for k in sorted(lag)}, super=sum(x["super"] for x in tt),
                         dup=sum(x["dup"] for x in tt), after_17h=late, h09=h9, h09_pct=pct(h9, len(tt)),
                         buy=sum(1 for x in tt if x["dir"] == 1), micro_ok=pct(sum(x["micro"] for x in tt), len(tt)))
                r["esp"][esp] = s
                print(f"   {esp:8s} base {s['base']:4d} → gatilhos {s['trig']:4d} ({s['trig_day']}/dia, {s['fired']}% dispara) "
                      f"· descartes {s['discard']} ({s['discard_pct']}%) · sub {s['sub']} · atraso {s['lag']} "
                      f"· super {s['super']} · dup {s['dup']} · 09h {s['h09_pct']}% · após 17h {late} · compras {s['buy']}")
            uniq = sum(1 for x in T if not x["dup"])
            r["combined_entries"], r["combined_day"] = uniq, round(uniq / nd, 2)
            print(f"   carteira combinada (deduplicada): {uniq} entradas ({r['combined_day']}/dia)")
            res[a][e] = r
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(res, open(os.path.join(HERE, "results", "etapa1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
