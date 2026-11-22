# -*- coding: utf-8 -*-
"""
"O dólar respeita as Walls" — as Walls do WDO são especiais? E dá para operar indo A FAVOR até a próxima Wall?
(pedido do usuário em 12/11/2026, depois de a reversão na Wall não ter vantagem no WDO)

Tudo comparado com PLACEBO: os mesmos níveis do dia deslocados por um valor sorteado (25–75% do espaçamento
mediano entre níveis), 10 sorteios. Se a Wall real não for diferente do placebo, ela não tem nada de especial.

1. RESPEITO: no primeiro toque de cada nível no dia (vindo de um lado), o que acontece primeiro em até 12 barras:
   o preço volta k pts para o lado de onde veio (respeitou) ou fecha k pts além (rompeu)?
2. ÍMÃ: estando a uma distância d do nível mais próximo à frente, qual a chance de tocá-lo em até 12 barras?
3. ESTRATÉGIA "RUMO À WALL": entrada a mercado na barra seguinte quando há impulso na direção (fechamento além da
   máxima/mínima anterior com corpo a favor, ou NWE50 inclinada a favor) e a próxima Wall está entre Dmin e Dmax;
   alvo = Wall − 0,5; stop fixo; um trade por vez; 09:15–16:30. Mesma regra com os níveis placebo.
Ativos: WDO (alvo da pergunta) e WIN (comparação). Execução tick a tick em M1.
Uso: python research/div_master/wdo_ima/teste.py → results/
"""
import itertools, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "research", "div_master", "especialistas")]
import numpy as np
import pandas as pd
import modulo as M, bt
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
IS_END = "2026-07-31"
CFG = {"WDO": dict(k=2.0, front=0.5, d=(4.0, 6.0, 8.0, 12.0), sl=(3.0, 5.0, 7.0), dmin=(3.0, 5.0), dmax=(10.0, 20.0)),
       "WIN": dict(k=100.0, front=15.0, d=(150.0, 250.0, 400.0, 600.0), sl=(150.0, 200.0, 300.0), dmin=(150.0, 250.0),
                   dmax=(500.0, 1000.0))}


def day_levels(walls):
    return sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)


def placebo(levels, rng):
    if len(levels) < 2:
        return levels
    gap = float(np.median(np.diff(levels)))
    s = rng.uniform(0.25, 0.75) * gap * rng.choice((-1, 1))
    return [v + s for v in levels]


def respect(D, levels, k):
    """Primeiro toque de cada nível: 1 = respeitou, 0 = rompeu, None = nenhum dos dois em 12 barras."""
    o, h, l, c = D["o5"], D["h5"], D["l5"], D["c5"]
    n = len(c)
    out = []
    for L in levels:
        for t in range(1, n - 1):
            if l[t] <= L <= h[t]:
                side = 1 if c[t - 1] > L else -1          # veio de cima (1) ou de baixo (−1)
                res = None
                for u in range(t, min(n, t + 13)):
                    if side * (c[u] - L) >= k:            # voltou k para o lado de origem
                        res = 1
                        break
                    if side * (L - c[u]) >= k:            # fechou k além
                        res = 0
                        break
                out.append(res)
                break
    return out


def magnet(D, levels, dists):
    """Para cada barra e cada faixa de distância: houve toque do nível mais próximo à frente (acima e abaixo)?"""
    h, l, c = D["h5"], D["l5"], D["c5"]
    n = len(c)
    hits = {d: [0, 0] for d in dists}
    lv = np.array(levels)
    for t in range(n - 12):
        for side in (1, -1):
            ahead = lv[(lv - c[t]) * side > 0]
            if len(ahead) == 0:
                continue
            L = ahead.min() if side == 1 else ahead.max()
            dist = abs(L - c[t])
            for d in dists:
                if dist <= d and dist > d * 0.5:
                    hit = (h[t + 1: t + 13].max() >= L) if side == 1 else (l[t + 1: t + 13].min() <= L)
                    hits[d][0] += int(hit)
                    hits[d][1] += 1
    return hits


