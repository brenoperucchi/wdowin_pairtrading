# -*- coding: utf-8 -*-
"""
O especialista V3.2 funcionaria no dólar? (pergunta do usuário em 12/11/2026)
Mesma regra do ESP_DIV_V22_WIN (motor v3.2 sem abertura, âncora Wall/MidWall ou extremo do dia, gatilho Opção C,
sem super-confluência, 1º/2º gatilho do dia, 10:00–15:55, contexto NWE50, um trade por vez, sem alvo, BE, 12 barras)
aplicada ao WDO. A saída do WIN (SL 200 · BE 180→20) é convertida pela razão das amplitudes M5 WIN/WDO, e também
uma pequena grade em volta. 1 contrato WDO, custo 0,5 pt, stop 1 tick pior. Execução tick a tick em M1.
Uso: python research/div_master/v32/especialista_wdo.py
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "research", "div_master", "especialistas")]
import numpy as np
import pandas as pd
import modulo as M, bt

IS_END = "2026-07-31"


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0, net=0, dd=0, rdd=0, rdd_is=0, rdd_oos=0, meses="0/0")
    R = pd.DataFrame(rows, columns=["date", "tm", "xt", "brl"]).sort_values(["date", "xt", "tm"])
    p = R.brl.values

    def rdd(q):
        if len(q) == 0:
            return 0.0, 0.0, 0.0
        eq = np.cumsum(q)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
        return float(eq[-1]), dd, (float(eq[-1]) / dd if dd else 99.0)

    net, dd, r = rdd(p)
    isv = (R.date <= IS_END).values
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    mon = pd.Series(p).groupby(R.date.str[:7].values).sum()
    return dict(ops=len(p), wr=round(100 * (p > 0).mean(), 1), pf=round(g / l, 2) if l else 99.0, net=round(net),
                dd=round(dd), rdd=round(r, 2), rdd_is=round(rdd(p[isv])[2], 2), rdd_oos=round(rdd(p[~isv])[2], 2),
                meses=f"{int((mon > 0).sum())}/{len(mon)}")


def main():
    M.V32 = dict(M.V32_PROD)
    rng = {}
    for a in ("WIN", "WDO"):
        m5 = pd.read_csv(os.path.join(bt.RATES, f"mt5_{a}_N_M5.csv"), parse_dates=["t"])
        rng[a] = float((m5.high - m5.low).median())
    k = rng["WDO"] / rng["WIN"]
    print(f"amplitude mediana M5: WIN {rng['WIN']:.0f} pts · WDO {rng['WDO']:.2f} pts · razão {k:.4f}")
    DS = bt.market("WDO")
    S = bt.simulate("WDO", bt.signals("WDO", "v3.2"), DS, exits=())
    print(f"gatilhos Opção C no WDO: {len(S)} · com barra de entrada: {int(S.ok.sum())}")
    x = bt.X["WDO"]

    def run(T, sl, be_t, be_l, tmax):
        rows, last = [], {}
        for r in T.sort_values(["date", "tm"]).itertuples():
            if r.tm <= last.get(r.date, -1):
                continue
            D = DS[r.date]
            pts, t = bt.sim(*bt._args(D), D["u30"], int(r.e), r.ep, r.dir, sl, r.ep + r.dir * 1e9, False, 0.0, 0.0,
                            0.0, be_t, be_l, tmax, x["tick"])
            last[r.date] = t
            rows.append((r.date, r.tm, t, (pts - x["cost"]) * x["brl"]))
        return rows

    full = S[S.ok & ~S.super & (S.seq <= 1) & (S.tm >= 600) & (S.tm < 960) & (S.ext50 > -0.5) & (S.slope50 > -0.5)]
    loose = S[S.ok]
    conv = (round(200 * k * 2) / 2, round(180 * k * 2) / 2, max(0.5, round(20 * k * 2) / 2))
    print(f"saída do WIN convertida: SL {conv[0]} · BE {conv[1]}→{conv[2]} · 12 barras")
    for name, T in (("regra do especialista", full), ("todos os gatilhos", loose)):
        print(f"\n{name}: {len(T)} sinais")
        st = stats(run(T, conv[0], conv[1], conv[2], 12))
        print(f"   convertida      {st}")
        res = []
        for sl, be_t, tmax in itertools.product((4.0, 6.0, 8.0, 10.0, 12.0), (3.0, 4.0, 6.0, 8.0), (12, 24)):
            st = stats(run(T, sl, be_t, 0.5, tmax))
            res.append(dict(sl=sl, be=be_t, tmax=tmax, **st))
        Rr = pd.DataFrame(res)
        print(f"   grade ({len(Rr)}): Ret/DD mediano {Rr.rdd.median():.2f} · positivas {int((Rr.net > 0).sum())}/{len(Rr)}")
        print(Rr.sort_values("rdd_is", ascending=False).head(5).to_string(index=False))


if __name__ == "__main__":
    main()
