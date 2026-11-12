"""
Relatório pós-OOS (sem nova escolha): entrada direta x Sniper 5176 corrigido x os dois juntos.
Juntos: se o Sniper tem trade da mesma divergência (entrada 1–3 barras depois do sinal, mesma direção), fica o do Sniper.
Uso: python -m research.sniper_direct.compare <trades_5176_B.csv>
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPLIT = "2026-07-31"


def m2(t):
    h, m = map(int, str(t).split(":")[:2])
    return h * 60 + m


def stats(df):
    if len(df) == 0:
        return dict(ops=0)
    df = df.sort_values(["date", "ent", "ext"])
    p = df.brl.values
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = df.groupby(df.date.str[:7]).brl.sum()
    return dict(ops=len(df), wr=round(100 * (p > 0).mean(), 1), pf=round(g / l, 2), net=round(eq[-1]), dd=round(dd),
                rdd=round(eq[-1] / dd, 2) if dd else 99, meses=f"{(m > 0).sum()}/{len(m)}", pior_mes=round(m.min()))


def rep(name, df):
    print(f"{name}\n  total {stats(df)}\n  IS    {stats(df[df.date <= SPLIT])}\n  OOS   {stats(df[df.date > SPLIT])}")


def main(path5176):
    T = pd.read_csv(os.path.join(ROOT, "research", "sniper_direct", "results", "oos_trades.csv"))
    T = T[T.escolha == "escolha"]
    d = pd.DataFrame(dict(sys="direta", asset=T.asset, date=T.date, time=T.time, direction=T.direction, brl=T.brl,
                          ent=T.time.map(m2), ext=T.exit_tm, sig=T.sig_time.map(m2)))
    s = pd.read_csv(path5176)
    s["sys"] = "5176"
    rep("ENTRADA DIRETA", d)
    rep("SNIPER 5176 corrigido", s)
    # mesma divergência: Sniper entra 5–15 min depois do sinal, mesma direção
    keep = []
    sk = {(r.asset, r.date, r.direction): [] for r in s.itertuples()}
    for r in s.itertuples():
        sk[(r.asset, r.date, r.direction)].append(r.ent)
    for r in d.itertuples():
        ents = sk.get((r.asset, r.date, r.direction), [])
        keep.append(not any(5 <= e - r.sig <= 15 for e in ents))
    d2 = d[np.array(keep)]
    print(f"\ndivergências da entrada direta que o Sniper já opera: {len(d) - len(d2)} de {len(d)}")
    rep("JUNTOS (Sniper + entrada direta nas divergências sem trade do Sniper)", pd.concat([s, d2]))
    for a in ("WIN", "WDO"):
        rep(f"  JUNTOS só {a}", pd.concat([s[s.asset == a], d2[d2.asset == a]]))
    J = pd.concat([s, d2])
    mm = J.groupby([J.date.str[:7], "sys"]).brl.sum().unstack(fill_value=0).round()
    mm["juntos"] = mm.sum(axis=1)
    print(mm)
    a = d2.groupby("date").brl.sum()
    b = s.groupby("date").brl.sum()
    idx = sorted(set(a.index) | set(b.index))
    print("correlação diária direta x Sniper:", round(np.corrcoef(a.reindex(idx, fill_value=0), b.reindex(idx, fill_value=0))[0, 1], 2))


if __name__ == "__main__":
    main(sys.argv[1])
