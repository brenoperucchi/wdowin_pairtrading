# -*- coding: utf-8 -*-
"""
Paridade: core/especialista_v22.run (usado no histórico e ao vivo) × pesquisa (v22/teste.py, variante A+B8 até 10:00).
Sinal nas barras do Profit (dataset div_wall_v1 + compute_flow), execução nas barras MT5 (bt.market), como no BT.
Também roda a versão "barra a barra" (como o motor ao vivo vê o dia) para conferir causalidade.
Uso: python research/div_master/carteira_v22/paridade_especialista.py
"""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas")]
import bt, modulo as M
from core import especialista_v22 as E
from research.div_wall.data import load_asset


def exec_bars(D):
    n = len(D["o5"])
    out = []
    for k in range(n):
        out.append(dict(time=f"{int(D['tm5'][k]) // 60:02d}:{int(D['tm5'][k]) % 60:02d}", open=float(D["o5"][k]),
                        high=float(D["h5"][k]), low=float(D["l5"][k]), close=float(D["c5"][k]),
                        nwe50_line=float(D["c50"][k + 1]) if k + 1 < n else 0.0,
                        nwe50_upper=float(D["u50"][k + 1]) if k + 1 < n else 0.0))
    return out


def day_inputs(DS, data, d):
    bars, walls, _ = data[d]
    fb = M.compute_flow([dict(b) for b in bars], "WIN")
    return fb, walls, exec_bars(DS[d])


def main(check_live_days=8):
    ref = json.load(open(os.path.join(DM, "v22", "results", "trades.json")))["A+B8 até 10:00|esp"]
    ref = sorted((r[0], r[1], r[2], round(r[3], 2)) for r in ref)
    DS = bt.market("WIN")
    data = load_asset("WIN", "M5")
    got, per_day = [], {}
    for d in sorted(data):
        if d > bt.END or d not in DS:
            continue
        fb, walls, ex = day_inputs(DS, data, d)
        trs = E.run(fb, walls, ex)
        per_day[d] = trs
        got += [(d, t["time"], t["exit_time"], round(t["brl_1c"], 2)) for t in trs]
    got = sorted(got)
    a, b = set(ref), set(got)
    print(f"pesquisa: {len(ref)} trades · core: {len(got)} trades · iguais: {len(a & b)}")
    print("só na pesquisa:", sorted(a - b)[:8])
    print("só no core:", sorted(b - a)[:8])
    print(f"R$ pesquisa {sum(r[3] for r in ref):.0f} · R$ core {sum(r[3] for r in got):.0f}")
    # causalidade: o dia visto barra a barra (como ao vivo) não pode mudar trades já fechados
    bad = 0
    days = [d for d in sorted(per_day) if per_day[d]][:check_live_days]
    for d in days:
        fb, walls, ex = day_inputs(DS, data, d)
        full = {(t["time"], t["exit_time"], t["brl_1c"]) for t in per_day[d]}
        for n in range(5, len(fb) + 1):
            tmax = fb[n - 1]["time"]
            ex_n = [b for b in ex if b["time"] <= tmax]
            part = E.run(fb[:n], walls, ex_n, is_live=True)
            for t in part:
                if not t["is_open"] and (t["time"], t["exit_time"], t["brl_1c"]) not in full:
                    bad += 1
                    print("  diverge", d, tmax, t["time"], t["exit_time"], t["brl_1c"])
                    break
    print(f"barra a barra em {len(days)} pregões: {bad} divergências")


if __name__ == "__main__":
    main()
