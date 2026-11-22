# -*- coding: utf-8 -*-
"""
Componentes de fluxo do tape real (.trd do Profit) por pregão — research/flow_ablation, 16/11/2026.

Só leitura dos .trd (Scalper/Profit database/assets). Nada em core/ é alterado; as listas de corretoras e a
lógica de boleta (sweep) vêm de core/profit_wall_players_engine.py.

Saídas (results/tape/):
  inventario_trd.csv          — 1 linha por arquivo .trd >= 150 KB (WIN/WDO/DOL): nº negócios, janela, cobertura
  comp_<ATIVO>_<AAAA-MM-DD>.pkl — DataFrame M5 (09:00–18:25) com OHLC do tape e todos os componentes
  percentis_lote.json         — percentis do tamanho de boleta agressora por ativo (pool dos dias completos)

Convenção de sinal: + = pressão compradora.
  agr_<cls>  = compras agredidas pela classe − vendas agredidas pela classe (classe = corretora AGRESSORA)
  pas_<cls>  = compras passivas da classe (contra agressão vendedora) − vendas passivas (contra agressão compradora)
  net_<cls>  = agr + pas (saldo líquido da classe na barra)
  lot_<bkt>  = delta agressor das boletas (sweep: mesmo segundo + mesma corretora + mesmo lado) por faixa de tamanho
  p_le50 / p_ge90 / p_ge99 = delta das boletas por percentil do ativo
  abs_big    = absorção: preenchimento passivo agrupado (minuto, preço, corretora passiva, lado) >= p99 dos grupos,
               com sinal do lado passivo (comprou contra venda = +)
  renov      = "renovação/iceberg" (proxy): mesmo grupo passivo recebendo agressões em >= 5 segundos distintos no
               minuto (o book não é gravado, então não dá p/ provar iceberg — é heurística)
  proj_*     = classificação EXATA do projeto (_build_from_profit_trd): inst_aggr, inst_pass, hft, ret
"""
import os, sys, json, glob
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
from core.profit_statarb_engine import TRD_DTYPE  # noqa: E402
from core.profit_wall_players_engine import (PURE_INST_CODES, MIXED_INST_BANKS, PURE_HFT_CODES,  # noqa: E402
                                              RETAIL_RLP_CODES)

