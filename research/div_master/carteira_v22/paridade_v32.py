# -*- coding: utf-8 -*-
"""
Paridade do motor da carteira 5176 a partir de 12/11/2026: v3.2 sem módulo de abertura (modulo.V32_PROD).
  1. Especialista: core/especialista_v22.run × pesquisa (v32/teste.py, variante "v3.2 sem módulo de abertura").
  2. Causalidade do especialista: o dia visto barra a barra (como ao vivo) não muda trades já fechados.
  3. Sniper: core/div_engines_view.sniper_divs barra a barra × no dia inteiro (sinal conhecido na confirmação),
     e × frente1.engine_map("v3.2") usado no backtest.
Uso: python research/div_master/carteira_v22/paridade_v32.py
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "frente1"), HERE]
import modulo as M, bt, robust as R
import motores as F1
from core import especialista_v22 as E
from core.div_engines_view import sniper_divs
from paridade_especialista import day_inputs
from research.div_wall.data import load_asset


def research_esp(DS):
    M.V32 = dict(M.V32_PROD)
    S = bt.simulate("WIN", bt.signals("WIN", "v3.2"), DS, exits=())
    T = R.run_exit(S, DS)
    m = T.ok & ~T.super & (T.seq <= 1) & (T.tm >= 600) & (T.tm < 960) & (T.ext50 > -0.5) & (T.slope50 > -0.5)
    q = bt.mgmt(T[m & T[R.COL].notna()].sort_values(["date", "tm"]), R.COL, R.XT, "UM_POR_VEZ")
    return sorted((r.date, r.time_in, f"{int(r.xt_X) // 60:02d}:{int(r.xt_X) % 60:02d}", round(2.0 * float(r.pnl_X), 2))
                  for r in q.itertuples())


def main(live_days=15, sniper_days=25):
    DS = bt.market("WIN")
    data = load_asset("WIN", "M5")
    ref = research_esp(DS)
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
    print(f"[1] especialista · pesquisa {len(ref)} tr R$ {sum(r[3] for r in ref):.0f} · core {len(got)} tr "
          f"R$ {sum(r[3] for r in got):.0f} · iguais {len(a & b)}")
    print("    só na pesquisa:", sorted(a - b)[:8])
    print("    só no core:", sorted(b - a)[:8])

    bad = 0
    days = [d for d in sorted(per_day) if per_day[d]][-live_days:]
    for d in days:
        fb, walls, ex = day_inputs(DS, data, d)
        full = {(t["time"], t["exit_time"], t["brl_1c"]) for t in per_day[d]}
        for n in range(5, len(fb) + 1):
            tmax = fb[n - 1]["time"]
            for t in E.run(fb[:n], walls, [x for x in ex if x["time"] <= tmax], is_live=True):
                if not t["is_open"] and (t["time"], t["exit_time"], t["brl_1c"]) not in full:
                    bad += 1
                    print("    diverge", d, tmax, t["time"], t["exit_time"], t["brl_1c"])
                    break
    print(f"[2] especialista barra a barra em {len(days)} pregões: {bad} divergências")

    for asset in ("WIN", "WDO"):
        dat = load_asset(asset, "M5")
        mp = F1.engine_map(asset, "v3.2", "conf", False)
        bad_c = bad_m = 0
        ds = sorted(dat)[-sniper_days:]
        for d in ds:
            fb = M.compute_flow([dict(x) for x in dat[d][0]], asset)
            full = sorted(set(sniper_divs(asset, fb)))
            bt_ = sorted(set((int(s[0]), int(s[1])) for s in mp.get(d, [])))
            bad_m += full != bt_
            for n in range(5, len(fb) + 1):
                part = set(sniper_divs(asset, fb[:n]))
                exp = {x for x in full if x[0] <= n - 1}
                if part != exp:
                    bad_c += 1
                    print("    sniper diverge", asset, d, fb[n - 1]["time"], sorted(part ^ exp)[:4])
                    break
        print(f"[3] Sniper {asset}: {len(ds)} pregões · barra a barra ≠ dia inteiro: {bad_c} · core ≠ backtest: {bad_m}")


if __name__ == "__main__":
    main()
