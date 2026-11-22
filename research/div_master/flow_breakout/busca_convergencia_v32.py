# -*- coding: utf-8 -*-
"""
Busca e validação de Rompimento / Continuação com CONVERGÊNCIA NO FLUXO (F1 -> F2),
marcada no preço × onda Smart Money (`wave` de `compute_flow`) exatamente com a mesma
infraestrutura causal de pivôs ZigZag e mediana móvel do motor `v3.2` (`modulo.py`).

Três famílias estruturais de Convergência F1 -> F2 testadas em WIN (213d) e WDO (211d):
  1. BRK_F1F2      : F1 = pivô anterior na Wall (topo p/ compra, fundo p/ venda);
                     F2 = barra `t` que rompe F1 e/ou a Wall com ONDA CONVERGENTE
                     (d * (w2 - w1) > thr e d * w2 > 0).
  2. PIV_CONV_CONT : Dois pivôs confirmados no ZigZag (fundos ascendentes p/ compra,
                     topos descendentes p/ venda) escorados em Wall, onde TANTO o preço
                     quanto a onda `wave` sobem/caem juntos (d * (px2 - px1) > 0 e d * (w2 - w1) > thr).
  3. PIV_CONV_MOM  : Dois pivôs de impulso no ZigZag ( dois topos ascendentes T1->T2 p/ compra,
                     dois fundos descendentes F1->F2 p/ venda) que em vez de divergir no fluxo,
                     CONVERGEM (d * (px2 - px1) > 0 e d * (w2 - w1) > thr), operando a favor do
                     rompimento na confirmação do respiro (MOM_CONF) ou na retomada (MOM_REBRK).
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import win_cache, DS_WIN, XW
from research.div_master.wdo_especialista.robustez_final import days_cache as wdo_cache, DS as DS_WDO, X as X_WDO


def _extract_pivots_v32(fb, atr, P, open_module=True):
    """Mesma extração causal de pivôs do engine_v32 em modulo.py."""
    n = len(fb)
    t_open, t_seed = M.hm(M.COMMON["open_conf_end"]), M.hm(M.COMMON["seed_end"])
    ev = [(p["conf"], p["idx"], p["side"], True, "zz")
          for p in M.zigzag(fb, atr, M.COMMON["r_atr"], P["zz_floor"])]
    if open_module:
        for p in M.zigzag(fb, atr, M.COMMON["r_atr_open"], P["zz_floor"]):
            if M.hm(fb[p["conf"]]["time"]) <= t_open:
                ev.append((p["conf"], p["idx"], p["side"], True, "zz08"))
        seeded = {1: False, -1: False}
        for j in range(1, n - 1):
            conf = j + 1
            for d in (1, -1):
                if M.hm(fb[conf]["time"]) <= t_open and M.is_piv(fb, j, d, 2, 1) and d * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                    ev.append((conf, j, d, True, "lr"))
                if not seeded[d] and M.hm(fb[j]["time"]) <= t_seed and M.is_piv(fb, j, d, 1, 1):
                    ev.append((conf, j, d, False, "seed"))
                    seeded[d] = True
        ev.append((0, 0, 1, False, "seed0"))
        ev.append((0, 0, -1, False, "seed0"))
    ev.sort(key=lambda e: (e[0], e[1], ("seed0", "seed", "zz", "zz08", "lr").index(e[4])))
    return ev


def engine_brk_f1f2(fb, levels, P, atr=None, open_module=True):
    """
    Motor 1 (BRK_F1F2):
    F1 = pivô anterior confirmado `k` (topo side=-1 p/ compra dir=+1; fundo side=+1 p/ venda dir=-1).
    F2 = primeira barra `t` (t >= conf_k, min_gap <= t - k <= max_gap) que fecha rompendo `px1`
         (e/ou uma Wall próxima de F1/F2) com CONVERGÊNCIA na onda (`d * (w2 - w1) > thr`).
    Retorna também sinais sem filtro de onda (`conv_ok`, `w2_pos`) para medir placebo exato!
    """
    n = len(fb)
    if n == 0:
        return []
    atr = atr or M.atr_series(fb, P["tick"])
    ev = _extract_pivots_v32(fb, atr, P, open_module=open_module)

    # Mapeia em que barra cada pivô é confirmado
    by_conf = {}
    for conf, j, side, f2_ok, src in ev:
        by_conf.setdefault(conf, []).append((j, side, f2_ok, src))

    pool = {1: [], -1: []}  # pool[side] guarda (k, px1, conf_k)
    seen = {1: set(), -1: set()}
    broken_k = {1: set(), -1: set()}  # cada F1 rompido no máximo 1 vez
    rm = M.RunMedian()
    out = []

    for t in range(n):
        rm.add(abs(float(fb[t]["wave"])))
        # Adiciona pivôs confirmados até t-1 (já conhecidos antes da barra t fechar, ou em t)
        if t - 1 in by_conf:
            for j, side, _, _ in by_conf[t - 1]:
                if j not in seen[side]:
                    seen[side].add(j)
                    px_piv = fb[j]["low"] if side == 1 else fb[j]["high"]
                    pool[side].append((j, px_piv))
                    pool[side].sort()

        if t < 2 or t + 1 >= n:
            continue

        thr = M.COMMON["k_v31"] * rm.get()
        bt_bar = fb[t]
        prev_bar = fb[t - 1]
        c_t, o_t, h_t, l_t = float(bt_bar["close"]), float(bt_bar["open"]), float(bt_bar["high"]), float(bt_bar["low"])
        c_prev = float(prev_bar["close"])
        w2 = float(bt_bar["wave"])

        # Compra (dir = +1) rompe topo anterior (side = -1); Venda (dir = -1) rompe fundo anterior (side = +1)
        for dr, piv_side in ((1, -1), (-1, 1)):
            if dr * (c_t - o_t) <= 0:
                continue  # barra rompendo precisa fechar a favor
            candidates_k = []
            for k, pk in pool[piv_side]:
                gap = t - k
                if gap < M.COMMON["min_gap"] or gap > M.COMMON["max_gap"] or k in broken_k[dr]:
                    continue
                # Rompimento da cabeça do pivô F1 na barra t (c_prev <= pk < c_t para compra)
                if dr == 1:
                    if not (c_prev <= pk + P["buf"] and c_t > pk):
                        continue
                else:
                    if not (c_prev >= pk - P["buf"] and c_t < pk):
                        continue
                w1 = float(fb[k]["wave"])
                ws_k1 = [float(fb[x]["wave"]) for x in range(max(0, k - 1), min(t, k + 1) + 1)]
                w1_k1 = max(ws_k1) if dr == 1 else min(ws_k1)
                candidates_k.append((k, pk, w1, w1_k1))

            if not candidates_k:
                continue

            # Escolhe o F1 mais recente (ou de maior/menor preço rompido)
            k, pk, w1, w1_k1 = max(candidates_k, key=lambda x: x[0])
            broken_k[dr].add(k)

            # Verifica relação com Walls: distância de pk ou c_t até a Wall mais próxima
            d_wall_piv = min((abs(pk - w) for w in levels), default=99999.0)
            d_wall_brk = min((abs(c_t - w) for w in levels), default=99999.0)
            # Wall cruzada pela barra t ou entre pk e c_t
            if dr == 1:
                w_crossed = [w for w in levels if min(o_t, c_prev, pk - P["zone"]) <= w <= c_t]
            else:
                w_crossed = [w for w in levels if c_t <= w <= max(o_t, c_prev, pk + P["zone"])]

            wd = dr * (w2 - w1)
            wd_k1 = dr * (w2 - w1_k1)
            out.append(dict(
                family="BRK_F1F2",
                dir=dr, k=k, j=t, conf=t, idx_sig=t, idx_in=t + 1,
                px1=pk, px2=c_t, w1=w1, w2=w2, wd=wd, wd_k1=wd_k1, thr=thr,
                conv_ok=(wd > thr),
                conv_k1_ok=(wd_k1 > thr),
                w2_fav=(dr * w2 > 0),
                w1_fav=(dr * w1 > 0),
                near_wall=(min(d_wall_piv, d_wall_brk) <= P["zone"]),
                pierce_wall=(min(d_wall_piv, d_wall_brk) <= P["pierce_max"]),
                crossed_wall=bool(w_crossed),
                micro=M.micro_ok(fb, k, t, dr),
            ))
    return out


def engine_piv_conv(fb, levels, P, atr=None, open_module=True):
    """
    Motores 2 e 3 sobre os pivôs confirmados do ZigZag (engine_v32):
      - PIV_CONV_CONT: d = side (Compra d=+1 em 2 fundos ascendentes px2 > px1; Venda d=-1 em 2 topos descendentes px2 < px1)
                       com convergência de fluxo d * (w2 - w1) > thr.
      - PIV_CONV_MOM : d = -side (Compra d=+1 em 2 topos ascendentes px2 > px1; Venda d=-1 em 2 fundos descendentes px2 < px1)
                       com convergência de fluxo d * (w2 - w1) > thr.
    """
    n = len(fb)
    if n == 0:
        return []
    atr = atr or M.atr_series(fb, P["tick"])
    ev = _extract_pivots_v32(fb, atr, P, open_module=open_module)
    tol = P["tol_v21"]

    pool = {1: [], -1: []}
    seen = {1: set(), -1: set()}
    tried = {1: set(), -1: set()}
    out = []

    for conf, j, side, f2_ok, src in ev:
        px2 = M._px(fb[j], side)
        if f2_ok and j not in tried[side] and conf + 1 < n:
            tried[side].add(j)
            thr = M.COMMON["k_v31"] * statistics.median([abs(float(fb[x]["wave"])) for x in range(conf + 1)])
            w2 = float(fb[j]["wave"])
            d_wall = min((abs(px2 - w) for w in levels), default=99999.0)
            a_same = M.anchors(fb, j, side, levels, P)
            a_opp = M.anchors(fb, j, -side, levels, P)

            # 1) PIV_CONV_CONT: continuação (pullback: fundo mais alto p/ compra side=+1, topo mais baixo p/ venda side=-1)
            dr_cont = side
            cs_cont = []
            for k, pk in pool[side]:
                gap = j - k
                if gap < M.COMMON["min_gap"] or gap > M.COMMON["max_gap"]:
                    continue
                # Fundo mais alto (dr=+1: px2 > pk + buf) ou Topo mais baixo (dr=-1: px2 < pk - buf)
                if not ((px2 > pk + P["buf"]) if dr_cont == 1 else (px2 < pk - P["buf"])):
                    continue
                w1 = float(fb[k]["wave"])
                cs_cont.append((k, pk, w1))
            if cs_cont:
                # Pega o pivô anterior k mais recente
                k, pk, w1 = max(cs_cont, key=lambda x: x[0])
                wd = dr_cont * (w2 - w1)
                out.append(dict(
                    family="PIV_CONV_CONT",
                    dir=dr_cont, k=k, j=j, conf=conf, idx_sig=conf, idx_in=conf + 1,
                    px1=pk, px2=px2, w1=w1, w2=w2, wd=wd, wd_k1=wd, thr=thr,
                    conv_ok=(wd > thr),
                    conv_k1_ok=(wd > 0),
                    w2_fav=(dr_cont * w2 > 0),
                    w1_fav=(dr_cont * w1 > 0),
                    near_wall=(d_wall <= P["zone"]),
                    pierce_wall=(d_wall <= P["pierce_max"]),
                    crossed_wall=(a_same["c1"] is not None or a_same["c2"] is not None),
                    micro=M.micro_ok(fb, j, conf, dr_cont),
                ))

            # 2) PIV_CONV_MOM: impulso convergente (2 topos ascendentes side=-1 -> compra dr=+1; 2 fundos descendentes side=+1 -> venda dr=-1)
            dr_mom = -side
            cs_mom = []
            for k, pk in pool[side]:
                gap = j - k
                if gap < M.COMMON["min_gap"] or gap > M.COMMON["max_gap"]:
                    continue
                # Topo mais alto (dr_mom=+1, side=-1: px2 > pk) ou Fundo mais baixo (dr_mom=-1, side=+1: px2 < pk)
                if not ((px2 >= pk - tol) if dr_mom == 1 else (px2 <= pk + tol)):
                    continue
                w1 = float(fb[k]["wave"])
                cs_mom.append((k, pk, w1))
            if cs_mom:
                k, pk, w1 = max(cs_mom, key=lambda x: x[0])
                wd = dr_mom * (w2 - w1)
                # Além da entrada em conf+1 (respiro), procura 1ª barra t em [conf, min(conf+3, n-2)] que fecha a favor
                t_rebrk = None
                for t in range(conf, min(conf + 3, n - 2) + 1):
                    if dr_mom * (float(fb[t]["close"]) - float(fb[t]["open"])) > 0:
                        t_rebrk = t
                        break
                out.append(dict(
                    family="PIV_CONV_MOM",
                    dir=dr_mom, k=k, j=j, conf=conf, idx_sig=conf, idx_in=conf + 1,
                    px1=pk, px2=px2, w1=w1, w2=w2, wd=wd, wd_k1=(dr_mom * (px2 - pk)), thr=thr,
                    conv_ok=(wd > thr),
                    conv_k1_ok=(wd > thr and (px2 > pk if dr_mom == 1 else px2 < pk)),
                    w2_fav=(dr_mom * w2 > 0),
                    w1_fav=(dr_mom * w1 > 0),
                    near_wall=(d_wall <= P["zone"]),
                    pierce_wall=(d_wall <= P["pierce_max"]),
                    crossed_wall=(a_opp["c1"] is not None or a_opp["c2"] is not None or d_wall <= P["zone"]),
                    micro=M.micro_ok(fb, j, conf, dr_mom),
                ))
                if t_rebrk is not None:
                    out.append(dict(
                        family="PIV_MOM_REBRK",
                        dir=dr_mom, k=k, j=j, conf=conf, idx_sig=t_rebrk, idx_in=t_rebrk + 1,
                        px1=pk, px2=px2, w1=w1, w2=w2, wd=wd, wd_k1=(dr_mom * (px2 - pk)), thr=thr,
                        conv_ok=(wd > thr),
                        conv_k1_ok=(wd > thr and (px2 > pk if dr_mom == 1 else px2 < pk)),
                        w2_fav=(dr_mom * w2 > 0),
                        w1_fav=(dr_mom * w1 > 0),
                        near_wall=(d_wall <= P["zone"]),
                        pierce_wall=(d_wall <= P["pierce_max"]),
                        crossed_wall=(a_opp["c1"] is not None or a_opp["c2"] is not None or d_wall <= P["zone"]),
                        micro=M.micro_ok(fb, j, t_rebrk, dr_mom),
                    ))

        if j not in seen[side]:
            seen[side].add(j)
            pool[side].append((j, px2))
            pool[side].sort()

    return out


def collect_asset_conv(asset: str, lv_mode: str = "wall", open_module: bool = True) -> pd.DataFrame:
    cache = win_cache if asset == "WIN" else wdo_cache
    X = XW if asset == "WIN" else X_WDO
    P = dict(M.PARAMS[asset])
    lo_w, hi_w = bt.WINDOW[asset]
    min_nw = 50.0 if asset == "WIN" else 2.0

    recs = []
    for d in sorted(cache):
        fb, w_all, w_wall, D = cache[d]
        levels = w_all if lv_mode == "all" else w_wall
        atr = M.atr_series(fb, P["tick"])

        s1 = engine_brk_f1f2(fb, levels, P, atr=atr, open_module=open_module)
        s2 = engine_piv_conv(fb, levels, P, atr=atr, open_module=open_module)

        for c in (s1 + s2):
            idx_sig, idx_in = c["idx_sig"], c["idx_in"]
            if idx_in >= len(fb):
                continue
            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            ep = float(D["o5"][e])
            dr = int(c["dir"])

            half50 = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
            half30 = max(0.5 * float(D["u30"][e] - D["l30"][e]), X["tick"])
            # ext50_trend > 0 = preço já está do lado da tendência de NWE50
            ext50_trend = dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            ext30_trend = dr * float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / half30

            b_sig = fb[idx_sig]
            rng = max(float(b_sig["high"]) - float(b_sig["low"]), X["tick"])
            body_r = dr * (float(b_sig["close"]) - float(b_sig["open"])) / rng
            pass_s = dr * sum(float(fb[x].get("inst_pass_delta", 0.0)) for x in range(max(0, idx_sig - 1), idx_sig + 1))
            smart_s = dr * float(b_sig.get("smart_inst", 0.0))
            force_s = dr * float(b_sig.get("force", 0.0))
            wyk_s = dr * float(b_sig.get("wyckoff_abs", 0.0))

            nw = bt.next_level(w_all, ep, dr, min_nw + X["front"])
            nw_d = dr * (nw - ep) - X["front"] if nw is not None else np.nan

            recs.append(dict(
                date=d, e=e, ep=ep, dir=dr, j=c["j"], k=c["k"], tm=tm, hh=tm // 60,
                family=c["family"],
                conv_ok=bool(c["conv_ok"]),
                conv_k1_ok=bool(c["conv_k1_ok"]),
                w2_fav=bool(c["w2_fav"]),
                w1_fav=bool(c["w1_fav"]),
                near_wall=bool(c["near_wall"]),
                pierce_wall=bool(c["pierce_wall"]),
                crossed_wall=bool(c["crossed_wall"]),
                micro=bool(c["micro"]),
                ext50_trend=ext50_trend,
                slope50=slope50,
                ext30_trend=ext30_trend,
                body_r=body_r,
                pass_s=pass_s,
                smart_s=smart_s,
                force_s=force_s,
                wyk_s=wyk_s,
                nw_d=nw_d,
            ))

    return pd.DataFrame(recs).sort_values(["date", "tm", "j"]).reset_index(drop=True)


EXITS = [
    ("SL10_TP15_t18", dict(WIN=(200.0, "fix", 300.0, 0.0, 0.0, 18), WDO=(10.0, "fix", 15.0, 0.0, 0.0, 18))),
    ("SL12_TP18_t24", dict(WIN=(240.0, "fix", 360.0, 0.0, 0.0, 24), WDO=(12.0, "fix", 18.0, 0.0, 0.0, 24))),
    ("SL14_TP14_t24", dict(WIN=(280.0, "fix", 280.0, 0.0, 0.0, 24), WDO=(14.0, "fix", 14.0, 0.0, 0.0, 24))),
    ("SL14_TP12_t18", dict(WIN=(280.0, "fix", 240.0, 0.0, 0.0, 18), WDO=(14.0, "fix", 12.0, 0.0, 0.0, 18))),
    ("SL12_NW_t24",   dict(WIN=(240.0, "nw",    0.0, 0.0, 0.0, 24), WDO=(12.0, "nw",   0.0, 0.0, 0.0, 24))),
    ("SL10_BE_t12",   dict(WIN=(200.0, "none",  0.0, 180.0, 20.0, 12), WDO=(10.0, "none", 0.0, 9.0, 1.0, 12))),
]


def precompute_exits(df: pd.DataFrame, asset: str) -> pd.DataFrame:
    DS = DS_WIN if asset == "WIN" else DS_WDO
    X = XW if asset == "WIN" else X_WDO
    nw_min, nw_lo, nw_hi = (50.0, 80.0, 440.0) if asset == "WIN" else (2.5, 4.0, 22.0)
    df = df.copy()
    n = len(df)
    for ex_name, ex_map in EXITS:
        sl, tp_mode, tp_val, be_trig, be_off, tmax = ex_map[asset]
        pnl = np.full(n, np.nan)
        xt = np.zeros(n, dtype=np.int64)
        for i, r in enumerate(df.itertuples()):
            D = DS[r.date]
            if tp_mode == "fix":
                tp_px = r.ep + r.dir * tp_val
            elif tp_mode == "none":
                tp_px = r.ep + r.dir * 999999.0
            else:
                if np.isnan(r.nw_d) or r.nw_d < nw_min:
                    continue
                tp_px = r.ep + r.dir * min(max(r.nw_d, nw_lo), nw_hi)
            p, x = bt.sim(*bt._args(D), D["u30"], r.e, r.ep, r.dir, sl, tp_px, False,
                          0.0, 0.0, 0.0, be_trig, be_off, int(tmax), X["tick"])
            pnl[i] = (p - X["cost"]) * X["brl"]
            xt[i] = x
        df[f"p_{ex_name}"] = pnl
        df[f"x_{ex_name}"] = xt
    return df


def eval_sub(df_sub: pd.DataFrame, ex_name: str):
    valid = df_sub.dropna(subset=[f"p_{ex_name}"])
    if len(valid) < 30:
        return None
    tf = bt.mgmt(valid, f"p_{ex_name}", f"x_{ex_name}", "UM")
    if len(tf) < 30:
        return None
    return bt.stats(tf, f"p_{ex_name}", f"x_{ex_name}")


def main():
    t0 = time.time()
    print("Coletando sinais de Convergência F1->F2 em WIN e WDO...")
    df_win = precompute_exits(collect_asset_conv("WIN", "wall", True), "WIN")
    df_wdo = precompute_exits(collect_asset_conv("WDO", "wall", True), "WDO")
    print(f"WIN candidatos brutos: {len(df_win)} | WDO candidatos brutos: {len(df_wdo)} ({time.time()-t0:.1f}s)")

    # 1. Comparação direta: COM Convergência (conv_ok=True) vs Placebo SEM Convergência (conv_ok=False)
    print("\n" + "=" * 115)
    print("1. IMPACTO PURO DA CONVERGÊNCIA DE FLUXO (F1 -> F2) POR FAMÍLIA (near_wall=True, SL14_TP14_t24)")
    print("=" * 115)
    for asset, df in (("WIN", df_win), ("WDO", df_wdo)):
        print(f"\n--- {asset} ---")
        for fam in ("BRK_F1F2", "PIV_CONV_CONT", "PIV_CONV_MOM", "PIV_MOM_REBRK"):
            for conv_state, label in ((True, "COM Convergência (w2-w1 > thr)"), (False, "SEM Convergência (Placebo)   ")):
                sub = df[(df["family"] == fam) & (df["near_wall"]) & (df["conv_ok"] == conv_state)]
                s = eval_sub(sub, "SL14_TP14_t24")
                if s:
                    print(f"  {fam:<15} | {label} | {s['ops']:4d} ops | WR {s['wr']:5.1f}% | PF {s['pf']:4.2f} | "
                          f"Net {s['net']:+8.0f} | DD {s['dd']:5.0f} | Ret/DD {s['rdd']:5.2f} | {s['meses']}/11m")

    # 2. Busca de filtros por ativo e simétricos (WIN e WDO simultaneamente)
    fams = ["BRK_F1F2", "PIV_CONV_CONT", "PIV_CONV_MOM", "PIV_MOM_REBRK"]
    conv_modes = [
        ("conv",      lambda d: d["conv_ok"]),
        ("conv_w2+",  lambda d: d["conv_ok"] & d["w2_fav"]),
        ("conv_k1",   lambda d: d["conv_k1_ok"]),
        ("conv_k1w2", lambda d: d["conv_k1_ok"] & d["w2_fav"]),
        ("conv_both", lambda d: d["conv_ok"] & d["w2_fav"] & d["w1_fav"]),
    ]
    wall_modes = [
        ("near_w",    lambda d: d["near_wall"]),
        ("pierce_w",  lambda d: d["pierce_wall"]),
        ("cross_w",   lambda d: d["crossed_wall"]),
        ("near&crs",  lambda d: d["near_wall"] & d["crossed_wall"]),
    ]
    time_modes = [
        ("all_h",     lambda d: d["tm"] >= 540),
        ("hh!=11",    lambda d: d["hh"] != 11),
        ("09-12h",    lambda d: d["tm"] <= 720),
        ("09:30-15h", lambda d: (d["tm"] >= 570) & (d["tm"] <= 900)),
        ("10-15h",    lambda d: (d["tm"] >= 600) & (d["tm"] <= 900)),
    ]
    flow_modes = [
        ("all",       lambda d: d["tm"] >= 0),
        ("micro",     lambda d: d["micro"]),
        ("pass>0",    lambda d: d["pass_s"] > 0),
        ("smart>0",   lambda d: d["smart_s"] > 0),
        ("force>0",   lambda d: d["force_s"] > 0),
        ("body>0.4",  lambda d: d["body_r"] > 0.4),
        ("slp>0",     lambda d: d["slope50"] > 0),
        ("ext50<1.0", lambda d: d["ext50_trend"] < 1.0),
        ("ext50<0.5", lambda d: d["ext50_trend"] < 0.5),
        ("ext50<0",   lambda d: d["ext50_trend"] < 0.0),
        ("slp>0&ex<1",lambda d: (d["slope50"] > 0) & (d["ext50_trend"] < 1.0)),
        ("bd>0.4&ex<1",lambda d: (d["body_r"] > 0.4) & (d["ext50_trend"] < 1.0)),
    ]

    win_hits = []
    wdo_hits = []
    sym_hits = []

    for fam in fams:
        dw0 = df_win[df_win["family"] == fam]
        dd0 = df_wdo[df_wdo["family"] == fam]
        for cn, cf in conv_modes:
            dw1 = dw0[cf(dw0)]
            dd1 = dd0[cf(dd0)]
            for wn, wf in wall_modes:
                dw2 = dw1[wf(dw1)]
                dd2 = dd1[wf(dd1)]
                for tn, tf in time_modes:
                    dw3 = dw2[tf(dw2)]
                    dd3 = dd2[tf(dd2)]
                    for fn, ff in flow_modes:
                        dw4 = dw3[ff(dw3)]
                        dd4 = dd3[ff(dd3)]
                        if len(dw4) < 70 and len(dd4) < 70:
                            continue
                        for ex_name, _ in EXITS:
                            sw = eval_sub(dw4, ex_name) if len(dw4) >= 70 else None
                            sd = eval_sub(dd4, ex_name) if len(dd4) >= 70 else None
                            tag = f"{fam} | {cn} | {wn} | {tn} | {fn} | {ex_name}"
                            if sw and sw["ops"] >= 100 and sw["rdd"] >= 3.5 and sw["h1"] > 0 and sw["h2"] > 0 and sw["oos"] > 0:
                                win_hits.append((sw["rdd"], tag, sw, sd))
                            if sd and sd["ops"] >= 100 and sd["rdd"] >= 3.5 and sd["h1"] > 0 and sd["h2"] > 0 and sd["oos"] > 0:
                                wdo_hits.append((sd["rdd"], tag, sd, sw))
                            if sw and sd and sw["ops"] >= 70 and sd["ops"] >= 70 and sw["net"] > 0 and sd["net"] > 0:
                                if sw["h1"] > 0 and sw["h2"] > 0 and sd["h1"] > 0 and sd["h2"] > 0:
                                    min_rdd = min(sw["rdd"], sd["rdd"])
                                    if min_rdd >= 1.5:
                                        sym_hits.append((min_rdd, sw["rdd"] + sd["rdd"], tag, sw, sd))

    win_hits.sort(key=lambda x: x[0], reverse=True)
    wdo_hits.sort(key=lambda x: x[0], reverse=True)
    sym_hits.sort(key=lambda x: (x[0], x[1]), reverse=True)

    print("\n" + "=" * 115)
    print(f"2. TOP CANDIDATOS WIN (>=100 ops, H1/H2/OOS>0, Ret/DD>=3.5): {len(win_hits)} encontrados")
    print("=" * 115)
    for rdd, tag, sw, sd in win_hits[:15]:
        wdo_str = f"WDO: {sd['ops']}op R/DD {sd['rdd']:.2f}" if sd else "WDO: <70op"
        print(f"  WIN {sw['ops']:3d}op WR {sw['wr']:4.1f}% PF {sw['pf']:4.2f} Net {sw['net']:+6.0f} DD {sw['dd']:4.0f} "
              f"R/DD {sw['rdd']:5.2f} ({sw['meses']}/11m) [{wdo_str}] | {tag}")

    print("\n" + "=" * 115)
    print(f"3. TOP CANDIDATOS WDO (>=100 ops, H1/H2/OOS>0, Ret/DD>=3.5): {len(wdo_hits)} encontrados")
    print("=" * 115)
    for rdd, tag, sd, sw in wdo_hits[:15]:
        win_str = f"WIN: {sw['ops']}op R/DD {sw['rdd']:.2f}" if sw else "WIN: <70op"
        print(f"  WDO {sd['ops']:3d}op WR {sd['wr']:4.1f}% PF {sd['pf']:4.2f} Net {sd['net']:+6.0f} DD {sd['dd']:4.0f} "
              f"R/DD {sd['rdd']:5.2f} ({sd['meses']}/11m) [{win_str}] | {tag}")

    print("\n" + "=" * 115)
    print(f"4. VALIDAÇÃO CRUZADA SIMÉTRICA (MESMOS FILTROS EM WIN E WDO, H1/H2>0 AMBOS): {len(sym_hits)} encontrados")
    print("=" * 115)
    for min_r, sum_r, tag, sw, sd in sym_hits[:20]:
        print(f"  minR/DD {min_r:4.2f} | WIN: {sw['ops']:3d}op PF {sw['pf']:4.2f} R/DD {sw['rdd']:4.2f} ({sw['meses']}/11) | "
              f"WDO: {sd['ops']:3d}op PF {sd['pf']:4.2f} R/DD {sd['rdd']:4.2f} ({sd['meses']}/11) | {tag}")


if __name__ == "__main__":
    main()