DIRS = [r"C:\Users\ryzen\AppData\Roaming\Nelogica\Scalper\database\assets",
        r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\database\assets"]
OUT = os.path.join(HERE, "results", "tape")
os.makedirs(OUT, exist_ok=True)
TODAY = "2026-11-16"   # arquivo do dia está sendo escrito ao vivo — excluído

# Classes por corretora (B3_CODE_TO_NAME + PLAYER_ROLE_BY_BROKER do projeto)
CLS = {
    "GRINGO": [13, 16, 23, 40, 77, 92, 107, 127, 238, 308],       # Merrill, JPM, Goldman, Morgan, Citi, Tullett
    "NACIONAL": [27, 39, 59, 72, 114, 191, 688],                  # Santander, Bradesco, Safra, Itaú
    "MISTO": [8, 45, 85],                                         # UBS, BTG
    "HFT": [1618, 3093],                                          # Ideal
    "VAREJO": [3, 88, 93, 120, 147, 262, 1099, 4090, 6003],       # XP, CM, Futura, Genial, Modal, Mirae, Inter, Toro
}
BUCKETS = [(1, 1, "b1"), (2, 5, "b2_5"), (6, 20, "b6_20"), (21, 100, "b21_100"), (101, 10 ** 9, "b100p")]


def list_files():
    rows = []
    for base in DIRS:
        for f in glob.glob(os.path.join(base, "*", "*.trd")):
            name = os.path.basename(f)
            if not name[:3] in ("WIN", "WDO", "DOL") or "_0_1_1_1_0_" not in name:
                continue
            sz = os.path.getsize(f)
            if sz < 150_000:
                continue
            ymd = name.rsplit("_", 1)[-1][:8]
            d = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
            rows.append(dict(asset=name[:3], contract=name.split("_")[0], date=d, path=f, size_mb=round(sz / 1e6, 1),
                             base="Scalper" if "Scalper" in f else "Profit"))
    return rows


def load(path):
    arr = np.fromfile(path, dtype=TRD_DTYPE, count=os.path.getsize(path) // 45)
    arr = arr[(arr["qty"] > 0) & (arr["px"] > 0)]
    day = np.floor(arr["dt"])
    sec = np.floor((arr["dt"] - day) * 86400.0 + 1e-6).astype(np.int32)
    return arr, day, sec


def inventory():
    rows = []
    for r in list_files():
        arr, day, sec = load(r["path"])
        if len(arr) == 0:
            continue
        mn = sec // 60
        reg = (mn >= 540) & (mn <= 1105)
        fl = arr["flag"]
        mins_with = len(np.unique(mn[reg]))
        r.update(n_trades=int(len(arr)), n_reg=int(reg.sum()),
                 first=f"{mn[reg].min() // 60:02d}:{mn[reg].min() % 60:02d}" if reg.any() else "",
                 last=f"{mn[reg].max() // 60:02d}:{mn[reg].max() % 60:02d}" if reg.any() else "",
                 min_cobertos=int(mins_with), cobertura=round(mins_with / 566, 3),
                 n_dias_no_arquivo=int(len(np.unique(day))),
                 pct_agr=round(float(np.isin(fl, [2, 3]).mean()), 3), pct_rlp=round(float((fl == 13).mean()), 3),
                 pct_direto=round(float((fl == 4).mean()), 3),
                 pct_brk0=round(float(((arr["b_brk"] == 0) | (arr["s_brk"] == 0)).mean()), 4),
                 contratos=int(arr["qty"][reg].sum()))
        # completo = cobre o pregão E é tape integral (os arquivos de ~1,5–2,5 MB cobrem o dia mas trazem só ~5% dos
        # negócios e quase nenhum RLP — são amostras/filtrados, não servem)
        min_tr = 2_000_000 if r["asset"] == "WIN" else 200_000
        r["completo"] = bool(r["cobertura"] >= 0.95 and r["date"] != TODAY and r["n_trades"] >= min_tr
                             and r["pct_rlp"] > 0.05)
        rows.append(r)
        print(r["asset"], r["date"], r["size_mb"], r["first"], r["last"], r["cobertura"], flush=True)
    df = pd.DataFrame(rows).sort_values(["asset", "date", "size_mb"], ascending=[True, True, False])
    df.to_csv(os.path.join(OUT, "inventario_trd.csv"), index=False)
    return df


def prep(path, is_win):
    arr, _, sec = load(path)
    mn = sec // 60
    m = (mn >= 540) & (mn <= 1105)
    arr, sec, mn = arr[m], sec[m], mn[m]
    fl = arr["flag"]
    qty = arr["qty"].astype(np.float64)
    px = arr["px"].astype(np.float64)
    bb, sb = arr["b_brk"].astype(np.int64), arr["s_brk"].astype(np.int64)
    isb, iss = fl == 2, fl == 3
    book = isb | iss
    agg = np.where(isb, bb, np.where(iss, sb, 0))
    pas = np.where(isb, sb, np.where(iss, bb, 0))
    ch = np.empty(len(arr), bool)
    ch[0] = True
    ch[1:] = (sec[1:] != sec[:-1]) | (fl[1:] != fl[:-1]) | (agg[1:] != agg[:-1]) | (~book[1:])
    sid = np.cumsum(ch) - 1
    sw = np.bincount(sid, weights=np.where(book, qty, 0.0))[sid]
    return dict(sec=sec, mn=mn, fl=fl, qty=qty, px=px, isb=isb, iss=iss, book=book, agg=agg, pas=pas, sid=sid, sw=sw,
                is_win=is_win)


def sweep_sizes(T):
    first = np.r_[True, T["sid"][1:] != T["sid"][:-1]] & T["book"]
    return T["sw"][first]


def passive_groups(T):
    """Grupos passivos (minuto, preço, corretora passiva, lado passivo). Devolve id por negócio, qty do grupo e
    nº de segundos distintos do grupo."""
    b = T["book"]
    side = np.where(T["iss"], 1, -1)   # lado passivo: +1 comprou (contra agressão vendedora)
    key = pd.DataFrame(dict(mn=T["mn"], px=T["px"], pb=T["pas"], sd=side, sec=T["sec"], q=T["qty"]))[b]
    g = key.groupby(["mn", "px", "pb", "sd"], sort=False)
    gid = g.ngroup().values
    gq = g["q"].transform("sum").values
    gs = g["sec"].transform("nunique").values
    return b, gid, gq, gs, key["sd"].values


def components(T, pct, abs_thr):
    is_win = T["is_win"]
    mn, qty, isb, iss, book, agg, pas, sw = (T[k] for k in ("mn", "qty", "isb", "iss", "book", "agg", "pas", "sw"))
    sgn = np.where(isb, 1.0, np.where(iss, -1.0, 0.0))
    b5 = (mn // 5) * 5
    keys = np.arange(540, 1106, 5)
    pos = np.searchsorted(keys, b5)
    nb = len(keys)

    def S(x):
        return np.bincount(pos, weights=x, minlength=nb)

    out = {}
    # OHLC do tape (negócios do book e diretos; RLP incluído — é negócio real)
    df = pd.DataFrame(dict(p=pos, px=T["px"]))
    g = df.groupby("p")["px"]
    o, h, l, c = (g.first(), g.max(), g.min(), g.last())
    for k, s in (("open", o), ("high", h), ("low", l), ("close", c)):
        v = np.full(nb, np.nan)
        v[s.index.values] = s.values
        out[k] = v
    out["vol"] = S(qty)
    out["buy_vol"] = S(np.where(isb, qty, 0))
    out["sell_vol"] = S(np.where(iss, qty, 0))
    out["agr_total"] = out["buy_vol"] - out["sell_vol"]
    out["rlp_vol"] = S(np.where(T["fl"] == 13, qty, 0))
    out["direto_vol"] = S(np.where(T["fl"] == 4, qty, 0))
    # contagens: negócios (fills) e boletas
    first = np.r_[True, T["sid"][1:] != T["sid"][:-1]] & book
    out["n_fill_delta"] = S(sgn * book)
    out["n_bol_delta"] = S(sgn * first)
    nbb, nbs = S(first & isb), S(first & iss)
    out["lote_med_compra"] = out["buy_vol"] / np.maximum(1, nbb)
    out["lote_med_venda"] = out["sell_vol"] / np.maximum(1, nbs)
    out["porte_tape"] = (out["lote_med_compra"] - out["lote_med_venda"]) / np.maximum(0.5, out["lote_med_compra"] + out["lote_med_venda"])
    # player x modalidade
    known = np.zeros(len(qty), bool)
    known_p = np.zeros(len(qty), bool)
    for cname, codes in CLS.items():
        ma, mp = np.isin(agg, codes) & book, np.isin(pas, codes) & book
        known |= ma
        known_p |= mp
        out[f"agr_{cname}"] = S(np.where(ma, sgn * qty, 0))
        out[f"pas_{cname}"] = S(np.where(mp, -sgn * qty, 0))
        out[f"net_{cname}"] = out[f"agr_{cname}"] + out[f"pas_{cname}"]
    out["agr_OUTROS"] = S(np.where(book & ~known, sgn * qty, 0))
    out["pas_OUTROS"] = S(np.where(book & ~known_p, -sgn * qty, 0))
    out["net_OUTROS"] = out["agr_OUTROS"] + out["pas_OUTROS"]
    # lote (boleta agressora)
    for lo, hi, nm in BUCKETS:
        m = book & (sw >= lo) & (sw <= hi)
        out[f"lot_{nm}"] = S(np.where(m, sgn * qty, 0))
        out[f"lotn_{nm}"] = S(np.where(m & first, sgn, 0))     # nº boletas da faixa (delta)
    out["p_le50"] = S(np.where(book & (sw <= pct["p50"]), sgn * qty, 0))
    out["p_ge90"] = S(np.where(book & (sw >= pct["p90"]), sgn * qty, 0))
    out["p_ge99"] = S(np.where(book & (sw >= pct["p99"]), sgn * qty, 0))
    # absorção / renovação
    b, gid, gq, gs, sd = passive_groups(T)
    q_b = qty[b]
    pos_b = pos[b]
    big = gq >= abs_thr
    ren = gs >= 5
    out["abs_big"] = np.bincount(pos_b, weights=np.where(big, sd * q_b, 0), minlength=nb)
    out["renov"] = np.bincount(pos_b, weights=np.where(ren, sd * q_b, 0), minlength=nb)
    out["abs_big_vol"] = np.bincount(pos_b, weights=np.where(big, q_b, 0), minlength=nb)
    # classificação exata do projeto
    thr, rml, ipt = (30.0, 10.0, 25.0) if is_win else (15.0, 3.0, 10.0)
    a_pi, a_mb, a_ph, a_rb = (np.isin(agg, x) for x in (PURE_INST_CODES, MIXED_INST_BANKS, PURE_HFT_CODES, RETAIL_RLP_CODES))
    p_pi, p_mb, p_ph, p_rb = (np.isin(pas, x) for x in (PURE_INST_CODES, MIXED_INST_BANKS, PURE_HFT_CODES, RETAIL_RLP_CODES))
    ia = book & (a_pi | (a_mb & (sw >= thr)) | (sw >= thr * 1.8))
    ra = book & ~ia & ((a_rb & (sw <= rml * 2)) | (~a_ph & ~a_mb & (sw <= rml)))
    ha = book & ~ia & ~ra
    ip = book & (p_pi | (p_mb & (qty >= ipt * 0.5)) | (qty >= ipt))
    rp = book & ~ip & ((p_rb & (qty <= rml * 1.5)) | (~p_ph & ~p_mb & (qty <= rml)))
    hp = book & ~ip & ~rp
    out["proj_inst_aggr"] = S(np.where(ia, sgn * qty, 0))
    out["proj_inst_pass"] = S(np.where(ip, -sgn * qty, 0))
    out["proj_hft"] = S(np.where(ha, sgn * qty, 0) + np.where(hp, -sgn * qty, 0))
    out["proj_ret"] = S(np.where(ra, sgn * qty, 0))
    res = pd.DataFrame(out)
    res.insert(0, "time", [f"{k // 60:02d}:{k % 60:02d}" for k in keys])
    return res[res["vol"] > 0].reset_index(drop=True)


def main():
    inv = inventory()
    for f in glob.glob(os.path.join(OUT, "comp_*.pkl")):
        os.remove(f)   # só arquivos gerados por este script
    full = inv[inv["completo"] & inv["asset"].isin(["WIN", "WDO"])].drop_duplicates(["asset", "date"])
    # percentis de boleta e limiar de absorção (pool dos dias completos)
    pct, abs_thr = {}, {}
    cache = {}
    for a in ("WIN", "WDO"):
        sws, gqs = [], []
        for _, r in full[full.asset == a].iterrows():
            T = prep(r["path"], a == "WIN")
            cache[(a, r["date"])] = r["path"]
            sws.append(sweep_sizes(T))
            _, gid, gq, _, _ = passive_groups(T)
            u = np.unique(gid, return_index=True)[1]
            gqs.append(gq[u])
        s, gq = np.concatenate(sws), np.concatenate(gqs)
        pct[a] = {f"p{p}": float(np.percentile(s, p)) for p in (50, 75, 90, 95, 99)}
        pct[a]["vol_p90"] = float(np.percentile(np.repeat(s, 1), 90))
        pct[a]["frac_vol_ge_p90"] = float(s[s >= pct[a]["p90"]].sum() / s.sum())
        pct[a]["frac_vol_ge_p99"] = float(s[s >= pct[a]["p99"]].sum() / s.sum())
        for lo, hi, nm in BUCKETS:
            m = (s >= lo) & (s <= hi)
            pct[a][f"n_{nm}"] = float(m.mean())
            pct[a][f"vol_{nm}"] = float(s[m].sum() / s.sum())
        abs_thr[a] = float(np.percentile(gq, 99))
        pct[a]["abs_thr_p99_grupo"] = abs_thr[a]
        pct[a]["n_boletas"] = int(len(s))
        print(a, pct[a], flush=True)
    json.dump(pct, open(os.path.join(OUT, "percentis_lote.json"), "w"), indent=1)
    for (a, d), path in cache.items():
        T = prep(path, a == "WIN")
        C = components(T, pct[a], abs_thr[a])
        C.to_pickle(os.path.join(OUT, f"comp_{a}_{d}.pkl"))
        print("comp", a, d, len(C), flush=True)


if __name__ == "__main__":
    main()
