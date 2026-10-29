"""
CONSTRUÇÃO DO PORTFÓLIO MIX CAMPEÃO DO DÓLAR (WDO-01 A WDO-16)
==============================================================
Avalia com rigor institucional e descorrelação entre vagas:
  1. Portfólio WDO Atual (Legacy WDO-01..16 Sem Alteração)
  2. Troca Pura ANTES da Otimização (substituindo as 4 vagas mais fracas: WDO-03, WDO-06, WDO-08, WDO-09
     por 4 Novos Achados Estruturais DESCORRELACIONADOS de 1 contrato, mantendo as demais 12 intactas)
  3. Otimização 3-Pilares pura nas 16 estratégias existentes (Caminho 1: sem trocar nenhuma estratégia)
  4. Portfólio MIX CAMPEÃO DO DÓLAR (Regra Estrita: Maior Ret/DD em cada vaga 01..16!)
"""

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_gex_nwe_setups import compute_nwe_series
from research.optimizers.evaluate_and_optimize_wdo_16 import (
    WDO_NAMES,
    load_wdo_and_win_aligned,
    simulate_single_wdo_slot,
    find_nearest_level,
    find_wdo_structural_targets,
    round05,
    window_ok,
    calc_wdo_summary,
)

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "wdo_16_setups_opt")
os.makedirs(OUT_DIR, exist_ok=True)


