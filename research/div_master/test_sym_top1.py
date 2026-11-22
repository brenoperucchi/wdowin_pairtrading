# -*- coding: utf-8 -*-
"""
Análise detalhada da estratégia simétrica SYM_TOP1:
  Regra: V32_OPEN (wall) | CONF | seq <= 1, !super | hh != 11 | ext50 > -0.5 & slope50 > -0.5
  1. Explorar grade fina de SL x TP x tmax (especialmente stops e alvos mais curtos no WDO: 5 a 14 pts, além de BE e ProxWall).
  2. Testar tanto a definição de !super do joint_win_wdo_test quanto !super estrito no CONF (ambas âncoras Wall+Dia).
  3. Rodar bateria completa de robustez (9 testes + Placebo sem divergência).
  4. Avaliar impacto no Portfólio (com E22_WIN e com V1a_WDO).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import (
    win_cache, DS_WIN, XW, get_e22_signals, eval_e22, sim_win_exact
)
from research.div_master.wdo_especialista.robustez_final import (
    days_cache as wdo_cache, DS as DS_WDO, X as X_WDO, make_P as make_P_wdo
)
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo

OPT_OPEN = {**M.V32, "abertura": M.V22_ABERTURA}


def collect_sym_top1(asset: str, nodiv: bool = False, strict_no_super: bool = False) -> pd.DataFrame:
    """
    Extrai os sinais da SYM_TOP1 para WIN ou WDO:
      Motor: V32_OPEN (open_module=True), lv_mode="wall" (só Walls principais)
      Gatilho: CONF (entrada na abertura de conf+1)
      Filtros: seq <= 1 (até 2º sinal por direção no dia), !super, hh != 11, ext50 > -0.5 & slope50 > -0.5
    """
    cache = win_cache if asset == "WIN" else wdo_cache
    X = XW if asset == "WIN" else X_WDO
    P = dict(M.PARAMS[asset])
    lo_w, hi_w = bt.WINDOW[asset]
    min_nw = 50.0 if asset == "WIN" else 2.0

    recs = []
    for d in sorted(cache):
        fb, w_all, w_wall, D = cache[d]
        levels = w_wall
        atr = M.atr_series(fb, P["tick"])

        if nodiv:
            # Placebo sem divergência: mesmos pivôs do V32_OPEN, elegíveis em Wall/Dia, mas SEM checar onda
            t_open = M.hm(M.COMMON["open_conf_end"])
            ev = [(p["conf"], p["idx"], p["side"], "zz") for p in M.zigzag(fb, atr, M.COMMON["r_atr"], P["zz_floor"])]
            for p in M.zigzag(fb, atr, M.COMMON["r_atr_open"], P["zz_floor"]):
                if M.hm(fb[p["conf"]]["time"]) <= t_open:
                    ev.append((p["conf"], p["idx"], p["side"], "zz08"))
            for j in range(1, len(fb) - 1):
                conf = j + 1
                for dr in (1, -1):
                    if M.hm(fb[conf]["time"]) <= t_open and M.is_piv(fb, j, dr, 2, 1) and dr * (fb[conf]["close"] - fb[conf]["open"]) > 0:
                        ev.append((conf, j, dr, "lr"))
            ev.sort(key=lambda e: (e[0], e[1]))
            tried = {1: set(), -1: set()}
            cands = []
            for conf, j, dr, src in ev:
                if j in tried[dr]:
                    continue
                tried[dr].add(j)
                a = M.anchors(fb, j, dr, levels, P)
                if M.eligible(a, "common", fb, j, dr, levels, P):
                    cands.append(M._cand("placebo", dr, j, max(0, j - 5), conf, fb, 0.0, 0.0, 1.0, a))
        else:
            cands = M.engine_v32(fb, levels, P, "common", atr=atr, opt=OPT_OPEN)

        seq = {1: 0, -1: 0}
        for c in cands:
            conf = c["conf"]
            if conf + 1 >= len(fb):
                continue
            s = seq[c["dir"]]
            seq[c["dir"]] += 1

            # Filtro 1: seq <= 1 (apenas 1º e 2º sinal de cada direção no dia)
            if s > 1:
                continue

            # Super-confluência no CONF (quando tem simultaneamente âncora Wall e âncora Dia)
            is_sup_conf = (c["c1"] is not None or c["c2"] is not None) and (c["day"] is not None)
            if strict_no_super and is_sup_conf:
                continue

            idx_in = conf + 1
            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                continue

            # Filtro 2: hh != 11
            if (tm // 60) == 11:
                continue

            e = D["pos"][tm]
            if e < 1:
                continue
            ep = float(D["o5"][e])
            dr = int(c["dir"])

            half50 = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50

            # Filtro 3: ext50 > -0.5 & slope50 > -0.5
            if not (ext50 > -0.5 and slope50 > -0.5):
                continue

            nw_all = bt.next_level(w_all, ep, dr, min_nw + X["front"])
            nw_all_d = dr * (nw_all - ep) - X["front"] if nw_all is not None else np.nan
            nw_wall = bt.next_level(w_wall, ep, dr, min_nw + X["front"])
            nw_wall_d = dr * (nw_wall - ep) - X["front"] if nw_wall is not None else np.nan
            d_wall = min((abs(float(c["px2"]) - w) for w in w_wall), default=99999.0)

            recs.append(dict(
                date=d, e=e, ep=ep, dir=dr, j=c["j"], tm=tm, hh=tm // 60,
                seq=s, is_sup_conf=is_sup_conf, d_wall=d_wall,
                ext50=ext50, slope50=slope50,
                nw_d=nw_all_d, nw_wall_d=nw_wall_d,
            ))

    return pd.DataFrame(recs).sort_values(["date", "tm", "j"]).reset_index(drop=True)


def sim_asset(df: pd.DataFrame, asset: str, sl: float, tp_mode: str, tp_val: float,
              be_trig: float = 0.0, be_lock: float = 0.0, tmax: int = 24,
              mode: str = "padrao", mgmt: str = "UM"):
    DS = DS_WIN if asset == "WIN" else DS_WDO
    X = dict(XW if asset == "WIN" else X_WDO)
    tick = X["tick"]
    cost = X["cost"]
    sl_eff = sl

    if mode == "stop2t":
        sl_eff = sl + 2.0 * tick
    elif mode == "custo2x":
        cost = cost * 2.0
    elif mode == "pesado":
        sl_eff = sl + 2.0 * tick
        cost = cost * 2.0 + 1.0 * tick

    nw_min, nw_lo, nw_hi = (50.0, 80.0, 440.0) if asset == "WIN" else (2.0, 3.5, 20.0)
    n = len(df)
    pnl = np.full(n, np.nan)
    xt = np.zeros(n, dtype=np.int64)

    for i, r in enumerate(df.itertuples()):
        D = DS[r.date]
        dr = -int(r.dir) if mode == "invertida" else int(r.dir)
        if tp_mode == "fix":
            tp_px = r.ep + dr * tp_val
        elif tp_mode == "none":
            tp_px = r.ep + dr * 999999.0
        elif tp_mode == "nw_all":
            if np.isnan(r.nw_d) or r.nw_d < nw_min:
                continue
            tp_px = r.ep + dr * min(max(r.nw_d, nw_lo), nw_hi)
        elif tp_mode == "nw_wall":
            if np.isnan(r.nw_wall_d) or r.nw_wall_d < nw_min:
                continue
            tp_px = r.ep + dr * min(max(r.nw_wall_d, nw_lo), nw_hi)
        else:
            tp_px = r.ep + dr * tp_val

        p, x = bt.sim(
            *bt._args(D), D["u30"], r.e, r.ep, dr, sl_eff, tp_px,
            (mode == "pior_m1"), 0.0, 0.0, 0.0, be_trig, be_lock, int(tmax), tick
        )
        pnl[i] = (p - cost) * X["brl"]
        xt[i] = x

    out = df[["date", "tm"]].copy()
    out["pnl"] = pnl
    out["xt"] = xt
    out = out.dropna(subset=["pnl"]).reset_index(drop=True)
    if len(out) == 0:
        return dict(ops=0, rdd=0.0), out
    tf = bt.mgmt(out, "pnl", "xt", mgmt)
    return bt.stats(tf, "pnl", "xt"), tf


def main():
    t0 = time.time()
    df_w = collect_sym_top1("WIN", nodiv=False, strict_no_super=False)
    df_d = collect_sym_top1("WDO", nodiv=False, strict_no_super=False)
    df_w_ns = collect_sym_top1("WIN", nodiv=False, strict_no_super=True)
    df_d_ns = collect_sym_top1("WDO", nodiv=False, strict_no_super=True)

    print(f"Candidatos SYM_TOP1: WIN={len(df_w)} (strict !super={len(df_w_ns)}) | WDO={len(df_d)} (strict !super={len(df_d_ns)})")

    # 1. EXPLORAÇÃO DE SL x TP x TMAX NO WDO (de stops/alvos curtos 5..14 pts até ProxWall e BE)
    print("\n" + "=" * 115)
    print("1. EXPLORAÇÃO DE SAÍDAS NO WDO PARA SYM_TOP1 (SL 5..14 pts x TP 4..14 pts, BE e ProxWall)")
    print("=" * 115)
    wdo_results = []
    for tmax in (12, 18, 24):
        for sl in (5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 14.0):
            for tp in (4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 14.0):
                s, _ = sim_asset(df_d, "WDO", sl, "fix", tp, 0.0, 0.0, tmax)
                if s["ops"] >= 150 and s["h1"] > 0 and s["h2"] > 0 and s["oos"] > 0:
                    wdo_results.append((s["rdd"], f"SL={sl:4.1f} TP={tp:4.1f} t={tmax:2d} (fix)", sl, "fix", tp, 0.0, 0.0, tmax, s))
            # Com Break-Even (ex: BE em 5, 6, 7, 8 pts travando +0.5 ou +1.0 pt)
            for be_t in (4.0, 5.0, 6.0, 7.0, 8.0):
                if be_t < sl:
                    for tp in (6.0, 8.0, 10.0, 12.0, 0.0):
                        tp_m = "none" if tp == 0.0 else "fix"
                        s, _ = sim_asset(df_d, "WDO", sl, tp_m, tp, be_t, 0.5, tmax)
                        if s["ops"] >= 150 and s["h1"] > 0 and s["h2"] > 0 and s["oos"] > 0:
                            wdo_results.append((s["rdd"], f"SL={sl:4.1f} TP={tp:4.1f} BE={be_t}->0.5 t={tmax:2d}", sl, tp_m, tp, be_t, 0.5, tmax, s))
            # Com ProxWall
            for nw_m in ("nw_all", "nw_wall"):
                s, _ = sim_asset(df_d, "WDO", sl, nw_m, 0.0, 0.0, 0.0, tmax)
                if s["ops"] >= 140 and s["h1"] > 0 and s["h2"] > 0 and s["oos"] > 0:
                    wdo_results.append((s["rdd"], f"SL={sl:4.1f} TP={nw_m} t={tmax:2d}", sl, nw_m, 0.0, 0.0, 0.0, tmax, s))

    wdo_results.sort(key=lambda x: x[0], reverse=True)
    print(f"Total combinações de saída WDO aprovadas (H1/H2/OOS > 0): {len(wdo_results)}")
    for rdd, lbl, sl, tpm, tpv, bet, bel, tm, s in wdo_results[:25]:
        # Checa Custo 2x e Pesado rápido para ver resiliência real ao spread
        s_c2, _ = sim_asset(df_d, "WDO", sl, tpm, tpv, bet, bel, tm, mode="custo2x")
        s_ps, _ = sim_asset(df_d, "WDO", sl, tpm, tpv, bet, bel, tm, mode="pesado")
        print(f"  {lbl:<36} | {s['ops']:3d}op WR {s['wr']:4.1f}% PF {s['pf']:4.2f} Net {s['net']:+6.0f} DD {s['dd']:4.0f} "
              f"R/DD {s['rdd']:5.2f} ({s['meses']}) [H1 {s['h1']:+5.0f} H2 {s['h2']:+5.0f} OOS {s['oos']:+5.0f}] "
              f"| Custo2x R/DD {s_c2['rdd']:4.2f} | Pesado R/DD {s_ps['rdd']:4.2f}")

    # 2. TABELA MATRICIAL SL x TP NO WDO (t=24 e t=18) PARA VER O EFEITO DE ENCURTAR vs ALARGAR
    print("\n" + "=" * 115)
    print("2. MATRIZ SL x TP NO WDO (SYM_TOP1, tmax=24) -> Formato: R/DD (PF | Net)")
    print("=" * 115)
    tps = [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 14.0]
    header = "SL \\ TP | " + " | ".join(f"TP={tp:4.1f}          " for tp in tps)
    print(header)
    print("-" * len(header))
    for sl in [5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 14.0]:
        cells = []
        for tp in tps:
            s, _ = sim_asset(df_d, "WDO", sl, "fix", tp, 0.0, 0.0, 24)
            cells.append(f"{s['rdd']:5.2f} ({s['pf']:4.2f}|{s['net']:+5.0f})")
        print(f"SL={sl:4.1f} | " + " | ".join(cells))

    # 3. EXPLORAÇÃO DE SAÍDAS NO WIN PARA SYM_TOP1
    print("\n" + "=" * 115)
    print("3. EXPLORAÇÃO DE SAÍDAS NO WIN PARA SYM_TOP1 (SL 140..280 pts x TP 140..280 pts, BE e ProxWall)")
    print("=" * 115)
    win_results = []
    for tmax in (12, 18, 24):
        for sl in (140.0, 160.0, 180.0, 200.0, 220.0, 250.0, 280.0):
            for tp in (140.0, 160.0, 180.0, 200.0, 220.0, 240.0, 280.0):
                s, _ = sim_asset(df_w, "WIN", sl, "fix", tp, 0.0, 0.0, tmax)
                if s["ops"] >= 200 and s["h1"] > 0 and s["h2"] > 0 and s["oos"] > 0:
                    win_results.append((s["rdd"], f"SL={sl:3.0f} TP={tp:3.0f} t={tmax:2d} (fix)", sl, "fix", tp, 0.0, 0.0, tmax, s))
            for be_t in (140.0, 160.0, 180.0):
                if be_t < sl:
                    for tp in (200.0, 240.0, 0.0):
                        tp_m = "none" if tp == 0.0 else "fix"
                        s, _ = sim_asset(df_w, "WIN", sl, tp_m, tp, be_t, 20.0, tmax)
                        if s["ops"] >= 200 and s["h1"] > 0 and s["h2"] > 0 and s["oos"] > 0:
                            win_results.append((s["rdd"], f"SL={sl:3.0f} TP={tp:3.0f} BE={be_t:.0f}->20 t={tmax:2d}", sl, tp_m, tp, be_t, 20.0, tmax, s))
            for nw_m in ("nw_all", "nw_wall"):
                s, _ = sim_asset(df_w, "WIN", sl, nw_m, 0.0, 0.0, 0.0, tmax)
                if s["ops"] >= 200 and s["h1"] > 0 and s["h2"] > 0 and s["oos"] > 0:
                    win_results.append((s["rdd"], f"SL={sl:3.0f} TP={nw_m} t={tmax:2d}", sl, nw_m, 0.0, 0.0, 0.0, tmax, s))

    win_results.sort(key=lambda x: x[0], reverse=True)
    for rdd, lbl, sl, tpm, tpv, bet, bel, tm, s in win_results[:20]:
        s_c2, _ = sim_asset(df_w, "WIN", sl, tpm, tpv, bet, bel, tm, mode="custo2x")
        s_ps, _ = sim_asset(df_w, "WIN", sl, tpm, tpv, bet, bel, tm, mode="pesado")
        print(f"  {lbl:<36} | {s['ops']:3d}op WR {s['wr']:4.1f}% PF {s['pf']:4.2f} Net {s['net']:+6.0f} DD {s['dd']:4.0f} "
              f"R/DD {s['rdd']:5.2f} ({s['meses']}) [H1 {s['h1']:+5.0f} H2 {s['h2']:+5.0f} OOS {s['oos']:+5.0f}] "
              f"| Custo2x R/DD {s_c2['rdd']:4.2f} | Pesado R/DD {s_ps['rdd']:4.2f}")

    print(f"\nConcluído etapa 1 em {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
