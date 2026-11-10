"""
TESTE COMPLETO DE OTIMIZAÇÃO DE TP, SL E BE NAS 4 ESTRATÉGIAS DE WDO
====================================================================
Testa:
  - TP: Fixo vs TP_MIDWALL vs TP_MAINWALL
  - SL: Fixo vs Ancorado no Extremo da Barra b1 (SL_B1_EXT) vs Ancorado na Wall (SL_WALL)
  - BE: Zero vs 1 Estágio atrás da Wall/b1 vs 2 Estágios (atrás da Wall + lucro/MidWall superada)
"""
import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.optimizers.wdo_mt5_sim as wsim

df_wdo, gex_wdo = wsim.load_wdo_mt5_raw()
closes = df_wdo["close"].values
n50_c, n50_u, n50_l, _, n50_s = wsim.compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)
n30_c, n30_u, n30_l, _, n30_s = wsim.compute_nwe_series(closes, lookback=30, bw=3.0, mult=1.6)
rsi7 = wsim.compute_rsi7_series(closes)


def run_custom_wdo_slot(
    slot_id: int,
    tp_mode: int,       # 0 = orig/fixo, 1 = TP_MIDWALL, 2 = TP_MAINWALL
    tp_orig_pts: float,
    sl_mode: str,       # "FIXO", "B1_EXT", "WALL"
    base_sl_pts: float,
    be_mode_custom: int,# 0 = zero, 1 = shield 1-estágio, 2 = shield 2-estágios
    be_buf_custom: float,
    cost_pts: float = 0.5,
):
    """
    Roda simulate_wdo_core_slot com overrides nos parâmetros de gestão de risco.
    """
    # Usamos o código base de simulate_wdo_core_slot interceptando a chamada da ordem
    # Para ser 100% rigoroso e idêntico, executamos a lógica barra a barra:
    dates = df_wdo["session_date"].values
    ts_arr = df_wdo["t"].values
    opens = df_wdo["open"].values
    highs = df_wdo["high"].values
    lows = df_wdo["low"].values
    closes = df_wdo["close"].values
    t_mins = df_wdo["t_min"].values
    win_ret3 = df_wdo["win_ret3"].values
    win_z = df_wdo["win_z"].values

    d_pos = 0
    lots = 0
    avg_price = 0.0
    target_tp = 0.0
    current_sl = 0.0
    orig_sl = 0.0
    be_active = False
    be_stage2_active = False
    max_fav_pts = 0.0
    bars_held = 0
    def_wall = 0.0
    wall_shield_buf = 0.0
    be_trig = 0.0
    be_lock = 0.0
    tr_trig = 0.0
    tr_dist = 0.0
    max_hold_bars = 16
    entry_time = None
    entry_bar_t = None
    trades_today = 0
    last_trade_date = ""
    last_entry_bar_time = None

    pend_dir = 0
    pend_price = 0.0
    pend_tp = 0.0
    pend_sl = 0.0
    pend_be_trig = 0.0
    pend_be_lock = 0.0
    pend_tr_trig = 0.0
    pend_tr_dist = 0.0
    pend_max_hold = 16
    pend_bars_left = 0
    pend_def_wall = 0.0
    pend_be_mode = 0
    pend_wall_buf = 0.0

    trades = []
    n_bars = len(df_wdo)

    for i in range(1, n_bars):
        today_str = str(dates[i])
        if today_str < "2026-05-11" or today_str > "2026-11-04" or today_str not in gex_wdo:
            continue

        if today_str != last_trade_date:
            trades_today = 0
            last_trade_date = today_str

        b1_idx = i - 1
        b1_tmin = int(t_mins[b1_idx])
        b1_time = ts_arr[b1_idx]
        new_bar_time = ts_arr[i]
        new_bar_open = opens[i]
        new_tmin = int(t_mins[i])

        g = gex_wdo[today_str]
        m_levels_walls = np.array(g["walls"], dtype=float)
        m_levels_mid = np.array(g["mid_walls"], dtype=float)
        m_levels_all = np.array(g["all_levels"], dtype=float)
        m_gamma_flip = float(g["gamma_flip"] or 0.0)

        b1_o = opens[b1_idx]
        b1_h = highs[b1_idx]
        b1_l = lows[b1_idx]
        b1_c = closes[b1_idx]
        body1 = b1_c - b1_o
        rng1 = max(0.5, b1_h - b1_l)

        d_l, lvl_s = wsim.find_nearest_level(m_levels_all, b1_l)
        d_h, lvl_r = wsim.find_nearest_level(m_levels_all, b1_h)
        dw_l_main, w_s_main = wsim.find_nearest_level(m_levels_walls, b1_l)
        dw_h_main, w_r_main = wsim.find_nearest_level(m_levels_walls, b1_h)

        m_n50_c_1, m_n50_u_1, m_n50_l_1, m_n50_s_1 = n50_c[b1_idx], n50_u[b1_idx], n50_l[b1_idx], n50_s[b1_idx]
        m_n30_c_1, m_n30_u_1, m_n30_l_1, m_n30_s_1 = n30_c[b1_idx], n30_u[b1_idx], n30_l[b1_idx], n30_s[b1_idx]
        m_rsi7_1 = rsi7[b1_idx]
        m_win_ret3_1 = win_ret3[b1_idx]
        m_win_z_1 = win_z[b1_idx]

        bw50 = max(0.5, m_n50_u_1 - m_n50_l_1)
        bw30 = max(0.5, m_n30_u_1 - m_n30_l_1)
        pos50 = (b1_c - m_n50_l_1) / bw50
        pos30 = (b1_c - m_n30_l_1) / bw30
        mid_b1 = wsim.round05(0.5 * (b1_h + b1_l))

        # 1. OnNewM5Bar (Gestão de posição existente)
        if d_pos != 0:
            bars_held += 1
            if (be_mode_custom == 1 or be_mode_custom == 2) and def_wall > 0.0:
                if d_pos == 1:
                    w_sl = wsim.round05(def_wall - be_buf_custom)
                    if not be_active and max_fav_pts >= be_trig and new_bar_open > w_sl + 0.5:
                        cand_sl = max(current_sl, w_sl)
                        if cand_sl > current_sl:
                            current_sl = cand_sl
                            be_active = True
                    if be_mode_custom == 2 and not be_stage2_active and max_fav_pts >= max(11.5, be_trig + 5.0):
                        lock_sl = wsim.round05(avg_price + be_lock)
                        if lock_sl > current_sl and new_bar_open > lock_sl + 0.5:
                            current_sl = lock_sl
                            be_stage2_active = True
                else:
                    w_sl = wsim.round05(def_wall + be_buf_custom)
                    if not be_active and max_fav_pts >= be_trig and new_bar_open < w_sl - 0.5:
                        cand_sl = min(current_sl, w_sl)
                        if cand_sl < current_sl:
                            current_sl = cand_sl
                            be_active = True
                    if be_mode_custom == 2 and not be_stage2_active and max_fav_pts >= max(11.5, be_trig + 5.0):
                        lock_sl = wsim.round05(avg_price - be_lock)
                        if lock_sl < current_sl and new_bar_open < lock_sl - 0.5:
                            current_sl = lock_sl
                            be_stage2_active = True

            if tr_trig > 0.0 and max_fav_pts >= tr_trig:
                if d_pos == 1:
                    c_sl = wsim.round05(new_bar_open - tr_dist)
                    if c_sl > current_sl: current_sl = c_sl
                else:
                    c_sl = wsim.round05(new_bar_open + tr_dist)
                    if c_sl < current_sl: current_sl = c_sl

            if bars_held >= max_hold_bars and new_bar_time != entry_bar_t:
                pnl = (new_bar_open - avg_price) * d_pos * lots - cost_pts * lots
                trades.append(dict(pnl=pnl, date=today_str, why="TIME"))
                d_pos = 0
                trades_today += 1

        # 2. Pendentes check na abertura
        if d_pos == 0 and pend_dir != 0:
            pend_bars_left -= 1
            if pend_bars_left < 0 or new_tmin >= 1035:
                pend_dir = 0
            else:
                filled = False
                fill_px = pend_price
                if pend_dir == 1 and new_bar_open <= pend_price:
                    filled = True; fill_px = pend_price
                elif pend_dir == -1 and new_bar_open >= pend_price:
                    filled = True; fill_px = pend_price

                if filled:
                    d_pos = pend_dir
                    lots = 1
                    avg_price = fill_px
                    target_tp = wsim.round05(avg_price + d_pos * pend_tp)
                    current_sl = wsim.round05(avg_price - d_pos * pend_sl)
                    orig_sl = current_sl
                    def_wall = pend_def_wall
                    wall_shield_buf = pend_wall_buf
                    be_trig = pend_be_trig
                    be_lock = pend_be_lock
                    tr_trig = pend_tr_trig
                    tr_dist = pend_tr_dist
                    max_hold_bars = pend_max_hold
                    entry_bar_t = new_bar_time
                    bars_held = 0
                    max_fav_pts = 0.0
                    be_active = False
                    be_stage2_active = False
                    pend_dir = 0

        # 3. Geração de Sinais
        if d_pos == 0 and pend_dir == 0 and new_tmin < 1035:
            sig = 0
            ent_type = "MKT"
            ord_p = new_bar_open
            ref_wall = 0.0
            base_tp = tp_orig_pts
            base_sl = base_sl_pts

            if slot_id == 2:
                sig2, wall2 = 0, 0.0
                if last_entry_bar_time != b1_time and wsim.window_ok(b1_tmin, "CORE_09_1615"):
                    for lvl in m_levels_all:
                        if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 2.0):
                            sig2, wall2 = -1, float(lvl); break
                        if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 2.0):
                            sig2, wall2 = 1, float(lvl); break
                if sig2 == 0 and wsim.window_ok(new_tmin, "CORE_09_1615"):
                    if pos50 >= 0.64 and d_h <= 3.5 and b1_c < (lvl_r - 0.5) and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip):
                        sig2, wall2 = -1, lvl_r
                    elif pos50 <= 0.36 and d_l <= 3.5 and b1_c > (lvl_s + 0.5) and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip):
                        sig2, wall2 = 1, lvl_s
                if sig2 != 0:
                    sig = sig2
                    ent_type = "LIMIT"
                    ord_p = wsim.round05(b1_l + 0.5) if sig2 == 1 else wsim.round05(b1_h - 0.5)
                    ref_wall = wall2

            elif slot_id == 7:
                if last_entry_bar_time != b1_time and wsim.window_ok(b1_tmin, "NY_1000_1630"):
                    for lvl in m_levels_all:
                        if b1_o <= lvl + 0.5 and b1_c > lvl + 0.5 and (b1_c - lvl) <= 4.5 and body1 >= 2.0 and m_n50_s_1 >= 0.15 and b1_c < (m_n50_u_1 - bw50 * 0.10):
                            sig, ref_wall, ent_type = -1, float(lvl), "MKT"; break
                        if b1_o >= lvl - 0.5 and b1_c < lvl - 0.5 and (lvl - b1_c) <= 4.5 and (-body1) >= 2.0 and m_n50_s_1 <= -0.15 and b1_c > (m_n50_l_1 + bw50 * 0.10):
                            sig, ref_wall, ent_type = 1, float(lvl), "MKT"; break

            elif slot_id == 9:
                if trades_today < 2 and wsim.window_ok(b1_tmin, "NO_LUNCH"):
                    if d_l <= 5.0 and pos30 <= 0.32 and pos50 <= 0.35 and (m_gamma_flip <= 0.0 or b1_c < m_gamma_flip + 5.0):
                        sig, ref_wall = 1, lvl_s
                    elif d_h <= 5.0 and pos30 >= 0.68 and pos50 >= 0.65 and (m_gamma_flip <= 0.0 or b1_c > m_gamma_flip - 5.0):
                        sig, ref_wall = -1, lvl_r
                    if sig != 0:
                        ent_type = "LIMIT"
                        ord_p = wsim.round05(ref_wall + 0.5) if sig == 1 else wsim.round05(ref_wall - 0.5)

            elif slot_id == 10:
                if trades_today < 3 and 720 <= b1_tmin <= 870:
                    if last_entry_bar_time is None or (b1_time - last_entry_bar_time) >= pd.Timedelta("15min"):
                        mae30 = max(1.2, (m_n30_u_1 - m_n30_c_1) / 1.6)
                        pos_z = (b1_c - m_n30_c_1) / mae30
                        lw10 = min(b1_o, b1_c) - b1_l
                        uw10 = b1_h - max(b1_o, b1_c)
                        if pos_z <= -0.75 and b1_c >= (b1_l + 0.50 * rng1) and (lw10 >= 0.25 * rng1 or b1_c > b1_o):
                            sig, ref_wall, ent_type = 1, b1_l, "MKT"
                        elif pos_z >= 0.75 and b1_c <= (b1_h - 0.50 * rng1) and (uw10 >= 0.25 * rng1 or b1_c < b1_o):
                            sig, ref_wall, ent_type = -1, b1_h, "MKT"

            if sig != 0:
                # Calcula TP de acordo com tp_mode
                tp_val = base_tp if tp_mode == 0 else wsim.calc_wdo_target_pts(ord_p, sig, tp_mode, base_tp, m_levels_walls, m_levels_all)

                # Calcula SL de acordo com sl_mode
                if sl_mode == "FIXO":
                    sl_val = base_sl
                elif sl_mode == "B1_EXT":
                    sl_raw = abs(ord_p - b1_l) + 1.0 if sig == 1 else abs(b1_h - ord_p) + 1.0
                    sl_val = max(7.0, min(14.0, wsim.round05(sl_raw)))
                elif sl_mode == "WALL":
                    sl_raw = abs(ord_p - ref_wall) + 1.5 if ref_wall > 0 else base_sl
                    sl_val = max(7.0, min(15.0, wsim.round05(sl_raw)))
                else:
                    sl_val = base_sl

                if ent_type == "MKT":
                    d_pos = sig
                    lots = 1
                    avg_price = new_bar_open
                    target_tp = wsim.round05(avg_price + sig * tp_val)
                    current_sl = wsim.round05(avg_price - sig * sl_val)
                    orig_sl = current_sl
                    def_wall = ref_wall
                    wall_shield_buf = be_buf_custom
                    be_trig = 5.5 if slot_id == 10 else 6.5
                    be_lock = 1.0 if slot_id == 10 else 1.5
                    tr_trig = 0.0 if slot_id == 10 else 11.0
                    tr_dist = 0.0 if slot_id == 10 else 4.5
                    max_hold_bars = 24 if slot_id == 10 else 15
                    entry_bar_t = new_bar_time
                    bars_held = 0
                    max_fav_pts = 0.0
                    be_active = False
                    be_stage2_active = False
                    last_entry_bar_time = b1_time
                else:
                    pend_dir = sig
                    pend_price = ord_p
                    pend_tp = tp_val
                    pend_sl = sl_val
                    pend_be_trig = 6.5
                    pend_be_lock = 1.5
                    pend_tr_trig = 13.5
                    pend_tr_dist = 5.0
                    pend_max_hold = 16
                    pend_bars_left = 1
                    pend_def_wall = ref_wall
                    pend_be_mode = be_mode_custom
                    pend_wall_buf = be_buf_custom

        # 4. Intrabar ticks (execução SL/TP dentro da barra i)
        if d_pos != 0:
            hi = highs[i]
            li = lows[i]
            fav = (hi - avg_price) if d_pos == 1 else (avg_price - li)
            if fav > max_fav_pts:
                max_fav_pts = fav

            hit_sl = (li <= current_sl) if d_pos == 1 else (hi >= current_sl)
            hit_tp = (hi >= target_tp) if d_pos == 1 else (li <= target_tp)

            if hit_sl and hit_tp:
                # Ordem realista: barra compradora atinge low primeiro se abriu em cima
                hit_sl = True
                hit_tp = False

            if hit_sl:
                exit_p = current_sl
                pnl = (exit_p - avg_price) * d_pos * lots - cost_pts * lots
                trades.append(dict(pnl=pnl, date=today_str, why="SL"))
                d_pos = 0
                trades_today += 1
            elif hit_tp:
                exit_p = target_tp
                pnl = (exit_p - avg_price) * d_pos * lots - cost_pts * lots
                trades.append(dict(pnl=pnl, date=today_str, why="TP"))
                d_pos = 0
                trades_today += 1

    df_t = pd.DataFrame(trades)
    if len(df_t) == 0:
        return dict(Trades=0, WR=0.0, PF=0.0, Net=0.0, DD=0.0, RetDD=0.0)

    gw = df_t[df_t["pnl"] > 0]["pnl"].sum()
    gl = abs(df_t[df_t["pnl"] < 0]["pnl"].sum())
    wr = 100.0 * (df_t["pnl"] > 0).mean()
    pf = gw / gl if gl > 0 else 99.9
    cum = df_t["pnl"].cumsum().values
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    dd = float(np.max(pk - cum)) if len(cum) > 0 else 0.0
    net = float(cum[-1]) * 10.0  # R$
    dd_brl = dd * 10.0
    ret_dd = net / dd_brl if dd_brl > 0 else 99.9

    return dict(Trades=len(df_t), WR=round(wr, 1), PF=round(pf, 2), Net=round(net, 0), DD=round(dd_brl, 0), RetDD=round(ret_dd, 2))


