"""
OTIMIZADOR ESTRUTURAL GEX WALLS + NWE + PRICE ACTION (WIN$N - 122 PREGÕES REAIS)
================================================================================
Modelagem intrabar OHLC idêntica ao MetaTrader 5 Strategy Tester:
  - Barra de alta (Close >= Open): sequência Open -> Low -> High -> Close
  - Barra de baixa (Close < Open): sequência Open -> High -> Low -> Close

Testa sistematicamente os 3 Pilares:
  1. PILAR 1 (Gestão de Stop / Break-Even Protegido pelas Walls):
     - BE_ZERO (Baseline): puxa SL para entry_px + 20 (na frente da Wall -> vulnerável a violinadas no reteste da Wall)
     - BE_WALL_SHIELD: no 1º gatilho, reduz SL inicial para logo atrás da Wall (Wall ∓ buf, ex: 15..35 pts atrás da Wall)
     - BE_TWO_STAGE_WALLS:
         * Estágio 1 (gatilho curto): reduz SL para logo atrás da Wall de entrada (Wall ∓ buf)
         * Estágio 2 (ao atingir a MidWall ou +260 pts): trava lucro atrás da MidWall (ou no BE + lock)
  2. PILAR 2 (Alvos Estruturais Reais nas MidWalls e Main Walls + Saídas Parciais):
     - TP_FIXED (Baseline): alvo fixo em pontos (400 pts)
     - TP_REAL_MIDWALL: 100% na coordenada exata da próxima MidWall (- front_run)
     - TP_REAL_MAIN_WALL: 100% na coordenada exata da próxima Main Wall (- front_run)
     - TP_PARTIAL_MID_MAIN: Realiza 50% na MidWall (- front_run) e carrega 50% até a Main Wall (- front_run)
       mantendo o Stop do lote final protegido atrás da Wall!
  3. PILAR 3 (Gatilhos de Entrada STOP e LIMIT nas Máximas/Mínimas das Barras Anteriores):
     - MKT_CLOSE (Baseline): entrada no fechamento da barra de sinal
     - STOP_PREV_BAR: Buy Stop na High[1] + off / Sell Stop na Low[1] - off (com filtro de distância máx. da Wall)
     - ROLLING_STOP_PREV_BAR: atualiza o Buy/Sell Stop barra a barra (High[1]/Low[1]) conforme o preço comprime na Wall
     - LIMIT_PREV_EXTREME: Buy Limit na Low[1] + off / Sell Limit na High[1] - off
     - LIMIT_PREV_MID50: Buy Limit em 50% da barra de sinal (desconto no pavio)
     - BRACKET_PA: Limit em 50% da barra[1] se recuar primeiro OU Stop na High[1]/Low[1] se romper direto
"""
import os
import sys
import time
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.discover_gex_nwe_setups import load_aligned_data, compute_nwe_series

OUT_DIR = os.path.join(ROOT_DIR, "data", "reports", "structural_walls_pa")
os.makedirs(OUT_DIR, exist_ok=True)


def find_structural_targets(entry_px: float, side: int, walls: np.ndarray, mid_walls: np.ndarray, all_lvls: np.ndarray, front_run: float = 20.0):
    """[ALINHADO MT5] Cópia exata de FindStructuralTargets() do Jumba_GEX_NWE_Core.mqh:
    mid = 1º nível (Wall ou MidWall) a >=135 pts; main = 1ª WALL a >=300 pts E além de mid+80."""
    walls = np.sort(np.asarray(walls, float))
    all_lvls = np.sort(np.asarray(all_lvls, float))
    r5 = lambda v: float(np.round(v / 5.0) * 5.0)
    if side == 1:
        ia = np.where(all_lvls >= entry_px + 135.0)[0]
        mid_i = int(ia[0]) if len(ia) else -1
        raw_mid = float(all_lvls[mid_i]) if mid_i >= 0 else entry_px + 460.0
        cw = walls[(walls >= entry_px + 300.0) & (walls > raw_mid + 80.0)]
        if len(cw):
            raw_main = float(cw[0])
        elif mid_i >= 0 and mid_i + 1 < len(all_lvls) and all_lvls[mid_i + 1] > raw_mid + 80.0:
            raw_main = float(all_lvls[mid_i + 1])
        else:
            raw_main = raw_mid + 480.0
        return r5(raw_mid - front_run), r5(raw_main - front_run), raw_mid, raw_main
    ia = np.where(all_lvls <= entry_px - 135.0)[0]
    mid_i = int(ia[-1]) if len(ia) else -1
    raw_mid = float(all_lvls[mid_i]) if mid_i >= 0 else entry_px - 460.0
    cw = walls[(walls <= entry_px - 300.0) & (walls < raw_mid - 80.0)]
    if len(cw):
        raw_main = float(cw[-1])
    elif mid_i > 0 and all_lvls[mid_i - 1] < raw_mid - 80.0:
        raw_main = float(all_lvls[mid_i - 1])
    else:
        raw_main = raw_mid - 480.0
    return r5(raw_mid + front_run), r5(raw_main + front_run), raw_mid, raw_main


