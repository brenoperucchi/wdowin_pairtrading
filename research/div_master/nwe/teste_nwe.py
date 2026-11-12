# -*- coding: utf-8 -*-
"""
Troca da NWE30 pela NWE100 (pedido de 12/11/2026). Motor de divergência v2.2 (V22_ABERTURA) nas duas estratégias.

Onde a NWE entra hoje:
  - Sniper WIN, lote 1: alvo na banda oposta da NWE30 (30, bw 3, mult 1,6), limitado a 260–750 pts;
  - especialista: filtros de contexto ext / slope na NWE50 (50, bw 8, mult 3).
Variantes: NWE30 (atual) · NWE100 mult 3 (100, 8, 3 — a do UpdateNWE do MT5) · NWE100 mult 1,8 (100, 8, 1,8).
Uso: python research/div_master/nwe/teste_nwe.py → research/div_master/nwe/results/
"""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "frente1"), os.path.join(DM, "v22")]
import numpy as np, pandas as pd
import research.flow_window_asg.inject_unified_div_opt2 as S
from research.discover_gex_nwe_setups import compute_nwe_series
from research.mt5_loader import get_mt5_rates
import modulo as M, bt, robust as R
import motores as F1

OUT = os.path.join(HERE, "results")
IS_END = "2026-07-31"
ENV = {"NWE30 (30·3·1,6)": (30, 3.0, 1.6), "NWE100 (100·8·3)": (100, 8.0, 3.0), "NWE100 (100·8·1,8)": (100, 8.0, 1.8)}
FILT = {"NWE50 (50·8·3)": (50, 8.0, 3.0), "NWE100 (100·8·3)": (100, 8.0, 3.0), "NWE100 (100·8·1,8)": (100, 8.0, 1.8)}
_ORIG_LOADER = S.load_mt5_win_bars_and_nwe30


def loader_with(env):
    """Mesmo carregador do Sniper (barras MT5 WIN$N 09:00–17:55) com outro envelope nas chaves n30_*."""
    def f():
        bars_by_day, _ = _ORIG_LOADER()
        df = get_mt5_rates("WIN$N", "M5").copy()
        df["session_date"] = df["t"].dt.strftime("%Y-%m-%d")
        df["t_min"] = df["t"].dt.hour * 60 + df["t"].dt.minute
        df = df[(df["t_min"] >= 540) & (df["t_min"] <= 1075)].reset_index(drop=True)
        c, u, l = compute_nwe_series(df["close"].values.astype(float), *env)[:3]
        df["n30_c"], df["n30_u"], df["n30_l"] = c, u, l
        out, last = {}, None
        for d, g in df.groupby("session_date", sort=True):
            out[str(d)] = {"n30_c": g["n30_c"].values.astype(float), "n30_u": g["n30_u"].values.astype(float),
                           "n30_l": g["n30_l"].values.astype(float), "prev": last}
            last = {k: float(g[k].iloc[-1]) for k in ("n30_c", "n30_u", "n30_l")}
        return bars_by_day, out
    return f


def sniper_rows(pool, vis, engine):
    trs = []
    for a in ("WIN", "WDO"):
        mp = vis[a] if engine == "B" else F1.engine_map(a, "v2.2", "conf", False)
        trs += F1.sniper_filter(pool[a], mp, ("tol", 2), a)
    return F1.rows_sniper(trs)


def esp_rows(filt):
    bt.N50 = filt
    DS = bt.market("WIN")
    T = R.run_exit(bt.simulate("WIN", bt.signals("WIN", "v2.2"), DS, exits=()), DS)
    m = T.ok & ~T.super & (T.seq <= 1) & (T.tm >= 600) & (T.tm < 960) & (T.ext50 > -0.5) & (T.slope50 > -0.5)
    q = bt.mgmt(T[m & T[R.COL].notna()].sort_values(["date", "tm"]), R.COL, R.XT, "UM_POR_VEZ")
    bt.N50 = (50, 8.0, 3.0)
    return [(r.date, r.time_in, f"{int(r.xt_X) // 60:02d}:{int(r.xt_X) % 60:02d}", 2.0 * float(r.pnl_X)) for r in q.itertuples()]


def summ(rows):
    per = F1.by_period(rows)
    isr = F1.stats_brl([x for x in rows if x[0] <= IS_END])["rdd"]
    c = per["completo"]
    return dict(trades=c["ops"], pf=c["pf"], lucro=c["net"], dd=c["dd"], rdd=c["rdd"], rdd_jan_jul=isr, meses=c["meses"],
                pf_partes="/".join(f"{per[p]['pf']:.2f}" for p in ("jan–abr", "mai–jul", "ago–nov")))


def main():
    os.makedirs(OUT, exist_ok=True)
    M.V22 = dict(M.V22, **M.V22_ABERTURA)
    rows, keep = [], {}
    for name, env in ENV.items():
        S.load_mt5_win_bars_and_nwe30 = loader_with(env)
        pool, vis = F1.sniper_pool()
        for eng in ("B", "v2.2"):
            rr = sniper_rows(pool, vis, eng)
            keep[("snp", eng, name)] = rr
            win_only = [x for x, t in zip(rr, rr)]
            rows.append(dict(parte="Sniper (WIN+WDO)", motor="atual (B)" if eng == "B" else "v2.2", nwe=name, **summ(rr)))
        print("Sniper ok:", name, flush=True)
    S.load_mt5_win_bars_and_nwe30 = _ORIG_LOADER
    for name, filt in FILT.items():
        rr = esp_rows(filt)
        keep[("esp", name)] = rr
        rows.append(dict(parte="Especialista (WIN 2c)", motor="v2.2", nwe=name, **summ(rr)))
        print("Especialista ok:", name, flush=True)
    for sn in ENV:
        for ef in FILT:
            rr = keep[("snp", "v2.2", sn)] + keep[("esp", ef)]
            rows.append(dict(parte="Carteira v2.2", motor="v2.2", nwe=f"alvo Sniper {sn} · filtro esp. {ef}", **summ(rr)))
    Rdf = pd.DataFrame(rows)
    Rdf.to_csv(os.path.join(OUT, "nwe.csv"), index=False)
    json.dump({"|".join(k): v for k, v in keep.items()}, open(os.path.join(OUT, "trades.json"), "w"))
    pd.set_option("display.width", 260)
    print(Rdf.to_string(index=False))


if __name__ == "__main__":
    main()
