# -*- coding: utf-8 -*-
"""
WDO — ordem LIMITE na própria Wall (o estudo de respeito mostrou 58–60% contra ~53% do placebo).
Regra: no 1º toque do dia de cada Wall/MidWall (o preço vem de um lado; a barra anterior fechou do outro lado do
nível), compra/venda limite NO nível a favor do respeito; alvo +TP (limite), stop −SL, saída no tempo; 1 contrato,
custo 0,5 pt, stop 1 tick pior. Execução tick a tick em M1 (o preenchimento é no primeiro tick que toca o nível;
só os ticks seguintes contam para alvo/stop). Um trade por vez. Mesma regra nos níveis placebo (10 sorteios).
Variante "fila": só preenche se o preço passar 1 tick além do nível (limite no fim da fila).
Uso: python research/div_master/wdo_ima/limite.py
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numba as nb
import numpy as np
import pandas as pd
import teste as T
import bt
from research.div_wall.data import load_asset

TICK, COST, BRL = 0.5, 0.5, 10.0


@nb.njit(cache=True)
def run_day(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, levels, tp, sl, tmax, queue, t_lo, t_hi):
    """Devolve (n, soma em pts líquidos, lista de pts) para o dia."""
    n5 = len(o5)
    used = np.zeros(len(levels), np.bool_)
    res = []
    busy_until = -1
    for t in range(1, n5):
        if t <= busy_until or tm5[t] < t_lo or tm5[t] > t_hi:
            continue
        for li in range(len(levels)):
            L = levels[li]
            if used[li]:
                continue
            if not (l5[t] <= L <= h5[t]):
                continue
            used[li] = True
            side = 1 if c5[t - 1] > L else -1        # veio de cima → compra (respeito); de baixo → venda
            d = side
            # ticks da barra t em diante; procura o preenchimento
            filled = False
            ep = L
            stop = L - d * sl
            tgt = L + d * tp
            done = False
            pts = 0.0
            for k in range(t, n5):
                if filled and (k - t > tmax or tm5[k] >= 1045):
                    pts = (o5[k] - ep) * d
                    busy_until = k
                    done = True
                    break
                nt = nn[k] if fb[k] == 0 else 4
                for j in range(nt):
                    if fb[k] == 0:
                        p = px[off[k] + j]
                    else:
                        p = o5[k] if j == 0 else ((l5[k] if d == 1 else h5[k]) if j == 1 else ((h5[k] if d == 1 else l5[k]) if j == 2 else c5[k]))
                    if not filled:
                        if (L - p) * d >= (TICK if queue else 0.0):
                            filled = True
                            if (L - p) * d > (TICK if queue else 0.0) and j == 0:
                                ep = p                    # gap além do nível: preenche na abertura (melhor)
                            stop = ep - d * sl
                            tgt = ep + d * tp
                        continue
                    if (p - stop) * d <= 0:
                        pts = (stop - d * TICK - ep) * d
                        done = True
                        break
                    if (p - tgt) * d >= 0:
                        pts = (tgt - ep) * d
                        done = True
                        break
                if done:
                    busy_until = k
                    break
                if not filled and k > t:
                    break                                  # não preencheu na barra do toque: cancela
            if filled:
                if not done:
                    pts = (c5[n5 - 1] - ep) * d
                    busy_until = n5
                res.append(pts - COST)
            break
    return res


def evaluate(DS, lvmap, tp, sl, tmax, queue):
    rows = []
    for d, D in DS.items():
        lv = lvmap.get(d)
        if not lv or d > bt.END:
            continue
        r = run_day(*bt._args(D), np.array(lv, float), tp, sl, tmax, queue, 555, 990)
        rows += [(d, x * BRL) for x in r]
    if not rows:
        return dict(ops=0, pf=0.0, net=0, rdd=0.0, pf_is=0.0, pf_oos=0.0)
    R = pd.DataFrame(rows, columns=["date", "brl"])
    p = R.brl.values
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    isv = (R.date <= T.IS_END).values

    def pf(q):
        g, l_ = q[q > 0].sum(), -q[q < 0].sum()
        return round(g / l_, 2) if l_ else 99.0

    return dict(ops=len(p), pf=pf(p), net=round(eq[-1]), dd=round(dd), rdd=round(eq[-1] / dd, 2) if dd else 99.0,
                pf_is=pf(p[isv]), pf_oos=pf(p[~isv]), wr=round(100 * (p > 0).mean(), 1))


def main():
    data = load_asset("WDO", "M5")
    DS = bt.market("WDO")
    real = {d: T.day_levels(v[1]) for d, v in data.items() if d in DS}
    plac = [{d: T.placebo(lv, np.random.default_rng(1000 * s + i)) for i, (d, lv) in enumerate(sorted(real.items()))}
            for s in range(10)]
    rows = []
    for tp, sl, tmax, queue in itertools.product((3.0, 4.0, 6.0, 8.0), (3.0, 4.0, 6.0, 8.0), (12, 24), (False, True)):
        sr = evaluate(DS, real, tp, sl, tmax, queue)
        sp = [evaluate(DS, p, tp, sl, tmax, queue) for p in plac[:5]]
        pfp = [s["pf"] for s in sp]
        rows.append(dict(tp=tp, sl=sl, tmax=tmax, fila=queue, **sr, placebo_pf=round(np.mean(pfp), 2),
                         placebo_max=round(max(pfp), 2)))
        print(f"TP {tp:3.0f} SL {sl:3.0f} {tmax:2d}b {'fila ' if queue else 'toque'} · {sr['ops']:4d} tr · WR {sr['wr']:4.1f}% · "
              f"PF {sr['pf']:4.2f} (jan–jul {sr['pf_is']:4.2f} · ago–nov {sr['pf_oos']:4.2f}) · R$ {sr['net']:6d} · "
              f"Ret/DD {sr['rdd']:5.2f} · placebo PF {np.mean(pfp):4.2f} (máx {max(pfp):4.2f})", flush=True)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(T.OUT, "limite.csv"), index=False)
    print(f"\nPF mediano: real {R.pf.median():.2f} · placebo {R.placebo_pf.median():.2f} · "
          f"real > placebo máx em {int((R.pf > R.placebo_max).sum())}/{len(R)} · PF>1 em {int((R.pf > 1).sum())}/{len(R)}")


if __name__ == "__main__":
    main()