def simulate_structural_setup(
    df_bars: pd.DataFrame,
    gex_by_date: dict,
    nwe_center: np.ndarray,
    nwe_upper: np.ndarray,
    nwe_lower: np.ndarray,
    nwe_slope: np.ndarray,
    rsi7s: np.ndarray,
    # Parâmetros de Sinal Base
    signal_mode: str = "HYBRID_WALL_NWE",
    prox_pct: float = 0.25,
    dist_touch: float = 65.0,
    # Pilar 3: Gatilho de Entrada (Barra Anterior)
    entry_type: str = "MKT_CLOSE",
    entry_off: float = 10.0,
    valid_bars: int = 2,
    max_stop_dist_wall: float = 135.0,
    # Pilar 1: Stop Inicial & Break-Even Protegido por Wall
    sl_init_pts: float = 230.0,
    be_mode: str = "BE_ZERO",  # "BE_ZERO", "BE_WALL_SHIELD", "BE_TWO_STAGE_WALLS"
    be_trigger_pts: float = 130.0,
    be_zero_lock: float = 20.0,
    wall_shield_buf: float = 25.0,  # Distância atrás da Wall (ex: Wall - 25 pts)
    stage2_trig_pts: float = 260.0,
    # Pilar 2: Alvos & Saídas Parciais nas Walls/MidWalls
    tp_mode: str = "TP_FIXED",  # "TP_FIXED", "TP_REAL_MIDWALL", "TP_REAL_MAIN_WALL", "TP_PARTIAL_MID_MAIN"
    tp_fixed_pts: float = 400.0,
    front_run_pts: float = 20.0,
    max_hold_bars: int = 18,
    cost_pts: float = 10.0,
):
    dates = df_bars["session_date"].values
    opens = df_bars["open"].values
    highs = df_bars["high"].values
    lows = df_bars["low"].values
    closes = df_bars["close"].values
    t_mins = df_bars["t_min"].values

    trades = []
    be_stops_count = 0
    wall_saves_count = 0
    partial_hits_count = 0

    n = len(df_bars)
    i = 2
    while i < n - 1:
        s_date = dates[i]
        if s_date < "2026-05-11" or s_date not in gex_by_date or dates[i - 1] != s_date:
            i += 1
            continue

        if not (550 <= t_mins[i] <= 990):
            i += 1
            continue

        g = gex_by_date[s_date]
        walls = g["walls"]
        mid_walls = g["mid_walls"]
        all_lvls = np.sort(np.concatenate([walls, mid_walls])) if len(mid_walls) > 0 else walls
        if len(all_lvls) == 0:
            i += 1
            continue

        o_s, h_s, l_s, c_s = opens[i], highs[i], lows[i], closes[i]
        u_s, lb_s, m_s, slp_s = nwe_upper[i], nwe_lower[i], nwe_center[i], nwe_slope[i]
        bw_s = u_s - lb_s

        sig_dir = 0
        def_wall_px = 0.0

        d_l = np.abs(all_lvls - l_s)
        idx_l = int(np.argmin(d_l))
        lvl_supp = float(all_lvls[idx_l])

        d_h = np.abs(all_lvls - h_s)
        idx_h = int(np.argmin(d_h))
        lvl_res = float(all_lvls[idx_h])

        touched_supp = (d_l[idx_l] <= dist_touch) and (c_s >= lvl_supp - 35.0) and ((c_s - lvl_supp) <= 95.0)
        touched_res = (d_h[idx_h] <= dist_touch) and (c_s <= lvl_res + 35.0) and ((lvl_res - c_s) <= 95.0)

        if signal_mode == "REVERSAL_NWE":
            if touched_supp and c_s <= (lb_s + bw_s * prox_pct) and rsi7s[i] <= 38.0:
                sig_dir = 1
                def_wall_px = lvl_supp
            elif touched_res and c_s >= (u_s - bw_s * prox_pct) and rsi7s[i] >= 62.0:
                sig_dir = -1
                def_wall_px = lvl_res

        elif signal_mode == "PULLBACK_SLOPE":
            if touched_supp and slp_s >= 7.0 and c_s <= (m_s + bw_s * 0.15) and c_s > lvl_supp:
                sig_dir = 1
                def_wall_px = lvl_supp
            elif touched_res and slp_s <= -7.0 and c_s >= (m_s - bw_s * 0.15) and c_s < lvl_res:
                sig_dir = -1
                def_wall_px = lvl_res

        else:  # HYBRID_WALL_NWE
            buy_rev = touched_supp and c_s <= (lb_s + bw_s * prox_pct) and rsi7s[i] <= 38.0
            buy_pb = touched_supp and slp_s >= 8.0 and c_s <= (m_s + bw_s * 0.15) and c_s > lvl_supp
            sell_rev = touched_res and c_s >= (u_s - bw_s * prox_pct) and rsi7s[i] >= 62.0
            sell_pb = touched_res and slp_s <= -8.0 and c_s >= (m_s - bw_s * 0.15) and c_s < lvl_res

            if buy_rev or buy_pb:
                sig_dir = 1
                def_wall_px = lvl_supp
            elif sell_rev or sell_pb:
                sig_dir = -1
                def_wall_px = lvl_res

        if sig_dir == 0:
            i += 1
            continue

        # ======================================================================
        # PILAR 3: EXECUÇÃO DO GATILHO DE ENTRADA (COM SEQUÊNCIA OHLC REALISTA)
        # ======================================================================
        entered = False
        entry_px = 0.0
        entry_bar_idx = i
        entry_order_kind = "MKT"  # "MKT", "LIMIT", "STOP"

        if entry_type == "MKT_CLOSE":
            entered = True
            entry_px = c_s
            entry_bar_idx = i
            entry_order_kind = "MKT"
        else:
            curr_ref_high = h_s
            curr_ref_low = l_s
            curr_ref_mid = 0.5 * (h_s + l_s)

            for k_wait in range(1, valid_bars + 1):
                b_idx = i + k_wait
                if b_idx >= n or dates[b_idx] != s_date or t_mins[b_idx] > 1000:
                    break

                ob, hb, lb, cb = opens[b_idx], highs[b_idx], lows[b_idx], closes[b_idx]

                if entry_type in ("STOP_PREV_BAR", "ROLLING_STOP_PREV_BAR"):
                    if sig_dir == 1:
                        stop_trig = curr_ref_high + entry_off
                        # Só apregoa Buy Stop se o gatilho não estiver longe demais da Wall de defesa
                        if (stop_trig - def_wall_px) <= max_stop_dist_wall and hb >= stop_trig:
                            entered = True
                            entry_px = max(ob, stop_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "STOP"
                            break
                        if entry_type == "ROLLING_STOP_PREV_BAR" and lb >= def_wall_px - 60.0:
                            curr_ref_high = min(curr_ref_high, hb)
                    else:
                        stop_trig = curr_ref_low - entry_off
                        if (def_wall_px - stop_trig) <= max_stop_dist_wall and lb <= stop_trig:
                            entered = True
                            entry_px = min(ob, stop_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "STOP"
                            break
                        if entry_type == "ROLLING_STOP_PREV_BAR" and hb <= def_wall_px + 60.0:
                            curr_ref_low = max(curr_ref_low, lb)

                elif entry_type == "LIMIT_PREV_EXTREME":
                    if sig_dir == 1:
                        lim_trig = curr_ref_low + entry_off
                        if lb <= lim_trig and ob >= lim_trig - 30.0:
                            entered = True
                            entry_px = min(ob, lim_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "LIMIT"
                            break
                    else:
                        lim_trig = curr_ref_high - entry_off
                        if hb >= lim_trig and ob <= lim_trig + 30.0:
                            entered = True
                            entry_px = max(ob, lim_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "LIMIT"
                            break

                elif entry_type == "LIMIT_PREV_MID50":
                    if sig_dir == 1:
                        lim_trig = curr_ref_mid
                        if lb <= lim_trig and ob >= lim_trig - 30.0:
                            entered = True
                            entry_px = min(ob, lim_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "LIMIT"
                            break
                    else:
                        lim_trig = curr_ref_mid
                        if hb >= lim_trig and ob <= lim_trig + 30.0:
                            entered = True
                            entry_px = max(ob, lim_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "LIMIT"
                            break

                elif entry_type == "BRACKET_PA":
                    if sig_dir == 1:
                        lim_trig = curr_ref_mid
                        stop_trig = curr_ref_high + 5.0
                        # Se barra abriu acima do limit e recuou até o limit primeiro
                        if lb <= lim_trig and ob >= lim_trig:
                            entered = True
                            entry_px = lim_trig
                            entry_bar_idx = b_idx
                            entry_order_kind = "LIMIT"
                            break
                        elif (stop_trig - def_wall_px) <= max_stop_dist_wall and hb >= stop_trig:
                            entered = True
                            entry_px = max(ob, stop_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "STOP"
                            break
                    else:
                        lim_trig = curr_ref_mid
                        stop_trig = curr_ref_low - 5.0
                        if hb >= lim_trig and ob <= lim_trig:
                            entered = True
                            entry_px = lim_trig
                            entry_bar_idx = b_idx
                            entry_order_kind = "LIMIT"
                            break
                        elif (def_wall_px - stop_trig) <= max_stop_dist_wall and lb <= stop_trig:
                            entered = True
                            entry_px = min(ob, stop_trig)
                            entry_bar_idx = b_idx
                            entry_order_kind = "STOP"
                            break

        if not entered:
            i += 1
            continue

        # ======================================================================
        # PILAR 1 & PILAR 2: DEFINIÇÃO DE ALVOS ESTRUTURAIS E GESTÃO DE STOP
        # ======================================================================
        tp_mid_px, tp_main_px, raw_mid_lvl, raw_main_lvl = find_structural_targets(
            entry_px, sig_dir, walls, mid_walls, all_lvls, front_run=front_run_pts
        )

        if tp_mode == "TP_FIXED":
            tp1_px = entry_px + tp_fixed_pts if sig_dir == 1 else entry_px - tp_fixed_pts
            tp2_px = tp1_px
            is_partial_mode = False
        elif tp_mode == "TP_REAL_MIDWALL":
            tp1_px = tp_mid_px
            tp2_px = tp_mid_px
            is_partial_mode = False
        elif tp_mode == "TP_REAL_MAIN_WALL":
            tp1_px = tp_main_px
            tp2_px = tp_main_px
            is_partial_mode = False
        elif tp_mode == "TP_PARTIAL_MID_MAIN":
            tp1_px = tp_mid_px
            tp2_px = tp_main_px
            is_partial_mode = True
        else:
            tp1_px = entry_px + tp_fixed_pts if sig_dir == 1 else entry_px - tp_fixed_pts
            tp2_px = tp1_px
            is_partial_mode = False

        curr_sl = entry_px - sl_init_pts if sig_dir == 1 else entry_px + sl_init_pts

        # Nível de Stop Protegido atrás da Wall (`shield_sl_stage1`):
        # Posiciona `wall_shield_buf` pontos atrás da Wall de defesa (`def_wall_px - wall_shield_buf` na compra),
        # garantindo que fique SEMPRE atrás da Wall (`<= def_wall_px - 10`) e reduza o risco inicial!
        if sig_dir == 1:
            shield_sl_stage1 = max(curr_sl + 40.0, min(def_wall_px - wall_shield_buf, entry_px - 15.0))
            shield_sl_stage2 = max(entry_px + 25.0, raw_mid_lvl - wall_shield_buf)
        else:
            shield_sl_stage1 = min(curr_sl - 40.0, max(def_wall_px + wall_shield_buf, entry_px + 15.0))
            shield_sl_stage2 = min(entry_px - 25.0, raw_mid_lvl + wall_shield_buf)

        stage1_active = False
        stage2_active = False
        partial_done = False
        partial_exit_px = 0.0
        final_exit_px = entry_px
        closed_on_entry_bar = False
        touched_zero_after_be = False
        bars_held = 0

        # Se entrou intrabar (LIMIT ou STOP), avalia apenas o restante da barra `entry_bar_idx` pós-preenchimento!
        if entry_order_kind in ("LIMIT", "STOP"):
            ob_e, hb_e, lb_e, cb_e = opens[entry_bar_idx], highs[entry_bar_idx], lows[entry_bar_idx], closes[entry_bar_idx]
            is_bull_bar = cb_e >= ob_e

            if sig_dir == 1:
                if entry_order_kind == "LIMIT":
                    # Na compra LIMIT, o preço desceu até `entry_px` (perto de lb_e).
                    # Pessimista: verificamos se a mínima `lb_e` violou `curr_sl`.
                    # Já a máxima `hb_e` só ocorreu DEPOIS da mínima `lb_e` se a barra fechou em alta (`is_bull_bar`),
                    # caso contrário o máximo pós-entrada na barra é apenas `cb_e`!
                    post_low = lb_e
                    post_high = hb_e if is_bull_bar else max(entry_px, cb_e)
                else:  # BUY STOP
                    # Na compra STOP, o preço subiu até `entry_px` (perto de hb_e).
                    # A mínima `lb_e` só ocorreu DEPOIS da máxima se a barra fechou de baixa (`not is_bull_bar`),
                    # caso contrário a mínima pós-entrada até o fechamento é `min(entry_px, cb_e)`!
                    post_low = lb_e if not is_bull_bar else min(entry_px, cb_e)
                    post_high = hb_e

                if post_low <= curr_sl:
                    final_exit_px = curr_sl
                    closed_on_entry_bar = True
                else:
                    if is_partial_mode and not partial_done and post_high >= tp1_px:
                        partial_done = True
                        partial_exit_px = tp1_px
                        partial_hits_count += 1
                        curr_sl = max(curr_sl, entry_px + be_zero_lock if be_mode == "BE_ZERO" else shield_sl_stage1)
                        stage1_active = True
                    if post_high >= tp2_px:
                        final_exit_px = tp2_px
                        closed_on_entry_bar = True
                    elif (post_high - entry_px) >= be_trigger_pts and not stage1_active:
                        stage1_active = True
                        curr_sl = max(curr_sl, entry_px + be_zero_lock if be_mode == "BE_ZERO" else shield_sl_stage1)
            else:  # VENDA
                if entry_order_kind == "LIMIT":
                    post_high = hb_e
                    post_low = lb_e if not is_bull_bar else min(entry_px, cb_e)
                else:  # SELL STOP
                    post_high = hb_e if is_bull_bar else max(entry_px, cb_e)
                    post_low = lb_e

                if post_high >= curr_sl:
                    final_exit_px = curr_sl
                    closed_on_entry_bar = True
                else:
                    if is_partial_mode and not partial_done and post_low <= tp1_px:
                        partial_done = True
                        partial_exit_px = tp1_px
                        partial_hits_count += 1
                        curr_sl = min(curr_sl, entry_px - be_zero_lock if be_mode == "BE_ZERO" else shield_sl_stage1)
                        stage1_active = True
                    if post_low <= tp2_px:
                        final_exit_px = tp2_px
                        closed_on_entry_bar = True
                    elif (entry_px - post_low) >= be_trigger_pts and not stage1_active:
                        stage1_active = True
                        curr_sl = min(curr_sl, entry_px - be_zero_lock if be_mode == "BE_ZERO" else shield_sl_stage1)

        j = entry_bar_idx + 1
        if not closed_on_entry_bar:
            while j < n and dates[j] == s_date:
                bars_held += 1
                hj, lj, cj = highs[j], lows[j], closes[j]

                if sig_dir == 1:
                    if stage1_active and lj <= entry_px + be_zero_lock and lj > curr_sl:
                        touched_zero_after_be = True

                    if lj <= curr_sl:
                        final_exit_px = curr_sl
                        if stage1_active:
                            be_stops_count += 1
                        break

                    if is_partial_mode and not partial_done and hj >= tp1_px:
                        partial_done = True
                        partial_exit_px = tp1_px
                        partial_hits_count += 1
                        stage1_active = True
                        curr_sl = max(curr_sl, entry_px + be_zero_lock if be_mode == "BE_ZERO" else shield_sl_stage1)

                    if hj >= tp2_px:
                        final_exit_px = tp2_px
                        break

                    fav = hj - entry_px
                    if not stage1_active and be_trigger_pts > 0 and fav >= be_trigger_pts:
                        stage1_active = True
                        if be_mode == "BE_ZERO":
                            curr_sl = max(curr_sl, entry_px + be_zero_lock)
                        else:
                            curr_sl = max(curr_sl, shield_sl_stage1)

                    if be_mode == "BE_TWO_STAGE_WALLS" and not stage2_active:
                        if fav >= stage2_trig_pts or cj > raw_mid_lvl + 10.0:
                            stage2_active = True
                            # No estágio 2, se já cruzou a MidWall, protege atrás da MidWall; senão no BE + lock
                            new_sl2 = shield_sl_stage2 if cj > raw_mid_lvl else (entry_px + be_zero_lock)
                            curr_sl = max(curr_sl, new_sl2)

                else:  # VENDA
                    if stage1_active and hj >= entry_px - be_zero_lock and hj < curr_sl:
                        touched_zero_after_be = True

                    if hj >= curr_sl:
                        final_exit_px = curr_sl
                        if stage1_active:
                            be_stops_count += 1
                        break

                    if is_partial_mode and not partial_done and lj <= tp1_px:
                        partial_done = True
                        partial_exit_px = tp1_px
                        partial_hits_count += 1
                        stage1_active = True
                        curr_sl = min(curr_sl, entry_px - be_zero_lock if be_mode == "BE_ZERO" else shield_sl_stage1)

                    if lj <= tp2_px:
                        final_exit_px = tp2_px
                        break

                    fav = entry_px - lj
                    if not stage1_active and be_trigger_pts > 0 and fav >= be_trigger_pts:
                        stage1_active = True
                        if be_mode == "BE_ZERO":
                            curr_sl = min(curr_sl, entry_px - be_zero_lock)
                        else:
                            curr_sl = min(curr_sl, shield_sl_stage1)

                    if be_mode == "BE_TWO_STAGE_WALLS" and not stage2_active:
                        if fav >= stage2_trig_pts or cj < raw_mid_lvl - 10.0:
                            stage2_active = True
                            new_sl2 = shield_sl_stage2 if cj < raw_mid_lvl else (entry_px - be_zero_lock)
                            curr_sl = min(curr_sl, new_sl2)

                if bars_held >= max_hold_bars or t_mins[j] >= 17 * 60 + 20:
                    final_exit_px = cj
                    break
                j += 1
            else:
                final_exit_px = closes[min(j, n - 1)]
        else:
            j = entry_bar_idx

        if is_partial_mode and partial_done:
            pts_leg1 = (partial_exit_px - entry_px) * sig_dir - cost_pts
            pts_leg2 = (final_exit_px - entry_px) * sig_dir - cost_pts
            net_pts_per_contract = 0.5 * pts_leg1 + 0.5 * pts_leg2
        else:
            net_pts_per_contract = (final_exit_px - entry_px) * sig_dir - cost_pts

        if touched_zero_after_be and net_pts_per_contract > 30.0:
            wall_saves_count += 1

        trades.append({
            "date": s_date,
            "side": int(sig_dir),
            "pnl_pts": net_pts_per_contract,
            "contracts": 2,
            "pnl_brl": net_pts_per_contract * 2 * 0.20,
            "partial_done": partial_done,
            "wall_saved": touched_zero_after_be and net_pts_per_contract > 30.0,
        })

        i = max(entry_bar_idx + 1, j + 1)

    return trades, {
        "be_stops": be_stops_count,
        "wall_saves": wall_saves_count,
        "partial_hits": partial_hits_count,
    }


def evaluate_config(trades, extra_stats, label, meta=None):
    if not trades:
        return None
    df_t = pd.DataFrame(trades)
    n_t = len(df_t)
    wins = df_t[df_t["pnl_brl"] > 0]
    losses = df_t[df_t["pnl_brl"] <= 0]
    wr = (len(wins) / n_t) * 100.0
    gw = wins["pnl_brl"].sum() if len(wins) > 0 else 0.0
    gl = abs(losses["pnl_brl"].sum()) if len(losses) > 0 else 1e-6
    pf = gw / gl if gl > 0 else 99.9

    cum_brl = df_t["pnl_brl"].cumsum().values
    peak = np.maximum.accumulate(np.insert(cum_brl, 0, 0.0))[1:]
    max_dd = float(np.max(peak - cum_brl)) if len(cum_brl) > 0 else 0.0
    tot_brl = float(cum_brl[-1])
    tot_pts_1c = float(df_t["pnl_pts"].sum())
    ret_dd = tot_brl / max_dd if max_dd > 0 else 99.9

    daily = df_t.groupby("date")["pnl_brl"].sum()
    sharpe = float((daily.mean() / daily.std()) * np.sqrt(252)) if len(daily) > 2 and daily.std() > 0 else 0.0

    row = {
        "Setup": label,
        "Trades": n_t,
        "WinRate": round(wr, 2),
        "PF": round(pf, 2),
        "NetPts_1C": round(tot_pts_1c, 0),
        "NetBRL_2C": round(tot_brl, 2),
        "MaxDD_2C": round(max_dd, 2),
        "Ret_DD": round(ret_dd, 2),
        "Sharpe": round(sharpe, 2),
        "AvgPts": round(float(df_t["pnl_pts"].mean()), 1),
        "WallSaves": extra_stats.get("wall_saves", 0),
        "PartialHits": extra_stats.get("partial_hits", 0),
    }
    if meta:
        row.update(meta)
    return row


def run_all_experiments():
    t0 = time.time()
    print("=" * 95)
    print("  ESTUDO DE OTIMIZAÇÃO ESTRUTURAL WIN$N: WALL-SHIELD BE + ALVOS WALLS + ENTRADAS PA BARRA[1]")
    print("=" * 95)

    df_bars, gex_by_date = load_aligned_data()
    closes = df_bars["close"].values
    nwe_c, nwe_u, nwe_l, _, nwe_slp = compute_nwe_series(closes, lookback=50, bw=5.0, mult=2.0)

    y = pd.Series(closes)
    dp = y.diff()
    gain = dp.clip(lower=0).rolling(7).mean()
    loss = (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6)
    rsi7s = (100.0 - (100.0 / (1.0 + (gain / loss)))).fillna(50.0).values

    # ==========================================================================
    # EXPERIMENTO 1: IMPACTO ISOLADO DO PILAR 1 (BREAK-EVEN NO ZERO vs ESCUDO DE WALL)
    # ==========================================================================
    print("\n" + "-" * 95)
    print("  EXPERIMENTO 1 (PILAR 1): BREAK-EVEN NO ZERO vs. STOP PARCIAL PROTEGIDO ATRÁS DA WALL")
    print("-" * 95)
    exp1_rows = []
    for be_mode in ["BE_ZERO", "BE_WALL_SHIELD", "BE_TWO_STAGE_WALLS"]:
        for buf in [15.0, 25.0, 40.0] if be_mode != "BE_ZERO" else [0.0]:
            for be_trig in [110.0, 140.0]:
                lbl = f"{be_mode}(trig={int(be_trig)}, buf={int(buf)})"
                tr, st = simulate_structural_setup(
                    df_bars, gex_by_date, nwe_c, nwe_u, nwe_l, nwe_slp, rsi7s,
                    signal_mode="HYBRID_WALL_NWE", entry_type="MKT_CLOSE",
                    sl_init_pts=230.0, be_mode=be_mode, be_trigger_pts=be_trig, wall_shield_buf=buf,
                    tp_mode="TP_PARTIAL_MID_MAIN", front_run_pts=20.0
                )
                exp1_rows.append(evaluate_config(tr, st, lbl))
    df_exp1 = pd.DataFrame(exp1_rows).sort_values("Ret_DD", ascending=False)
    df_exp1.to_csv(os.path.join(OUT_DIR, "exp1_be_wall_shield.csv"), index=False)
    print(df_exp1[["Setup", "Trades", "WinRate", "PF", "NetPts_1C", "NetBRL_2C", "MaxDD_2C", "Ret_DD", "Sharpe", "WallSaves"]].to_string(index=False))

    # ==========================================================================
    # EXPERIMENTO 2: IMPACTO ISOLADO DO PILAR 2 (ALVOS FIXOS vs. MIDWALL / MAIN WALL / PARCIAL)
    # ==========================================================================
    print("\n" + "-" * 95)
    print("  EXPERIMENTO 2 (PILAR 2): ALVO FIXO vs. COORDENADA REAL MIDWALL / MAIN WALL / SAÍDA PARCIAL")
    print("-" * 95)
    exp2_rows = []
    for tp_m in ["TP_FIXED", "TP_REAL_MIDWALL", "TP_REAL_MAIN_WALL", "TP_PARTIAL_MID_MAIN"]:
        for be_m in ["BE_ZERO", "BE_TWO_STAGE_WALLS"]:
            for fr in [15.0, 25.0] if tp_m != "TP_FIXED" else [0.0]:
                lbl = f"{tp_m}(fr={int(fr)}) + {be_m}"
                tr, st = simulate_structural_setup(
                    df_bars, gex_by_date, nwe_c, nwe_u, nwe_l, nwe_slp, rsi7s,
                    signal_mode="HYBRID_WALL_NWE", entry_type="MKT_CLOSE",
                    sl_init_pts=230.0, be_mode=be_m, be_trigger_pts=130.0, wall_shield_buf=25.0,
                    tp_mode=tp_m, tp_fixed_pts=400.0, front_run_pts=fr
                )
                exp2_rows.append(evaluate_config(tr, st, lbl))
    df_exp2 = pd.DataFrame(exp2_rows).sort_values("Ret_DD", ascending=False)
    df_exp2.to_csv(os.path.join(OUT_DIR, "exp2_structural_targets.csv"), index=False)
    print(df_exp2[["Setup", "Trades", "WinRate", "PF", "NetPts_1C", "NetBRL_2C", "MaxDD_2C", "Ret_DD", "Sharpe", "PartialHits", "WallSaves"]].to_string(index=False))

    # ==========================================================================
    # EXPERIMENTO 3: IMPACTO ISOLADO DO PILAR 3 (ENTRADAS STOP & LIMIT BARRA ANTERIOR)
    # ==========================================================================
    print("\n" + "-" * 95)
    print("  EXPERIMENTO 3 (PILAR 3): GATILHOS DE ENTRADA STOP & LIMIT NA MÁXIMA/MÍNIMA DA BARRA ANTERIOR")
    print("-" * 95)
    exp3_rows = []
    for ent_type in ["MKT_CLOSE", "STOP_PREV_BAR", "ROLLING_STOP_PREV_BAR", "LIMIT_PREV_EXTREME", "LIMIT_PREV_MID50", "BRACKET_PA"]:
        offs = [0.0] if ent_type in ("MKT_CLOSE", "LIMIT_PREV_MID50") else [5.0, 15.0]
        vbars = [1] if ent_type == "MKT_CLOSE" else [1, 2, 3]
        for off in offs:
            for vb in vbars:
                lbl = f"{ent_type}(off={int(off)}, vbars={vb})"
                tr, st = simulate_structural_setup(
                    df_bars, gex_by_date, nwe_c, nwe_u, nwe_l, nwe_slp, rsi7s,
                    signal_mode="HYBRID_WALL_NWE",
                    entry_type=ent_type, entry_off=off, valid_bars=vb,
                    sl_init_pts=230.0, be_mode="BE_TWO_STAGE_WALLS", be_trigger_pts=130.0, wall_shield_buf=25.0,
                    tp_mode="TP_PARTIAL_MID_MAIN", front_run_pts=20.0
                )
                exp3_rows.append(evaluate_config(tr, st, lbl))
    df_exp3 = pd.DataFrame(exp3_rows).sort_values("Ret_DD", ascending=False)
    df_exp3.to_csv(os.path.join(OUT_DIR, "exp3_prev_bar_entries.csv"), index=False)
    print(df_exp3[["Setup", "Trades", "WinRate", "PF", "NetPts_1C", "NetBRL_2C", "MaxDD_2C", "Ret_DD", "Sharpe", "AvgPts", "WallSaves"]].to_string(index=False))

    # ==========================================================================
    # EXPERIMENTO 4: BUSCA COMBINADA COMPLETA (GRID SEARCH DOS 3 PILARES JUNTOS)
    # ==========================================================================
    print("\n" + "-" * 95)
    print("  EXPERIMENTO 4: OTIMIZAÇÃO GLOBAL COMBINADA (ENTRADAS BARRA[1] + WALL-SHIELD BE + ALVOS WALLS)")
    print("-" * 95)
    grid_rows = []
    for sig_m in ["HYBRID_WALL_NWE", "REVERSAL_NWE", "PULLBACK_SLOPE"]:
        for ent_t in ["MKT_CLOSE", "STOP_PREV_BAR", "ROLLING_STOP_PREV_BAR", "LIMIT_PREV_MID50", "LIMIT_PREV_EXTREME", "BRACKET_PA"]:
            for be_m in ["BE_ZERO", "BE_WALL_SHIELD", "BE_TWO_STAGE_WALLS"]:
                for tp_m in ["TP_FIXED", "TP_REAL_MIDWALL", "TP_REAL_MAIN_WALL", "TP_PARTIAL_MID_MAIN"]:
                    for sl_p in [200.0, 240.0]:
                        for sh_buf in [15.0, 30.0] if be_m != "BE_ZERO" else [0.0]:
                            lbl = f"[{sig_m[:6]}|{ent_t}|SL={int(sl_p)}|{be_m}(buf={int(sh_buf)})|{tp_m}]"
                            tr, st = simulate_structural_setup(
                                df_bars, gex_by_date, nwe_c, nwe_u, nwe_l, nwe_slp, rsi7s,
                                signal_mode=sig_m,
                                entry_type=ent_t, entry_off=10.0, valid_bars=2,
                                sl_init_pts=sl_p, be_mode=be_m, be_trigger_pts=130.0, wall_shield_buf=sh_buf,
                                tp_mode=tp_m, tp_fixed_pts=400.0, front_run_pts=20.0
                            )
                            res = evaluate_config(tr, st, lbl, meta={
                                "SignalMode": sig_m,
                                "EntryType": ent_t,
                                "BEMode": be_m,
                                "TPMode": tp_m,
                                "SL": sl_p,
                                "ShieldBuf": sh_buf,
                            })
                            if res and res["Trades"] >= 45:
                                grid_rows.append(res)

    df_grid = pd.DataFrame(grid_rows).sort_values(["Ret_DD", "Sharpe", "NetPts_1C"], ascending=False)
    df_grid.to_csv(os.path.join(OUT_DIR, "exp4_full_combined_ranking.csv"), index=False)
    print("\nTOP 20 CONFIGURAÇÕES CAMPEÃS (ORDENADAS POR RETORNO / DRAWDOWN E SHARPE):")
    print(df_grid.head(20)[["Setup", "Trades", "WinRate", "PF", "NetPts_1C", "NetBRL_2C", "MaxDD_2C", "Ret_DD", "Sharpe", "AvgPts", "WallSaves"]].to_string(index=False))

    print("\nTOP 12 CAMPEÃS COM BREAK-EVEN PROTEGIDO PELA WALL (BE_TWO_STAGE_WALLS / BE_WALL_SHIELD):")
    df_shield = df_grid[df_grid["BEMode"] != "BE_ZERO"].sort_values(["Ret_DD", "Sharpe"], ascending=False)
    print(df_shield.head(12)[["Setup", "Trades", "WinRate", "PF", "NetPts_1C", "NetBRL_2C", "MaxDD_2C", "Ret_DD", "Sharpe", "AvgPts", "WallSaves"]].to_string(index=False))

    print("\nTOP 10 CONFIGURAÇÕES POR LUCRO TOTAL EM PONTOS (NetPts_1C):")
    df_by_pts = df_grid.sort_values(["NetPts_1C", "PF"], ascending=False)
    print(df_by_pts.head(10)[["Setup", "Trades", "WinRate", "PF", "NetPts_1C", "NetBRL_2C", "MaxDD_2C", "Ret_DD", "Sharpe", "AvgPts", "WallSaves"]].to_string(index=False))

    print(f"\nConcluído em {time.time() - t0:.1f}s. CSVs salvos em: {OUT_DIR}")


if __name__ == "__main__":
    run_all_experiments()
