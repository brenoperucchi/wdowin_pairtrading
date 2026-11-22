# -*- coding: utf-8 -*-
"""
Poder informativo de cada componente de fluxo — research/flow_ablation, 16/11/2026.

(a) correlação na MESMA barra com o candle (retorno da barra, posição do fechamento no range) e IC/acerto para
    a próxima barra e próximas 3/6 barras; IC "além do preço" = IC parcial depois de tirar (por regressão nos
    postos) retorno da barra, posição do fechamento, retorno de 3 barras e a geometria Wyckoff só-preço (E1).
    Erro-padrão por bootstrap em blocos de PREGÃO (as barras do mesmo dia não são independentes).
(c) quanto a decomposição sintética do .min reproduz cada componente do tape (dias com os dois).

Universos: TAPE = dias com .trd completo (results/tape/comp_*.pkl); MIN = todos os pregões do .min (dez/25–nov/26).
Saídas: results/ic_componentes.csv, results/reproducao_sintetico.csv, results/min_m5.pkl
"""
import os, sys, glob, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT]
import flows as FL  # noqa: E402

RES = os.path.join(HERE, "results")
TAPE = os.path.join(RES, "tape")
TICK = {"WIN": 5.0, "WDO": 0.5}
HORIZ = (1, 3, 6)
NBOOT = 400
END_MIN = "2026-11-13"


def rank(x):
    return pd.Series(x).rank().values


def ols_resid(y, X):
    X = np.column_stack([np.ones(len(y)), X])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ b