def strategy(asset, DS, lv_by_day, trig, sl, dmin, dmax, front):
    x = bt.X[asset]
    rows = []
    for d, D in DS.items():
        if d not in lv_by_day or d > bt.END:
            continue
        lv = np.array(lv_by_day[d])
        if len(lv) == 0:
            continue
        o, h, l, c, tm = D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"]
        n = len(c)
        busy = -1
        for t in range(2, n - 1):
            if t <= busy or not (555 <= tm[t + 1] <= 990):
                continue
            for side in (1, -1):
                if trig == "barra":
                    ok = (c[t] > h[t - 1] if side == 1 else c[t] < l[t - 1]) and side * (c[t] - o[t]) > 0
                else:   # NWE50 inclinada a favor e preço do lado certo do centro
                    ok = side * (D["c50"][t + 1] - D["c50"][max(0, t - 5)]) > 0 and side * (c[t] - D["c50"][t + 1]) > 0
                if not ok:
                    continue
                ep = o[t + 1]
                ahead = lv[(lv - ep) * side >= dmin]
                if len(ahead) == 0:
                    continue
                L = ahead.min() if side == 1 else ahead.max()
                if abs(L - ep) > dmax:
                    continue
                tp = L - side * front
                pts, xt = bt.sim(*bt._args(D), D["u30"], t + 1, ep, side, sl, tp, False, 0.0, 0.0, 0.0, 0.0, 0.0, 24,
                                 x["tick"])
                rows.append((d, int(tm[t + 1]), int(xt), (pts - x["cost"]) * x["brl"]))
                busy = int(np.searchsorted(tm, xt))
                break
    return rows


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0.0, net=0, rdd=0.0, pf_is=0.0, pf_oos=0.0)
    R = pd.DataFrame(rows, columns=["date", "tm", "xt", "brl"]).sort_values(["date", "xt", "tm"])
    p = R.brl.values
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    isv = (R.date <= IS_END).values

    def pf(q):
        g, l_ = q[q > 0].sum(), -q[q < 0].sum()
        return round(g / l_, 2) if l_ else 99.0

    return dict(ops=len(p), pf=pf(p), net=round(eq[-1]), rdd=round(eq[-1] / dd, 2) if dd else 99.0,
                pf_is=pf(p[isv]), pf_oos=pf(p[~isv]))


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for asset in ("WDO", "WIN"):
        cfg = CFG[asset]
        data = load_asset(asset, "M5")
        DS = bt.market(asset)
        real = {d: day_levels(v[1]) for d, v in data.items() if d in DS}
        plac = [{d: placebo(lv, np.random.default_rng(1000 * s + i)) for i, (d, lv) in enumerate(sorted(real.items()))}
                for s in range(10)]

        # 1. respeito
        def resp(lvmap):
            r = [x for d, lv in lvmap.items() for x in respect(DS[d], lv, cfg["k"]) if x is not None]
            return 100 * np.mean(r), len(r)

        rr, nr = resp(real)
        rp = [resp(p)[0] for p in plac]
        print(f"\n== {asset} · 1) RESPEITO no 1º toque (volta {cfg['k']} antes de fechar {cfg['k']} além, até 12 barras)")
        print(f"   Walls reais: {rr:.1f}% respeitam ({nr} toques) · placebo: {np.mean(rp):.1f}% "
              f"(faixa {min(rp):.1f}–{max(rp):.1f}%)")
        rows.append(dict(ativo=asset, teste="respeito", real=round(rr, 1), placebo=round(np.mean(rp), 1),
                         placebo_min=round(min(rp), 1), placebo_max=round(max(rp), 1), n=nr))

        # 2. ímã
        def mag(lvmap):
            tot = {d: [0, 0] for d in cfg["d"]}
            for d, lv in lvmap.items():
                if lv:
                    for k_, (a, b) in magnet(DS[d], lv, cfg["d"]).items():
                        tot[k_][0] += a
                        tot[k_][1] += b
            return {k_: 100 * a / b if b else 0 for k_, (a, b) in tot.items()}

        mr = mag(real)
        mp = [mag(p) for p in plac[:5]]
        print(f"== {asset} · 2) ÍMÃ: chance de tocar o nível à frente em até 12 barras (distância entre d/2 e d)")
        for d in cfg["d"]:
            pv = [m[d] for m in mp]
            print(f"   d ≤ {d:6.1f}: Walls reais {mr[d]:5.1f}% · placebo {np.mean(pv):5.1f}% ({min(pv):.1f}–{max(pv):.1f}%)")
            rows.append(dict(ativo=asset, teste=f"ima d<={d}", real=round(mr[d], 1), placebo=round(np.mean(pv), 1),
                             placebo_min=round(min(pv), 1), placebo_max=round(max(pv), 1)))

        # 3. estratégia rumo à Wall
        print(f"== {asset} · 3) RUMO À WALL (alvo na Wall − {cfg['front']}, stop fixo, 24 barras)")
        for trig, sl, dmin, dmax in itertools.product(("barra", "nwe50"), cfg["sl"], cfg["dmin"], cfg["dmax"]):
            sr = stats(strategy(asset, DS, real, trig, sl, dmin, dmax, cfg["front"]))
            sp = [stats(strategy(asset, DS, p, trig, sl, dmin, dmax, cfg["front"])) for p in plac[:3]]
            pfp = np.mean([s["pf"] for s in sp])
            rows.append(dict(ativo=asset, teste=f"rumo {trig} SL{sl} D{dmin}-{dmax}", real=sr["pf"], placebo=round(pfp, 2),
                             ops=sr["ops"], net=sr["net"], rdd=sr["rdd"], pf_is=sr["pf_is"], pf_oos=sr["pf_oos"]))
            print(f"   {trig:5s} SL {sl:5.1f} D {dmin:5.1f}–{dmax:6.1f}: {sr['ops']:5d} tr · PF {sr['pf']:4.2f} "
                  f"(jan–jul {sr['pf_is']:4.2f} · ago–nov {sr['pf_oos']:4.2f}) · R$ {sr['net']:7d} · placebo PF {pfp:4.2f}",
                  flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "ima.csv"), index=False)


if __name__ == "__main__":
    main()