print("=" * 100)
print("  GRADE DE TESTES PARA OS 4 SLOTS DE WDO (WDO-02, WDO-07, WDO-09, WDO-10)")
print("=" * 100)

for sid, base_tp, base_sl in [(2, 25.0, 11.0), (7, 19.0, 11.0), (9, 22.0, 11.5), (10, 16.0, 10.0)]:
    print(f"\n--- WDO-{sid:02d} ---")
    tp_opts = [0, 1, 2] # 0 = Fixo, 1 = MidWall, 2 = MainWall
    sl_opts = ["FIXO", "B1_EXT", "WALL"]
    be_opts = [(1, 1.0), (2, 1.0), (2, 1.5)]

    best_m = None
    best_desc = ""

    for tp_m in tp_opts:
        tp_lbl = "TP_FIXO" if tp_m == 0 else ("TP_MIDWALL" if tp_m == 1 else "TP_MAINWALL")
        for sl_m in sl_opts:
            for be_m, buf in be_opts:
                res = run_custom_wdo_slot(sid, tp_m, base_tp, sl_m, base_sl, be_m, buf, cost_pts=0.5)
                desc = f"{tp_lbl:11s} | SL={sl_m:6s} | BE_M{be_m}(buf={buf})"
                if best_m is None or (res["Net"] > best_m["Net"] and res["PF"] >= best_m["PF"] * 0.95):
                    best_m = res
                    best_desc = desc
                # Imprime se for baseline ou muito bom
                if (tp_m == 0 and sl_m == "FIXO" and be_m == 1) or res["Net"] >= 2800:
                    print(f"  {desc} -> Trades={res['Trades']:3d} | WR={res['WR']:4.1f}% | PF={res['PF']:4.2f} | Net=R$ {res['Net']:6.0f} | DD=R$ {res['DD']:4.0f} | Ret/DD={res['RetDD']:4.2f}")

    print(f"  >> MELHOR WDO-{sid:02d}: {best_desc} -> Net=R$ {best_m['Net']} | PF={best_m['PF']} | DD=R$ {best_m['DD']} | Ret/DD={best_m['RetDD']}")