# ───────────────────────── .min → M5 (todos os dias) ─────────────────────────
def min_m5(asset):
    from core.profit_wall_players_engine import _load_profit_min_index
    idx = _load_profit_min_index(asset)
    rows = []
    days = sorted(d for d in idx if idx[d].get("m1") is not None and d <= END_MIN)
    # limiar de "minuto de lote grande" = p90 do lote médio por lado (pool)
    lots = []
    cache = {}
    for d in days:
        a, mod = FL._minutes(idx[d]["m1"], d)
        if len(a) < 100:
            continue
        cache[d] = (a, mod)
        bl = a["buy_qty"] / np.maximum(1, a["buy_trd"])
        sl = a["sell_qty"] / np.maximum(1, a["sell_trd"])
        lots.append(np.r_[bl, sl])
    p90 = float(np.percentile(np.concatenate(lots), 90))
    for d, (a, mod) in cache.items():
        ia, ip, rd, _, _ = FL._decomp(a, asset)
        bq, sq = a["buy_qty"].astype(float), a["sell_qty"].astype(float)
        bt_, st_ = a["buy_trd"].astype(float), a["sell_trd"].astype(float)
        bl, sl = bq / np.maximum(1, bt_), sq / np.maximum(1, st_)
        big = np.where(bl >= p90, bq, 0) - np.where(sl >= p90, sq, 0)
        rlp = a["qty_vol"].astype(float) - bq - sq
        b5 = (mod // 5) * 5
        df = pd.DataFrame(dict(b5=b5, o=a["open"], h=a["high"], l=a["low"], c=a["close"], bq=bq, sq=sq, bt=bt_, st=st_,
                               ia=ia, ip=ip, rd=rd, big=big, rlp=rlp, vol=a["qty_vol"].astype(float)))
        g = df.groupby("b5")
        m = pd.DataFrame(dict(open=g.o.first(), high=g.h.max(), low=g.l.min(), close=g.c.last(), buy_vol=g.bq.sum(),
                              sell_vol=g.sq.sum(), bt=g.bt.sum(), st=g.st.sum(), syn_inst_aggr=g.ia.sum(),
                              syn_inst_pass=g.ip.sum(), syn_ret=g.rd.sum(), min_lote_grande=g.big.sum(),
                              rlp_vol=g.rlp.sum(), vol=g.vol.sum())).reset_index()
        m["time"] = [f"{int(k) // 60:02d}:{int(k) % 60:02d}" for k in m.b5]
        m["agr_total"] = m.buy_vol - m.sell_vol
        m["min_ntrd_delta"] = m.bt - m.st
        lb, ls = m.buy_vol / np.maximum(1, m.bt), m.sell_vol / np.maximum(1, m.st)
        m["min_porte"] = (lb - ls) / np.maximum(0.5, lb + ls)
        m["min_excesso_lote"] = m.agr_total - 0.5 * (lb + ls) * m.min_ntrd_delta   # delta não explicado pela contagem
        m["syn_inst"] = 0.55 * m.syn_inst_aggr + 1.15 * m.syn_inst_pass - 0.85 * m.syn_ret
        m.insert(0, "date", d)
        rows.append(m.drop(columns=["b5"]))
    out = pd.concat(rows, ignore_index=True)
    out["asset"] = asset
    return out, p90


# ───────────────────────── features de preço e alvos ─────────────────────────
def add_price(df, asset):
    out = []
    for d, g in df.groupby("date", sort=True):
        g = g.sort_values("time").copy()
        o, h, l, c = (g[k].values.astype(float) for k in ("open", "high", "low", "close"))
        rng = np.maximum(h - l, TICK[asset])
        g["ret0"] = (c - o) / o
        g["clv"] = (2 * c - h - l) / rng
        lw, uw = np.maximum(0, np.minimum(o, c) - l), np.maximum(0, h - np.maximum(o, c))
        g["geo"] = ((c - l) / rng) * (0.8 + 1.4 * lw / rng) - ((h - c) / rng) * (0.8 + 1.4 * uw / rng)
        cs = pd.Series(c)
        g["r3"] = (cs / cs.shift(3) - 1).fillna(0).values
        for n in HORIZ:
            g[f"f{n}"] = (cs.shift(-n) / cs - 1).values
        g["volm"] = g["vol"].mean()
        out.append(g)
    return pd.concat(out, ignore_index=True)


def ic_table(df, comps, universe, asset):
    rows = []
    days = df["date"].values
    ud = np.unique(days)
    rs = np.random.RandomState(7)
    boots = [rs.choice(len(ud), len(ud)) for _ in range(NBOOT)]
    pos_by_day = {d: np.where(days == d)[0] for d in ud}
    for comp in comps:
        if comp not in df:
            continue
        x_all = (df[comp] if comp in ("porte_tape", "min_porte") else df[comp] / df["volm"]).values.astype(float)
        r = dict(universo=universe, ativo=asset, componente=comp, n_dias=len(ud), n_barras=int(np.isfinite(x_all).sum()))
        valid0 = np.isfinite(x_all)
        r["corr_ret0"] = float(pd.Series(x_all[valid0]).corr(pd.Series(df["ret0"].values[valid0]), method="spearman"))
        r["corr_clv"] = float(pd.Series(x_all[valid0]).corr(pd.Series(df["clv"].values[valid0]), method="spearman"))
        for n in HORIZ:
            y = df[f"f{n}"].values
            v = np.isfinite(x_all) & np.isfinite(y)
            x, yy = x_all[v], y[v]
            rx, ry = rank(x), rank(yy)
            ic = float(np.corrcoef(rx, ry)[0, 1])
            nz = (x != 0) & (yy != 0)
            hit = float((np.sign(x[nz]) == np.sign(yy[nz])).mean()) if nz.any() else np.nan
            C = np.column_stack([rank(df[k].values[v]) for k in ("ret0", "clv", "r3", "geo")])
            ex, ey = ols_resid(rx, C), ols_resid(ry, C)
            pic = float(np.corrcoef(ex, ey)[0, 1])
            # bootstrap por pregão (IC e IC parcial), índices no espaço filtrado
            vidx = np.cumsum(v) - 1
            bi, bp = [], []
            for bs in boots:
                sel = np.concatenate([pos_by_day[ud[k]] for k in bs])
                sel = sel[v[sel]]
                s2 = vidx[sel]
                bi.append(np.corrcoef(rx[s2], ry[s2])[0, 1])
                bp.append(np.corrcoef(ex[s2], ey[s2])[0, 1])
            se_i, se_p = float(np.nanstd(bi)), float(np.nanstd(bp))
            r.update({f"ic{n}": ic, f"ic{n}_se": se_i, f"ic{n}_t": ic / se_i if se_i > 0 else np.nan,
                      f"hit{n}": hit, f"pic{n}": pic, f"pic{n}_se": se_p, f"pic{n}_t": pic / se_p if se_p > 0 else np.nan})
        rows.append(r)
    return rows


TAPE_COMPS = (["agr_total", "n_fill_delta", "n_bol_delta", "porte_tape"]
              + [f"{k}_{c}" for c in ("GRINGO", "NACIONAL", "MISTO", "HFT", "VAREJO", "OUTROS") for k in ("agr", "pas", "net")]
              + [f"lot_{b}" for b in ("b1", "b2_5", "b6_20", "b21_100", "b100p")]
              + [f"lotn_{b}" for b in ("b1", "b2_5", "b6_20", "b21_100", "b100p")]
              + ["p_le50", "p_ge90", "p_ge99", "abs_big", "renov", "proj_inst_aggr", "proj_inst_pass", "proj_hft", "proj_ret",
                 "proj_inst", "geo_x_vol"])
MIN_COMPS = ["agr_total", "min_ntrd_delta", "min_porte", "min_lote_grande", "min_excesso_lote", "syn_inst_aggr",
             "syn_inst_pass", "syn_ret", "syn_inst", "geo_x_vol"]


def load_tape(asset):
    fs = sorted(glob.glob(os.path.join(TAPE, f"comp_{asset}_*.pkl")))
    parts = []
    for f in fs:
        d = os.path.basename(f)[len(f"comp_{asset}_"):-4]
        c = pd.read_pickle(f)
        c.insert(0, "date", d)
        parts.append(c)
    df = pd.concat(parts, ignore_index=True)
    df["proj_inst"] = 0.55 * df.proj_inst_aggr + 1.15 * df.proj_inst_pass - 0.85 * df.proj_ret
    return df


def main():
    allrows, rep = [], []
    pinfo = {}
    for asset in ("WIN", "WDO"):
        T = add_price(load_tape(asset), asset)
        T["geo_x_vol"] = T["geo"] * T["vol"]          # referência: só preço (escala de volume p/ comparar)
        Mn, p90 = min_m5(asset)
        pinfo[asset] = p90
        Mn = add_price(Mn, asset)
        Mn["geo_x_vol"] = Mn["geo"] * Mn["vol"]
        Mn.to_pickle(os.path.join(RES, f"min_m5_{asset}.pkl"))
        T.to_pickle(os.path.join(RES, f"tape_m5_{asset}.pkl"))
        allrows += ic_table(T, TAPE_COMPS, "TAPE (todos)", asset)
        T26 = T[T.date >= "2026-01-01"]
        if T26.date.nunique() >= 3:
            allrows += ic_table(T26.reset_index(drop=True), TAPE_COMPS, "TAPE 2026", asset)
        allrows += ic_table(Mn, MIN_COMPS, "MIN (todos)", asset)
        # mesmo universo de dias do tape, só que com o .min (p/ separar "dado" de "amostra")
        Mt = Mn[Mn.date.isin(set(T.date))].reset_index(drop=True)
        if Mt.date.nunique() >= 3:
            allrows += ic_table(Mt, MIN_COMPS, "MIN nos dias de tape", asset)
        # (c) reprodução
        J = T.merge(Mn, on=["date", "time"], suffixes=("_t", "_m"))
        pairs = [("agr_total_t", "agr_total_m", "agressão total (sanidade)"),
                 ("proj_inst_aggr", "syn_inst_aggr", "inst agressor (projeto)"),
                 ("proj_inst_pass", "syn_inst_pass", "inst passivo (projeto)"),
                 ("proj_ret", "syn_ret", "varejo agressor (projeto)"),
                 ("proj_inst", "syn_inst", "termo Inst da força"),
                 ("net_GRINGO", "syn_inst", "gringo líquido vs Inst sintético"),
                 ("agr_GRINGO", "syn_inst_aggr", "gringo agressor vs inst agr sintético"),
                 ("pas_GRINGO", "syn_inst_pass", "gringo passivo vs inst pas sintético"),
                 ("net_VAREJO", "syn_ret", "varejo líquido vs varejo sintético"),
                 ("agr_VAREJO", "syn_ret", "varejo agressor vs varejo sintético"),
                 ("p_ge90", "min_lote_grande", "boletas >= p90 vs minutos de lote grande"),
                 ("lot_b100p", "min_lote_grande", "boletas >100 vs minutos de lote grande"),
                 ("porte_tape", "min_porte", "porte (lote médio por lado)"),
                 ("n_bol_delta", "min_ntrd_delta", "contagem de boletas"),
                 ("n_fill_delta", "min_ntrd_delta", "contagem de negócios"),
                 ("abs_big", "syn_inst_pass", "absorção vs inst passivo sintético"),
                 ("renov", "syn_inst_pass", "renovação vs inst passivo sintético")]
        for a_, b_, lab in pairs:
            if a_ not in J or b_ not in J:
                continue
            x, y = J[a_].values.astype(float), J[b_].values.astype(float)
            cum_c = []
            for d, g in J.groupby("date"):
                cx, cy = np.cumsum(g[a_].values), np.cumsum(g[b_].values)
                if cx.std() > 0 and cy.std() > 0:
                    cum_c.append(np.corrcoef(cx, cy)[0, 1])
            nz = (x != 0) & (y != 0)
            rep.append(dict(ativo=asset, par=lab, tape=a_, sintetico=b_, n_dias=J.date.nunique(), n_barras=len(J),
                            pearson_barra=float(np.corrcoef(x, y)[0, 1]),
                            spearman_barra=float(pd.Series(x).corr(pd.Series(y), method="spearman")),
                            sinal_igual=float((np.sign(x[nz]) == np.sign(y[nz])).mean()),
                            corr_acumulado_dia=float(np.mean(cum_c)) if cum_c else np.nan,
                            razao_escala=float(np.std(y) / np.std(x)) if np.std(x) > 0 else np.nan))
        print(asset, "ok", len(T), len(Mn), J.date.nunique(), flush=True)
    pd.DataFrame(allrows).to_csv(os.path.join(RES, "ic_componentes.csv"), index=False)
    pd.DataFrame(rep).to_csv(os.path.join(RES, "reproducao_sintetico.csv"), index=False)
    json.dump(pinfo, open(os.path.join(RES, "min_p90_lote.json"), "w"))


if __name__ == "__main__":
    main()
