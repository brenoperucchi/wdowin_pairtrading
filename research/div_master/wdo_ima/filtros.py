# -*- coding: utf-8 -*-
"""
WDO — o que separa os toques na Wall que SEGURAM dos que ROMPEM? (pedido do usuário em 12/11/2026)
Evento: 1º toque do dia de cada Wall/MidWall (09:15–16:30). Tudo que descreve o evento é conhecido no fechamento da
barra ANTERIOR ao toque (causal) — exceto nada. Resultados por evento:
  respeito  — volta 3 pts para o lado de origem antes de fechar 3 além (12 barras)
  pnl_toque — limite no nível, alvo 6 / stop 4, preenchido ao tocar (otimista)
  pnl_fila  — idem, mas só preenche se o preço passar 1 tick além (realista)
Características (terços definidos em jan–jul; um filtro só vale se melhorar jan–jul E ago–nov):
  velocidade  · quanto o preço andou rumo ao nível nas 3 barras antes do toque (em ATR)
  fluxo_contra· onda do Fluxo Smart Money a favor do respeito na barra anterior (d·onda, em mediana |onda|)
  fluxo_virou · variação da onda nas 3 barras anteriores a favor do respeito
  tipo        · Wall × MidWall      largura · largura da Wall no GEX (1, 2, 3+)
  hora        · 09–10h / 11–12h / 13–14h / 15–16h
  extremo     · o nível está no extremo do dia até ali (toque = nova máxima/mínima)
  nwe         · posição em relação à NWE50: esticado a favor do respeito (preço longe do centro, do lado de onde veio)
  lado        · compra (veio de cima) × venda (veio de baixo)
  dist_open   · distância do nível à abertura do dia (em ATR)
Uso: python research/div_master/wdo_ima/filtros.py
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "research", "div_master", "especialistas")]
import numba as nb
import numpy as np
import pandas as pd
import modulo as M, bt
import teste as T
from research.div_wall.data import load_asset

TICK, COST, BRL = 0.5, 0.5, 10.0
TP, SL, K = 6.0, 4.0, 3.0


@nb.njit(cache=True)
def trade(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, t, L, d, tp, sl, queue, tick):
    """Ordem limite no nível L a partir da barra t (barra do toque). Retorna (preencheu, pts brutos)."""
    n5 = len(o5)
    filled = False
    ep = L
    for k in range(t, n5):
        if filled and (k - t > 24 or tm5[k] >= 1045):
            return True, (o5[k] - ep) * d
        nt = nn[k] if fb[k] == 0 else 4
        for j in range(nt):
            if fb[k] == 0:
                p = px[off[k] + j]
            else:
                p = o5[k] if j == 0 else ((l5[k] if d == 1 else h5[k]) if j == 1 else ((h5[k] if d == 1 else l5[k]) if j == 2 else c5[k]))
            if not filled:
                if (L - p) * d >= (tick if queue else 0.0):
                    filled = True
                    if j == 0 and (L - p) * d > (tick if queue else 0.0):
                        ep = p
                continue
            if (p - (ep - d * sl)) * d <= 0:
                return True, -sl - tick
            if (p - (ep + d * tp)) * d >= 0:
                return True, tp
        if not filled:
            return False, 0.0
    return filled, (c5[n5 - 1] - ep) * d if filled else 0.0


def events():
    data = load_asset("WDO", "M5")
    DS = bt.market("WDO")
    h = pd.read_csv(os.path.join(ROOT, "mt5", "Files", "jumba_gex_wdo_history.csv"), sep=";")
    width = {(str(r.session_date), round(float(r.price), 2)): int(r.width) for r in h[h.type == "Wall"].itertuples()}
    rows = []
    for d in sorted(data):
        if d not in DS or d > bt.END:
            continue
        bars, walls, _ = data[d]
        D = DS[d]
        fb = M.compute_flow([dict(b) for b in bars], "WDO")
        wave_by_t = {b["time"]: float(b["wave"]) for b in fb}
        o, hh, l, c, tm = D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"]
        n = len(c)
        rng = np.maximum(hh - l, TICK)
        atr = pd.Series(rng).rolling(14, min_periods=1).mean().values
        waves = np.array([wave_by_t.get(f"{int(x) // 60:02d}:{int(x) % 60:02d}", np.nan) for x in tm])
        lvl = [(float(w["price"]), w["type"]) for w in walls if w.get("type") in M.LEVEL_TYPES]
        for L, typ in lvl:
            for t in range(4, n - 1):
                if not (l[t] <= L <= hh[t]):
                    continue
                if not (555 <= tm[t] <= 990):
                    break
                dd = 1 if c[t - 1] > L else -1                 # veio de cima → compra (respeito)
                a = atr[t - 1]
                res = None
                for u in range(t, min(n, t + 13)):
                    if dd * (c[u] - L) >= K:
                        res = 1
                        break
                    if dd * (L - c[u]) >= K:
                        res = 0
                        break
                f1, p1 = trade(*bt._args(D), t, L, dd, TP, SL, False, TICK)
                f2, p2 = trade(*bt._args(D), t, L, dd, TP, SL, True, TICK)
                wv = waves[max(0, t - 30): t]
                med = np.nanmedian(np.abs(wv)) if np.isfinite(wv).any() else np.nan
                lo_day, hi_day = l[:t].min(), hh[:t].max()
                rows.append(dict(
                    date=d, tm=int(tm[t]), L=L, dir=dd, tipo=typ,
                    largura=width.get((d, round(L, 2)), 1) if typ == "Wall" else 0,
                    velocidade=-dd * (c[t - 1] - c[t - 4]) / a,     # >0 = veio rápido rumo ao nível
                    fluxo_contra=dd * waves[t - 1] / med if med and np.isfinite(waves[t - 1]) else np.nan,
                    fluxo_virou=dd * (waves[t - 1] - waves[t - 4]) / med if med and np.isfinite(waves[t - 4]) else np.nan,
                    extremo=int((dd == 1 and L <= lo_day) or (dd == -1 and L >= hi_day)),
                    nwe=dd * (D["c50"][t] - c[t - 1]) / max(D["u50"][t] - D["c50"][t], TICK),   # >0 = esticado longe do centro do lado de onde veio
                    dist_open=abs(L - o[0]) / a,
                    hora=int(tm[t]) // 60,
                    respeito=res, filled_toque=f1, pnl_toque=(p1 - COST) * BRL if f1 else np.nan,
                    filled_fila=f2, pnl_fila=(p2 - COST) * BRL if f2 else np.nan))
                break
    return pd.DataFrame(rows)


def summ(g):
    r = g.respeito.dropna()
    pt, pf_ = g.pnl_toque.dropna(), g.pnl_fila.dropna()

    def pf(p):
        gw, gl = p[p > 0].sum(), -p[p < 0].sum()
        return gw / gl if gl else np.nan
    return dict(n=len(g), resp=100 * r.mean() if len(r) else np.nan, pf_toque=pf(pt), pf_fila=pf(pf_),
                rs_fila=pf_.sum())


def main():
    E = events()
    E.to_csv(os.path.join(T.OUT, "eventos_toque.csv"), index=False)
    E["per"] = np.where(E.date <= T.IS_END, "jan–jul", "ago–nov")
    print(f"{len(E)} toques (1º do dia por nível) · jan–jul {int((E.per == 'jan–jul').sum())} · ago–nov {int((E.per == 'ago–nov').sum())}")
    base = {p: summ(g) for p, g in E.groupby("per")}
    print("BASE      " + " | ".join(f"{p}: n {s['n']} · resp {s['resp']:.1f}% · PF toque {s['pf_toque']:.2f} · PF fila {s['pf_fila']:.2f}"
                                    for p, s in base.items()))
    E["hora_g"] = pd.cut(E.hora, [8, 10, 12, 14, 17], labels=["09–10h", "11–12h", "13–14h", "15–16h"])
    E["largura_g"] = E.largura.clip(upper=3).map({0: "MidWall", 1: "W1", 2: "W2", 3: "W3+"})
    E["lado"] = E.dir.map({1: "compra", -1: "venda"})
    IS = E.per == "jan–jul"
    out = []
    for f in ("velocidade", "fluxo_contra", "fluxo_virou", "nwe", "dist_open"):
        q = E.loc[IS, f].quantile([1 / 3, 2 / 3]).values
        E[f + "_g"] = pd.cut(E[f], [-np.inf, q[0], q[1], np.inf], labels=["baixo", "médio", "alto"])
    cats = ["velocidade_g", "fluxo_contra_g", "fluxo_virou_g", "nwe_g", "dist_open_g", "hora_g", "largura_g", "tipo",
            "extremo", "lado"]
    print(f"\n{'característica':16s} {'grupo':8s} | {'jan–jul: n  resp  PFtoq PFfila':34s} | {'ago–nov: n  resp  PFtoq PFfila':34s}")
    for cat in cats:
        for grp, g in E.groupby(cat):
            s = {p: summ(gg) for p, gg in g.groupby("per")}
            if len(s) < 2:
                continue
            a, b = s["jan–jul"], s["ago–nov"]
            both = a["pf_fila"] > 1 and b["pf_fila"] > 1
            out.append(dict(caracteristica=cat.replace("_g", ""), grupo=str(grp), **{f"is_{k}": v for k, v in a.items()},
                            **{f"oos_{k}": v for k, v in b.items()}, fila_nos_dois=both))
            mark = " ◀ PF fila > 1 nos dois" if both else ""
            print(f"{cat.replace('_g', ''):16s} {str(grp):8s} | {a['n']:4d} {a['resp']:5.1f}% {a['pf_toque']:5.2f} {a['pf_fila']:5.2f}"
                  f"{'':10s} | {b['n']:4d} {b['resp']:5.1f}% {b['pf_toque']:5.2f} {b['pf_fila']:5.2f}{mark}")
    pd.DataFrame(out).to_csv(os.path.join(T.OUT, "filtros_toque.csv"), index=False)


if __name__ == "__main__":
    main()