def simulate_decorrelated_wdo_family(
    slot_id: int,
    df: pd.DataFrame,
    gex_by_date: dict,
    n50_c: np.ndarray, n50_u: np.ndarray, n50_l: np.ndarray, n50_s: np.ndarray,
    n30_c: np.ndarray, n30_u: np.ndarray, n30_l: np.ndarray, n30_s: np.ndarray,
    rsi7s: np.ndarray,
    fam: str,
    wmode: str,
    use_main_walls: bool,
    ent_mode: str,
    vb_max: int = 2,
    sl_pts: float = 11.5,
    be_trig: float = 6.5,
    buf: float = 1.5,
    tp_mode: str = "MID",
    cost_pts: float = 0.5,
):
    dates = df["session_date"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    t_mins = df["t_min"].values
    win_ret3 = df["win_ret3"].values
    win_z = df["win_z"].values

    trades = []
    wall_saves = 0
    n = len(df)
    idx = 2

    while idx < n - 1:
        b1 = idx - 1
        d_str = dates[idx]
        if d_str < "2026-05-07" or d_str not in gex_by_date or dates[b1] != d_str:
            idx += 1
            continue
        if not window_ok(int(t_mins[b1]), wmode):
            idx += 1
            continue
        g = gex_by_date[d_str]
        lvls = g["walls"] if use_main_walls else g["all_levels"]
        if len(lvls) == 0:
            idx += 1
            continue
        gf = g["gamma_flip"] or 0.0
        bo, bh, bl, bc = opens[b1], highs[b1], lows[b1], closes[b1]
        dl, ls = find_nearest_level(lvls, bl)
        dh, lr = find_nearest_level(lvls, bh)
        bw50 = max(1.0, n50_u[b1] - n50_l[b1])
        pos50 = (bc - n50_l[b1]) / bw50
        bw30 = max(1.0, n30_u[b1] - n30_l[b1])
        pos30 = (bc - n30_l[b1]) / bw30
        r7 = rsi7s[b1]

        sig, def_w = 0, 0.0
        if fam == "WIN_ARB_WALL":
            if dl <= 4.0 and pos50 <= 0.36 and (win_ret3[b1] <= -5.0 or win_z[b1] <= -0.8) and (gf <= 0 or bc < gf + 8.0):
                sig, def_w = 1, ls
            elif dh <= 4.0 and pos50 >= 0.64 and (win_ret3[b1] >= 5.0 or win_z[b1] >= 0.8) and (gf <= 0 or bc > gf - 8.0):
                sig, def_w = -1, lr
        elif fam == "RSI_WALL":
            if dl <= 4.0 and pos50 <= 0.35 and r7 <= 35.0 and (gf <= 0 or bc < gf + 10.0):
                sig, def_w = 1, ls
            elif dh <= 4.0 and pos50 >= 0.65 and r7 >= 65.0 and (gf <= 0 or bc > gf - 10.0):
                sig, def_w = -1, lr
        elif fam == "WALL_ABS_LIMIT":
            if dl <= 3.5 and pos50 <= 0.30 and bc > bo and (gf <= 0 or bc < gf):
                sig, def_w = 1, ls
            elif dh <= 3.5 and pos50 >= 0.70 and bc < bo and (gf <= 0 or bc > gf):
                sig, def_w = -1, lr
        elif fam == "MAIN_WALL_CLUSTER":
            if dl <= 5.0 and pos30 <= 0.32 and pos50 <= 0.35 and (gf <= 0 or bc < gf + 5.0):
                sig, def_w = 1, ls
            elif dh <= 5.0 and pos30 >= 0.68 and pos50 >= 0.65 and (gf <= 0 or bc > gf - 5.0):
                sig, def_w = -1, lr
        elif fam == "WDO04_MAIN":
            if gf > 0 and bc > gf + 4.0 and pos50 >= 0.65 and dh <= 4.0 and bc < lr:
                sig, def_w = -1, lr
            elif gf > 0 and bc < gf - 4.0 and pos50 <= 0.35 and dl <= 4.0 and bc > ls:
                sig, def_w = 1, ls
        elif fam == "WDO16_EOD_MAIN":
            if not (550 <= int(t_mins[idx]) <= 840):
                idx += 1
                continue
            if len(trades) > 0 and trades[-1]["date"] == d_str:
                idx += 1
                continue
            if pos50 >= 0.65 and dh <= 4.0 and bc < lr and (gf <= 0 or bc > gf):
                sig, def_w = -1, lr
            elif pos50 <= 0.35 and dl <= 4.0 and bc > ls and (gf <= 0 or bc < gf):
                sig, def_w = 1, ls
        elif fam == "WDO11_GRID_GF":
            if gf > 0 and pos50 <= 0.35 and dl <= 4.5 and bc < gf - 5.0 and bc > bo:
                sig, def_w = 1, ls
            elif gf > 0 and pos50 >= 0.65 and dh <= 4.5 and bc > gf + 5.0 and bc < bo:
                sig, def_w = -1, lr
            if sig != 0:
                epx = round05(opens[idx])
                step2, l1, l2, tp_avg, max_sl, m_hold = 16.0, 1, 2, 11.0, 22.0, 24
                lots, leg = 1, 1
                p1, avg_p = epx, epx
                init_sl = max(max_sl, (l2 * step2) / (l1 + l2) + max_sl)
                c_sl = round05(epx - init_sl) if sig == 1 else round05(epx + init_sl)
                tm_px, _, _, _ = find_wdo_structural_targets(avg_p, sig, g["walls"], g["all_levels"], 0.5)
                c_tp = tm_px
                mfav, bea, bh_cnt, k = 0.0, False, 0, idx
                ex_px = closes[idx]
                while k < n:
                    if dates[k] != d_str or int(t_mins[k]) >= 1035:
                        ex_px = opens[k] if dates[k] == d_str else closes[k - 1]
                        break
                    if leg == 1:
                        p2 = round05(p1 - step2) if sig == 1 else round05(p1 + step2)
                        if (sig == 1 and lows[k] <= p2) or (sig == -1 and highs[k] >= p2):
                            avg_p = round05((p1 * l1 + p2 * l2) / 3.0)
                            lots, leg, bea, mfav = 3, 2, False, 0.0
                            c_tp = round05(avg_p + tp_avg) if sig == 1 else round05(avg_p - tp_avg)
                            c_sl = round05(avg_p - max_sl) if sig == 1 else round05(avg_p + max_sl)
                    if (sig == 1 and lows[k] <= c_sl) or (sig == -1 and highs[k] >= c_sl):
                        ex_px = c_sl
                        break
                    if (sig == 1 and highs[k] >= c_tp) or (sig == -1 and lows[k] <= c_tp):
                        ex_px = c_tp
                        break
                    bh_cnt += 1
                    fav = (highs[k] - avg_p) if sig == 1 else (avg_p - lows[k])
                    if fav > mfav:
                        mfav = fav
                    if k + 1 < n and dates[k + 1] == d_str:
                        no = opens[k + 1]
                        if not bea and mfav >= 6.5:
                            csl = round05(avg_p + 1.5) if sig == 1 else round05(avg_p - 1.5)
                            if (sig == 1 and no > csl + 0.5) or (sig == -1 and no < csl - 0.5):
                                c_sl = max(c_sl, csl) if sig == 1 else min(c_sl, csl)
                                bea = True
                        if bh_cnt >= m_hold:
                            ex_px = no
                            k += 1
                            break
                    k += 1
                pts = ((ex_px - avg_p) * sig - cost_pts) * lots
                trades.append({
                    "date": d_str, "slot_id": slot_id, "side": sig,
                    "contracts": float(lots), "pnl_pts": float(pts), "pnl_brl": float(pts * 10.0),
                })
                idx = max(idx + 1, k + 1)
                continue

        if sig == 0:
            idx += 1
            continue

        filled, fbar, epx = False, idx, 0.0
        for v in range(vb_max):
            eb = idx + v
            if eb >= n or dates[eb] != d_str or int(t_mins[eb]) >= 1005:
                break
            if ent_mode == "LIM_EXT":
                op = round05(bl + 0.5) if sig == 1 else round05(bh - 0.5)
            elif ent_mode == "LIM_MID":
                op = round05(0.5 * (bh + bl))
            elif ent_mode == "LIM_WALL":
                op = round05(def_w + 0.5) if sig == 1 else round05(def_w - 0.5)
            else:
                op = round05(def_w)
            if (sig == 1 and opens[eb] >= op and lows[eb] <= op) or (sig == -1 and opens[eb] <= op and highs[eb] >= op):
                filled, fbar, epx = True, eb, op
                break

        if not filled:
            idx += 1
            continue

        c_sl = round05(epx - sl_pts) if sig == 1 else round05(epx + sl_pts)
        tm_px, tmain_px, _, _ = find_wdo_structural_targets(epx, sig, g["walls"], g["all_levels"], 0.5)
        c_tp = tm_px if tp_mode == "MID" else tmain_px

        mfav, bea, k, bh_cnt = 0.0, False, fbar, 0
        ex_px = closes[fbar]
        touched_zero = False

        while k < n:
            if dates[k] != d_str or int(t_mins[k]) >= 1035:
                ex_px = opens[k] if dates[k] == d_str else closes[k - 1]
                break
            if bea:
                if (sig == 1 and lows[k] <= epx + 1.5) or (sig == -1 and highs[k] >= epx - 1.5):
                    touched_zero = True
            if sig == 1:
                if lows[k] <= c_sl:
                    ex_px = c_sl
                    break
                if highs[k] >= c_tp:
                    ex_px = c_tp
                    break
            else:
                if highs[k] >= c_sl:
                    ex_px = c_sl
                    break
                if lows[k] <= c_tp:
                    ex_px = c_tp
                    break
            bh_cnt += 1
            fav = (highs[k] - epx) if sig == 1 else (epx - lows[k])
            if fav > mfav:
                mfav = fav
            if k + 1 < n and dates[k + 1] == d_str:
                no = opens[k + 1]
                if not bea and mfav >= be_trig:
                    csl = round05(def_w - buf) if sig == 1 else round05(def_w + buf)
                    if (sig == 1 and no > csl + 0.5) or (sig == -1 and no < csl - 0.5):
                        c_sl = max(c_sl, csl) if sig == 1 else min(c_sl, csl)
                        bea = True
                if mfav >= be_trig + 5.0:
                    csl2 = round05(epx + 2.5) if sig == 1 else round05(epx - 2.5)
                    if (sig == 1 and no > csl2 + 0.5) or (sig == -1 and no < csl2 - 0.5):
                        c_sl = max(c_sl, csl2) if sig == 1 else min(c_sl, csl2)
                if mfav >= 13.5:
                    ctr = round05(epx + mfav - 5.0) if sig == 1 else round05(epx - mfav + 5.0)
                    if (sig == 1 and no > ctr + 0.5) or (sig == -1 and no < ctr - 0.5):
                        c_sl = max(c_sl, ctr) if sig == 1 else min(c_sl, ctr)
                if bh_cnt >= 16:
                    ex_px = no
                    k += 1
                    break
            k += 1

        pts = (ex_px - epx) * sig - cost_pts
        if touched_zero and pts > 2.5:
            wall_saves += 1
        trades.append({
            "date": d_str,
            "slot_id": slot_id,
            "side": sig,
            "contracts": 1.0,
            "pnl_pts": float(pts),
            "pnl_brl": float(pts * 10.0),
        })
        idx = max(idx + 1, k + 1)

    return trades, {"wall_saves": wall_saves, "partial_hits": 0}


def main():
    df, gex_by_date = load_wdo_and_win_aligned()
    closes = df["close"].values
    n50_c, n50_u, n50_l, _, n50_s = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
    n30_c, n30_u, n30_l, _, n30_s = compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(closes).diff()
    rsi7s = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    # 7 Ajustes/Novos Achados Estruturais de Altíssimo Ret/DD (incluindo WDO-04, WDO-11 e WDO-16 que estavam < 3.0):
    pa_specs = {
        3: ("NOVO-WDO-03: Arbitragem WIN+WDO MainWall | Limit 50%B1(2b) | BE_2Stage(1.5) | TP_MidWall",
            dict(fam="WIN_ARB_WALL", wmode="CORE_09_1615", use_main_walls=True, ent_mode="LIM_MID", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MID")),
        4: ("3-Pilares MainWall: Limit 50%B1 | BE_2Stage(1.5) | TP_MainWall (MainWalls Only)",
            dict(fam="WDO04_MAIN", wmode="FULL_09_17", use_main_walls=True, ent_mode="LIM_MID", vb_max=1, sl_pts=14.0, be_trig=7.5, buf=1.5, tp_mode="MAIN")),
        6: ("NOVO-WDO-06: Exaustao RSI7+Wall+NWE50 | Limit ExtB1(2b) | BE_2Stage(1.5) | TP_MidWall",
            dict(fam="RSI_WALL", wmode="NO_LUNCH", use_main_walls=False, ent_mode="LIM_EXT", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MID")),
        8: ("NOVO-WDO-08: Absorcao MainWall+Gamma | Limit 50%B1(2b) | BE_2Stage(1.5) | TP_MainWall",
            dict(fam="WALL_ABS_LIMIT", wmode="NO_LUNCH", use_main_walls=True, ent_mode="LIM_MID", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MAIN")),
        9: ("NOVO-WDO-09: Cluster NWE30+50 Wall | Limit Wall+0.5(2b) | BE_2Stage(1.5) | TP_MidWall",
            dict(fam="MAIN_WALL_CLUSTER", wmode="NO_LUNCH", use_main_walls=False, ent_mode="LIM_WALL", vb_max=2, sl_pts=11.5, be_trig=6.5, buf=1.5, tp_mode="MID")),
        11: ("3-Pilares Grid: GammaFlip(-5)+Rejeicao Barra | TP_MidWall Real (NO_LUNCH)",
            dict(fam="WDO11_GRID_GF", wmode="NO_LUNCH", use_main_walls=False, ent_mode="MKT", vb_max=1, sl_pts=22.0, be_trig=6.5, buf=0.0, tp_mode="MID")),
        16: ("3-Pilares EOD MainWall: Limit 50%B1 | BE_Wall(1.5) | TP_MidWall (MainWalls Only)",
            dict(fam="WDO16_EOD_MAIN", wmode="FULL_09_17", use_main_walls=True, ent_mode="LIM_MID", vb_max=1, sl_pts=20.0, be_trig=11.5, buf=1.5, tp_mode="MID")),
    }

    pa_results = {}
    for sid, (label, kwargs) in pa_specs.items():
        tr_pa, st_pa = simulate_decorrelated_wdo_family(
            sid, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s, **kwargs
        )
        pa_results[sid] = (label, calc_wdo_summary(tr_pa, st_pa, label), tr_pa, st_pa)

    # Melhores configurações de 3 Pilares para cada WDO-01..16 (Caminho 1 nas existentes)
    opt_3p_configs = {
        1:  ("CURRENT",      "BE_WALL_SHIELD", 1.0, "TP_MIDWALL",       "3-Pilares: BE_Wall(1.0) + TP_MidWall"),
        2:  ("LIMIT_B1_EXT", "BE_WALL_2STAGE", 1.0, "TP_MIDWALL",       "3-Pilares: Limit_ExtB1 + BE_2Stage(1.0) + TP_MidWall"),
        3:  ("LIMIT_B1_EXT", "BE_WALL_SHIELD", 1.5, "TP_MIDWALL",       "3-Pilares: Limit_ExtB1 + BE_Wall(1.5) + TP_MidWall"),
        4:  ("LIMIT_B1_MID", "BE_WALL_SHIELD", 2.0, "TP_CURRENT",       "3-Pilares: Limit_50%B1 + BE_Wall(2.0) + TP_Orig"),
        5:  ("LIMIT_B1_EXT", "BE_ZERO",        0.0, "TP_MIDWALL",       "3-Pilares: Limit_ExtB1 + TP_MidWall"),
        6:  ("CURRENT",      "BE_WALL_SHIELD", 2.0, "TP_MIDWALL",       "3-Pilares: BE_Wall(2.0) + TP_MidWall"),
        7:  ("CURRENT",      "BE_WALL_SHIELD", 1.0, "TP_MIDWALL",       "3-Pilares: BE_Wall(1.0) + TP_MidWall"),
        8:  ("LIMIT_B1_EXT", "BE_WALL_SHIELD", 1.0, "TP_MIDWALL",       "3-Pilares: Limit_ExtB1 + BE_Wall(1.0) + TP_MidWall"),
        9:  ("CURRENT",      "BE_WALL_SHIELD", 1.0, "TP_MIDWALL",       "3-Pilares: BE_Wall(1.0) + TP_MidWall"),
        10: ("CURRENT",      "BE_WALL_SHIELD", 2.0, "TP_MIDWALL",       "3-Pilares: BE_Wall(2.0) + TP_MidWall"),
        11: ("CURRENT",      "BE_ZERO",        0.0, "TP_MIDWALL",       "3-Pilares: TP_MidWall Real"),
        12: ("CURRENT",      "BE_WALL_SHIELD", 1.5, "TP_PARTIAL_WALLS", "3-Pilares: BE_Wall(1.5) + Parcial 50% Mid / 50% Main"),
        13: ("CURRENT",      "BE_ZERO",        0.0, "TP_MIDWALL",       "3-Pilares: TP_MidWall Real"),
        14: ("CURRENT",      "BE_ZERO",        0.0, "TP_MIDWALL",       "3-Pilares: TP_MidWall Real"),
        15: ("LIMIT_B1_EXT", "BE_WALL_SHIELD", 1.0, "TP_CURRENT",       "3-Pilares: Limit_ExtB1 + BE_Wall(1.0) + TP_Orig"),
        16: ("CURRENT",      "BE_WALL_SHIELD", 1.5, "TP_CURRENT",       "3-Pilares: BE_Wall(1.5) + TP_Orig"),
    }

    p1_legacy = []
    p2_pure_swap = []
    p3_opt_3p = []
    p4_best_mix = []

    rows = []

    for sid in range(1, 17):
        tr_leg, st_leg = simulate_single_wdo_slot(
            sid, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override="CURRENT", be_mode="BE_ZERO", wall_shield_buf=0.0, tp_mode="TP_CURRENT"
        )
        m_leg = calc_wdo_summary(tr_leg, st_leg, "Original")
        p1_legacy.extend(tr_leg)

        em, bm, buf, tm, desc_3p = opt_3p_configs[sid]
        tr_3p, st_3p = simulate_single_wdo_slot(
            sid, df, gex_by_date, n50_c, n50_u, n50_l, n50_s, n30_c, n30_u, n30_l, n30_s, rsi7s,
            entry_override=em, be_mode=bm, wall_shield_buf=buf, tp_mode=tm
        )
        m_3p = calc_wdo_summary(tr_3p, st_3p, desc_3p)
        p3_opt_3p.extend(tr_3p)

        # Portfólio 2: Troca Pura ANTES da otimização nas 4 piores vagas (WDO-03, WDO-06, WDO-08, WDO-09)
        if sid in pa_results:
            pa_lbl, pa_m, pa_tr, _ = pa_results[sid]
            p2_pure_swap.extend(pa_tr)
        else:
            pa_lbl, pa_m, pa_tr = "-", None, None
            p2_pure_swap.extend(tr_leg)

        # Portfólio 4 (MIX CAMPEÃO): Regra estrita de maior Ret/DD
        cands = [
            ("MANTIDO ORIGINAL", m_leg, tr_leg),
            (desc_3p, m_3p, tr_3p),
        ]
        if sid in pa_results:
            cands.append((pa_lbl, pa_m, pa_tr))

        best_lbl, best_m, best_tr = max(cands, key=lambda x: x[1]["Ret_DD"])
        p4_best_mix.extend(best_tr)

        rows.append({
            "Slot": f"WDO-{sid:02d}",
            "Nome": WDO_NAMES[sid],
            "Orig_Tr": m_leg["Trades"],
            "Orig_BRL": m_leg["NetBRL"],
            "Orig_DD": m_leg["MaxDD_BRL"],
            "Orig_PF": m_leg["PF"],
            "Orig_RetDD": m_leg["Ret_DD"],
            "3Pil_BRL": m_3p["NetBRL"],
            "3Pil_DD": m_3p["MaxDD_BRL"],
            "3Pil_RetDD": m_3p["Ret_DD"],
            "NovoPA_BRL": pa_m["NetBRL"] if pa_m else 0.0,
            "NovoPA_DD": pa_m["MaxDD_BRL"] if pa_m else 0.0,
            "NovoPA_RetDD": pa_m["Ret_DD"] if pa_m else 0.0,
            "MIX_Tr": best_m["Trades"],
            "MIX_BRL": best_m["NetBRL"],
            "MIX_DD": best_m["MaxDD_BRL"],
            "MIX_PF": best_m["PF"],
            "MIX_RetDD": best_m["Ret_DD"],
            "Decisao_Mix": best_lbl,
        })

    df_rows = pd.DataFrame(rows)
    df_rows.to_csv(os.path.join(OUT_DIR, "wdo_16_best_mix_decorrelated.csv"), index=False)

    s1 = calc_wdo_summary(sorted(p1_legacy, key=lambda x: x["date"]), {}, "1. ATUAL LEGACY (WDO-01..16 Sem Alteracao)")
    s2 = calc_wdo_summary(sorted(p2_pure_swap, key=lambda x: x["date"]), {}, "2. TROCA PURA ANTES DA OTIMIZACAO (Troca WDO-03, 06, 08, 09 por Novos Achados)")
    s3 = calc_wdo_summary(sorted(p3_opt_3p, key=lambda x: x["date"]), {}, "3. OTIMIZADO 3-PILARES NAS 16 EXISTENTES (Sem Troca de Estrategia)")
    s4 = calc_wdo_summary(sorted(p4_best_mix, key=lambda x: x["date"]), {}, "4. MIX CAMPEAO DO DOLAR (Maior Ret/DD estrito em cada vaga 01..16)")

    df_stages = pd.DataFrame([s1, s2, s3, s4])
    df_stages.to_csv(os.path.join(OUT_DIR, "wdo_portfolio_4_stages_decorrelated.csv"), index=False)

    print("=" * 140)
    print("TABELA VAGA A VAGA DO DOLAR (WDO-01 A WDO-16) — ANTES vs. 3-PILARES vs. NOVOS ACHADOS vs. MIX CAMPEAO:")
    print("=" * 140)
    print(df_rows.to_string(index=False))

    print("\n" + "=" * 140)
    print("COMPARATIVO DOS 4 ESTAGIOS DO PORTFOLIO DO DOLAR (122 PREGOES SINCRONIZADOS):")
    print("=" * 140)
    print(df_stages[["Config", "Trades", "WinRate", "PF", "NetPts", "NetBRL", "MaxDD_BRL", "Ret_DD", "Sharpe"]].to_string(index=False))
    print("=" * 140)


if __name__ == "__main__":
    main()

