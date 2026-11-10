"""
DISCOVERY ENGINE: NOVOS ROBÔS M15 E M2 (WALLS & MIDWALLS + NWE)
==============================================================
Busca de novos modelos quantitativos para preenchimento dos lotes vagos:
- WIN Vagos: EST-03, EST-05, EST-09, EST-10, EST-11
- WDO Vagos: WDO-01, WDO-03, WDO-04, WDO-05, WDO-08, WDO-12, WDO-13, WDO-14, WDO-16

Regras Fundamentais:
1. Sempre usa MagicWalls / MidWalls como base estrutural de entrada e saída.
2. Stop Loss estritamente ancorado atrás da Wall de defesa (def_wall - buf para COMPRA, def_wall + buf para VENDA).
3. Take Profit estritamente ancorado no próximo nível (MidWall ou Main Wall), com front-running.
4. Filtros NWE opcionais: Direção/Slope, Largura de Banda (volatilidade), Espaço livre (Room to Wall).
5. Custos B3 reais: R$ 2,00 por contrato no WIN (10 pts) e R$ 5,00 por contrato no WDO (0,5 pt).
"""

import os
import sys
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.mt5_loader import load_gex_csv, HIST_WIN, HIST_WDO
import research.discover_gex_nwe_setups as disc

START_DATE = "2026-05-11"
END_DATE = "2026-11-04"

WIN_COST_PTS = 10.0   # R$ 2,00
WDO_COST_PTS = 0.5    # R$ 5,00

def round_tick(val, asset):
    if asset == "WIN":
        return round(val / 5.0) * 5.0
    return round(val * 2.0) / 2.0

def load_tf_bars(asset: str, tf: str):
    p = os.path.join(ROOT_DIR, "data", "mt5_rates", f"mt5_{asset}_N_{tf}.csv")
    if not os.path.exists(p):
        raise FileNotFoundError(f"Arquivo {p} não encontrado!")
    df = pd.read_csv(p, parse_dates=["t"])
    df["session_date"] = df["t"].dt.strftime("%Y-%m-%d")
    df["t_min"] = df["t"].dt.hour * 60 + df["t"].dt.minute
    df = df[(df["session_date"] >= START_DATE) & (df["session_date"] <= END_DATE)].copy()
    # Horário operacional: 09:00 às 17:55
    df = df[(df["t_min"] >= 540) & (df["t_min"] <= 1075)].sort_values("t").reset_index(drop=True)
    return df

def find_structural_exit_levels(entry_px: float, side: int, all_lvls: np.ndarray, asset: str, min_tp_dist: float, front_run: float):
    """
    Retorna TP estrutural (próximo nível além da distância mínima) e confirmação.
    """
    all_lvls = np.sort(all_lvls)
    if side == 1:
        valid_tps = all_lvls[all_lvls >= entry_px + min_tp_dist]
        if len(valid_tps) == 0:
            return None
        raw_tp = valid_tps[0]
        tp_px = round_tick(raw_tp - front_run, asset)
        return tp_px
    else:
        valid_tps = all_lvls[all_lvls <= entry_px - min_tp_dist]
        if len(valid_tps) == 0:
            return None
        raw_tp = valid_tps[-1]
        tp_px = round_tick(raw_tp + front_run, asset)
        return tp_px

def run_simulation(
    df: pd.DataFrame,
    gex_data: dict,
    asset: str,
    tf: str,
    setup_name: str,
    nwe_series: dict,
    # Parâmetros de execução
    wall_buf: float,
    min_tp_dist: float,
    front_run: float,
    be_trigger_ratio: float = 0.50, # aciona BE quando atingir 50% do alvo
    be_lock_pts: float = 15.0,      # protege 15 pts no WIN / 1.0 pt no WDO
    time_window: tuple = (555, 1005), # 09:15 às 16:45
    use_nwe_slope: bool = False,
    nwe_slope_thresh: float = 0.0,
    min_nwe_bw: float = 0.0,
    max_hold_bars: int = 40,
):
    cost_pts = WIN_COST_PTS if asset == "WIN" else WDO_COST_PTS
    pt_val = 0.20 if asset == "WIN" else 10.0
    
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    dates = df["session_date"].values
    tmins = df["t_min"].values
    n = len(df)
    
    n_c = nwe_series["center"]
    n_u = nwe_series["upper"]
    n_l = nwe_series["lower"]
    n_s = nwe_series["slope"]
    n_bw = n_u - n_l
    
    trades = []
    in_pos = False
    side = 0
    ep = 0.0
    sl = 0.0
    tp = 0.0
    be_active = False
    def_wall = 0.0
    i_entry = 0
    last_trade_date = ""
    trades_today = 0
    
    # Tolerância de toque na Wall
    touch_tol = 45.0 if asset == "WIN" else 2.5
    if tf == "M2":
        touch_tol = 30.0 if asset == "WIN" else 1.5

    for i in range(2, n):
        d = dates[i]
        tm = tmins[i]
        
        if d != dates[i - 1]:
            trades_today = 0
            
        # 1. Gerenciamento de posição aberta
        if in_pos:
            cur_o = opens[i]
            cur_h = highs[i]
            cur_l = lows[i]
            bars_held = i - i_entry
            
            # Saída por fim de dia (17:40) ou limite de barras
            if tm >= 1060 or d != dates[i_entry] or bars_held >= max_hold_bars:
                exit_px = cur_o
                pnl = (exit_px - ep) * side - cost_pts
                trades.append({
                    "date": dates[i_entry],
                    "time": tmins[i_entry],
                    "side": side,
                    "ep": ep,
                    "xp": exit_px,
                    "pts": pnl,
                    "brl": round(pnl * pt_val, 2),
                    "reason": "EOD_TIME",
                    "bars": bars_held,
                })
                in_pos = False
                continue
            
            if side == 1:
                # Long
                # Break-Even estrutural
                if not be_active and cur_h >= ep + (tp - ep) * be_trigger_ratio:
                    be_active = True
                    # Move stop para além do ponto de entrada (lucro mínimo) ou def_wall
                    sl = max(sl, round_tick(ep + be_lock_pts, asset))
                
                # SL check
                if cur_l <= sl:
                    exit_px = sl
                    pnl = (exit_px - ep) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "side": 1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "SL_BE" if be_active else "SL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
                # TP check
                elif cur_h >= tp:
                    exit_px = tp
                    pnl = (exit_px - ep) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "side": 1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "TP_WALL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
            else:
                # Short
                # Break-Even estrutural
                if not be_active and cur_l <= ep - (ep - tp) * be_trigger_ratio:
                    be_active = True
                    sl = min(sl, round_tick(ep - be_lock_pts, asset))
                
                # SL check
                if cur_h >= sl:
                    exit_px = sl
                    pnl = (ep - exit_px) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "side": -1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "SL_BE" if be_active else "SL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue
                # TP check
                elif cur_l <= tp:
                    exit_px = tp
                    pnl = (ep - exit_px) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "time": tmins[i_entry],
                        "side": -1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "TP_WALL",
                        "bars": bars_held,
                    })
                    in_pos = False
                    continue

        # 2. Avaliação de Sinal de Entrada
        if not in_pos and (time_window[0] <= tm <= time_window[1]):
            gex = gex_data.get(d)
            if not gex:
                continue
            
            walls = gex["walls"]
            mid_walls = gex["mid_walls"]
            all_lvls = np.sort(np.unique(np.concatenate([walls, mid_walls])))
            if len(all_lvls) < 2:
                continue
            
            c_prev = closes[i - 1]
            o_prev = opens[i - 1]
            h_prev = highs[i - 1]
            l_prev = lows[i - 1]
            rng_prev = max(1e-5, h_prev - l_prev)
            body_prev = abs(c_prev - o_prev)
            top_wick = h_prev - max(c_prev, o_prev)
            bot_wick = min(c_prev, o_prev) - l_prev
            
            c_prev2 = closes[i - 2]
            o_prev2 = opens[i - 2]
            h_prev2 = highs[i - 2]
            l_prev2 = lows[i - 2]
            
            slp = n_s[i - 1]
            bw = n_bw[i - 1]
            
            if min_nwe_bw > 0 and bw < min_nwe_bw:
                continue
            
            entry_px = opens[i]
            sig_side = 0
            candidate_wall = 0.0
            
            # --- DEFINIÇÃO DOS SETUPS ---
            if setup_name == "M15_PINBAR_WALL" or setup_name == "M2_PINBAR_WALL":
                # Compra: Pavio inferior longo tocando Wall e fechando acima
                # Acha o nível mais próximo do low anterior
                dists_l = np.abs(all_lvls - l_prev)
                closest_l = all_lvls[np.argmin(dists_l)]
                if (bot_wick >= 0.40 * rng_prev) and (l_prev <= closest_l + touch_tol) and (c_prev > closest_l):
                    if not use_nwe_slope or slp >= -nwe_slope_thresh:
                        sig_side = 1
                        candidate_wall = closest_l
                
                # Venda: Pavio superior longo tocando Wall e fechando abaixo
                dists_h = np.abs(all_lvls - h_prev)
                closest_h = all_lvls[np.argmin(dists_h)]
                if (top_wick >= 0.40 * rng_prev) and (h_prev >= closest_h - touch_tol) and (c_prev < closest_h):
                    if not use_nwe_slope or slp <= nwe_slope_thresh:
                        sig_side = -1
                        candidate_wall = closest_h

            elif setup_name == "M15_ENGULFING_WALL" or setup_name == "M2_ENGULFING_WALL":
                # Compra: Barra 2 cai na Wall, Barra 1 engolfa para cima
                dists_l = np.abs(all_lvls - min(l_prev, l_prev2))
                closest_l = all_lvls[np.argmin(dists_l)]
                if c_prev2 < o_prev2 and c_prev > o_prev and c_prev > h_prev2 and (min(l_prev, l_prev2) <= closest_l + touch_tol):
                    if not use_nwe_slope or slp >= 0.0:
                        sig_side = 1
                        candidate_wall = closest_l
                
                # Venda: Barra 2 sobe na Wall, Barra 1 engolfa para baixo
                dists_h = np.abs(all_lvls - max(h_prev, h_prev2))
                closest_h = all_lvls[np.argmin(dists_h)]
                if c_prev2 > o_prev2 and c_prev < o_prev and c_prev < l_prev2 and (max(h_prev, h_prev2) >= closest_h - touch_tol):
                    if not use_nwe_slope or slp <= 0.0:
                        sig_side = -1
                        candidate_wall = closest_h

            elif setup_name == "M15_BREAKOUT_RETEST" or setup_name == "M2_BREAKOUT_RETEST":
                # Compra: Rompeu Wall e retesta como suporte
                dists_l = np.abs(all_lvls - l_prev)
                closest_l = all_lvls[np.argmin(dists_l)]
                if (c_prev > closest_l) and (l_prev <= closest_l + touch_tol) and (c_prev2 > closest_l):
                    if i >= 4 and any(closes[i-k] < closest_l for k in range(3, 6)):
                        if not use_nwe_slope or slp >= nwe_slope_thresh:
                            sig_side = 1
                            candidate_wall = closest_l
                
                # Venda: Rompeu Wall e retesta como resistência
                dists_h = np.abs(all_lvls - h_prev)
                closest_h = all_lvls[np.argmin(dists_h)]
                if (c_prev < closest_h) and (h_prev >= closest_h - touch_tol) and (c_prev2 < closest_h):
                    if i >= 4 and any(closes[i-k] > closest_h for k in range(3, 6)):
                        if not use_nwe_slope or slp <= -nwe_slope_thresh:
                            sig_side = -1
                            candidate_wall = closest_h

            elif setup_name == "M15_FAKEOUT_TRAP" or setup_name == "M2_FAKEOUT_TRAP":
                # Falso rompimento: fura a Wall mas falha e fecha rejeitando com força
                trap_dist = 50.0 if asset == "WIN" else 3.5
                if tf == "M2":
                    trap_dist = 30.0 if asset == "WIN" else 2.0
                
                dists_l = np.abs(all_lvls - l_prev)
                closest_l = all_lvls[np.argmin(dists_l)]
                if (l_prev <= closest_l - trap_dist) and (c_prev > closest_l + (10.0 if asset == "WIN" else 0.5)):
                    if not use_nwe_slope or slp >= -nwe_slope_thresh:
                        sig_side = 1
                        candidate_wall = closest_l
                
                dists_h = np.abs(all_lvls - h_prev)
                closest_h = all_lvls[np.argmin(dists_h)]
                if (h_prev >= closest_h + trap_dist) and (c_prev < closest_h - (10.0 if asset == "WIN" else 0.5)):
                    if not use_nwe_slope or slp <= nwe_slope_thresh:
                        sig_side = -1
                        candidate_wall = closest_h

            elif setup_name == "M15_MIDWALL_TREND" or setup_name == "M2_MIDWALL_TREND":
                # Pullback na MidWall a favor do forte slope NWE
                dists = np.abs(mid_walls - c_prev)
                if len(dists) > 0:
                    closest_mid = mid_walls[np.argmin(dists)]
                    if abs(c_prev - closest_mid) <= touch_tol:
                        if slp >= nwe_slope_thresh and c_prev >= closest_mid:
                            sig_side = 1
                            candidate_wall = closest_mid
                        elif slp <= -nwe_slope_thresh and c_prev <= closest_mid:
                            sig_side = -1
                            candidate_wall = closest_mid

            elif setup_name == "M2_LUNCH_FADE":
                # Almoço 12:00 às 14:30: Reversão extrema da Wall em direção à MidWall central
                if 720 <= tm <= 870:
                    dists_w = np.abs(walls - c_prev)
                    if len(dists_w) > 0:
                        closest_w = walls[np.argmin(dists_w)]
                        if abs(c_prev - closest_w) <= touch_tol:
                            if c_prev > n_c[i - 1] and top_wick >= 0.35 * rng_prev:
                                sig_side = -1
                                candidate_wall = closest_w
                            elif c_prev < n_c[i - 1] and bot_wick >= 0.35 * rng_prev:
                                sig_side = 1
                                candidate_wall = closest_w

            # 3. Validação Estrutural Rigorosa de Stop e Alvo pelas Walls
            if sig_side != 0:
                tp_target = find_structural_exit_levels(entry_px, sig_side, all_lvls, asset, min_tp_dist, front_run)
                if tp_target is None:
                    continue
                
                # O Stop deve ser protegido atrás da Wall de defesa
                if sig_side == 1:
                    # Compra: a Wall de defesa DEVE estar abaixo ou no preço de entrada
                    def_levels = all_lvls[all_lvls <= entry_px]
                    if len(def_levels) == 0:
                        continue
                    # A Wall de defesa mais próxima abaixo do preço
                    def_wall_level = def_levels[-1]
                    sl_target = round_tick(def_wall_level - wall_buf, asset)
                    
                    # Verificação de sanidade do stop de compra
                    if sl_target >= entry_px:
                        sl_target = round_tick(entry_px - (150.0 if asset == "WIN" else 8.0), asset)
                    
                    risk = entry_px - sl_target
                    reward = tp_target - entry_px
                    if risk <= 0 or reward < risk * 0.75: # Payoff mínimo aceitável
                        continue
                    # Filtro de stop máximo tolerável (evita stops gigantescos se a wall estiver muito longe)
                    max_allowed_sl = 450.0 if asset == "WIN" else 22.0
                    if risk > max_allowed_sl:
                        continue
                else:
                    # Venda: a Wall de defesa DEVE estar acima ou no preço de entrada
                    def_levels = all_lvls[all_lvls >= entry_px]
                    if len(def_levels) == 0:
                        continue
                    def_wall_level = def_levels[0]
                    sl_target = round_tick(def_wall_level + wall_buf, asset)
                    
                    if sl_target <= entry_px:
                        sl_target = round_tick(entry_px + (150.0 if asset == "WIN" else 8.0), asset)
                        
                    risk = sl_target - entry_px
                    reward = entry_px - tp_target
                    if risk <= 0 or reward < risk * 0.75:
                        continue
                    max_allowed_sl = 450.0 if asset == "WIN" else 22.0
                    if risk > max_allowed_sl:
                        continue

                # Entrada confirmada
                in_pos = True
                side = sig_side
                ep = entry_px
                sl = sl_target
                tp = tp_target
                def_wall = def_wall_level
                be_active = False
                i_entry = i
                trades_today += 1

    return trades

def compute_metrics(trades):
    if not trades:
        return {"tr": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "mdd": 0.0, "ret_dd": 0.0, "avg": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t["brl"] > 0)
    wr = round(wins / n * 100.0, 1)
    gw = sum(t["brl"] for t in trades if t["brl"] > 0)
    gl = abs(sum(t["brl"] for t in trades if t["brl"] < 0))
    pf = round(gw / gl, 2) if gl > 0 else 99.9
    net = round(sum(t["brl"] for t in trades), 2)
    avg = round(net / n, 2)
    
    by_day = {}
    for t in trades:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + t["brl"]
    cum = np.cumsum([by_day[d] for d in sorted(by_day.keys())])
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    mdd = round(float(np.max(pk - cum)), 2) if len(cum) else 0.0
    ret_dd = round(net / mdd, 2) if mdd > 0 else 99.9
    return {"tr": n, "wr": wr, "pf": pf, "net": net, "mdd": mdd, "ret_dd": ret_dd, "avg": avg}

def main():
    print("=" * 110)
    print("  SIMULADOR DE DESCOBERTA QUANT: PREENCHIMENTO DOS LOTES VAGOS (M15 E M2)")
    print("=" * 110)
    
    gex_win = load_gex_csv(HIST_WIN)
    gex_wdo = load_gex_csv(HIST_WDO)
    
    configs = [
        # (asset, tf, setup_name, wall_buf, min_tp_dist, front_run, be_ratio, be_lock, time_window, use_nwe, slope_th, min_bw, hold)
        # --- WIN M15 ---
        ("WIN", "M15", "M15_PINBAR_WALL", 35.0, 180.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WIN", "M15", "M15_PINBAR_WALL", 35.0, 180.0, 20.0, 0.50, 25.0, (555, 1005), True, 2.0, 300.0, 32),
        ("WIN", "M15", "M15_ENGULFING_WALL", 35.0, 220.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WIN", "M15", "M15_ENGULFING_WALL", 35.0, 220.0, 20.0, 0.50, 25.0, (555, 1005), True, 3.0, 300.0, 32),
        ("WIN", "M15", "M15_BREAKOUT_RETEST", 30.0, 250.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WIN", "M15", "M15_BREAKOUT_RETEST", 30.0, 250.0, 20.0, 0.50, 25.0, (555, 1005), True, 4.0, 0.0, 32),
        ("WIN", "M15", "M15_FAKEOUT_TRAP", 30.0, 220.0, 20.0, 0.50, 25.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WIN", "M15", "M15_FAKEOUT_TRAP", 30.0, 220.0, 20.0, 0.50, 25.0, (555, 1005), True, 2.0, 0.0, 32),
        ("WIN", "M15", "M15_MIDWALL_TREND", 35.0, 250.0, 20.0, 0.50, 25.0, (555, 1005), True, 5.0, 350.0, 32),
        
        # --- WIN M2 ---
        ("WIN", "M2", "M2_PINBAR_WALL", 25.0, 120.0, 15.0, 0.50, 20.0, (555, 1005), False, 0.0, 0.0, 45),
        ("WIN", "M2", "M2_PINBAR_WALL", 25.0, 120.0, 15.0, 0.50, 20.0, (555, 1005), True, 1.5, 250.0, 45),
        ("WIN", "M2", "M2_ENGULFING_WALL", 25.0, 140.0, 15.0, 0.50, 20.0, (555, 1005), False, 0.0, 0.0, 45),
        ("WIN", "M2", "M2_ENGULFING_WALL", 25.0, 140.0, 15.0, 0.50, 20.0, (555, 1005), True, 2.0, 250.0, 45),
        ("WIN", "M2", "M2_BREAKOUT_RETEST", 25.0, 160.0, 15.0, 0.50, 20.0, (555, 1005), True, 2.5, 0.0, 45),
        ("WIN", "M2", "M2_FAKEOUT_TRAP", 25.0, 140.0, 15.0, 0.50, 20.0, (555, 1005), False, 0.0, 0.0, 45),
        ("WIN", "M2", "M2_FAKEOUT_TRAP", 25.0, 140.0, 15.0, 0.50, 20.0, (555, 1005), True, 1.5, 0.0, 45),
        ("WIN", "M2", "M2_LUNCH_FADE", 25.0, 150.0, 15.0, 0.50, 20.0, (720, 870), False, 0.0, 0.0, 45),
        
        # --- WDO M15 ---
        ("WDO", "M15", "M15_PINBAR_WALL", 2.0, 5.5, 1.0, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WDO", "M15", "M15_PINBAR_WALL", 2.0, 5.5, 1.0, 0.50, 1.0, (555, 1005), True, 0.15, 8.0, 32),
        ("WDO", "M15", "M15_ENGULFING_WALL", 2.0, 6.5, 1.0, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WDO", "M15", "M15_ENGULFING_WALL", 2.0, 6.5, 1.0, 0.50, 1.0, (555, 1005), True, 0.20, 8.0, 32),
        ("WDO", "M15", "M15_BREAKOUT_RETEST", 2.0, 7.0, 1.0, 0.50, 1.0, (555, 1005), True, 0.25, 0.0, 32),
        ("WDO", "M15", "M15_FAKEOUT_TRAP", 2.0, 6.0, 1.0, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 32),
        ("WDO", "M15", "M15_FAKEOUT_TRAP", 2.0, 6.0, 1.0, 0.50, 1.0, (555, 1005), True, 0.15, 0.0, 32),
        ("WDO", "M15", "M15_MIDWALL_TREND", 2.0, 7.5, 1.0, 0.50, 1.0, (555, 1005), True, 0.30, 9.0, 32),
        
        # --- WDO M2 ---
        ("WDO", "M2", "M2_PINBAR_WALL", 1.5, 4.5, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 45),
        ("WDO", "M2", "M2_PINBAR_WALL", 1.5, 4.5, 0.5, 0.50, 1.0, (555, 1005), True, 0.10, 6.0, 45),
        ("WDO", "M2", "M2_ENGULFING_WALL", 1.5, 5.0, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 45),
        ("WDO", "M2", "M2_ENGULFING_WALL", 1.5, 5.0, 0.5, 0.50, 1.0, (555, 1005), True, 0.15, 6.0, 45),
        ("WDO", "M2", "M2_BREAKOUT_RETEST", 1.5, 5.5, 0.5, 0.50, 1.0, (555, 1005), True, 0.20, 0.0, 45),
        ("WDO", "M2", "M2_FAKEOUT_TRAP", 1.5, 4.5, 0.5, 0.50, 1.0, (555, 1005), False, 0.0, 0.0, 45),
        ("WDO", "M2", "M2_FAKEOUT_TRAP", 1.5, 4.5, 0.5, 0.50, 1.0, (555, 1005), True, 0.10, 0.0, 45),
        ("WDO", "M2", "M2_LUNCH_FADE", 1.5, 5.0, 0.5, 0.50, 1.0, (720, 870), False, 0.0, 0.0, 45),
    ]

    # Cache de dados por ativo e timeframe
    dfs = {}
    nwes = {}
    for a in ["WIN", "WDO"]:
        for tf in ["M15", "M2"]:
            print(f"Carregando e calculando NWE para {a} {tf}...")
            df = load_tf_bars(a, tf)
            dfs[(a, tf)] = df
            closes = df["close"].values
            lookback = 30 if tf == "M15" else 60
            bw = 4.0 if tf == "M15" else 6.0
            mult = 1.8 if tf == "M15" else 2.2
            c, u, l, _, s = disc.compute_nwe_series(closes, lookback=lookback, bw=bw, mult=mult)
            nwes[(a, tf)] = {"center": c, "upper": u, "lower": l, "slope": s}

    print("\nExecutando simulações de backtest...\n")
    print(f"{'ATIVO':<5} {'TF':<4} {'SETUP':<22} {'FILTRO NWE':<14} {'TR':>4} {'WR%':>6} {'PF':>5} {'LUCRO (R$)':>12} {'MAX DD':>10} {'RET/DD':>7} {'AVG/TR':>8}")
    print("-" * 110)

    results = []
    for cfg in configs:
        asset, tf, setup_name, wall_buf, min_tp_dist, front_run, be_ratio, be_lock, time_window, use_nwe, slope_th, min_bw, hold = cfg
        gex_data = gex_win if asset == "WIN" else gex_wdo
        df = dfs[(asset, tf)]
        nwe_s = nwes[(asset, tf)]
        
        trades = run_simulation(
            df=df,
            gex_data=gex_data,
            asset=asset,
            tf=tf,
            setup_name=setup_name,
            nwe_series=nwe_s,
            wall_buf=wall_buf,
            min_tp_dist=min_tp_dist,
            front_run=front_run,
            be_trigger_ratio=be_ratio,
            be_lock_pts=be_lock,
            time_window=time_window,
            use_nwe_slope=use_nwe,
            nwe_slope_thresh=slope_th,
            min_nwe_bw=min_bw,
            max_hold_bars=hold,
        )
        
        m = compute_metrics(trades)
        filter_label = f"Slope>={slope_th}" if use_nwe else "Sem NWE"
        if min_bw > 0:
            filter_label += f"+BW>{min_bw:.0f}"
            
        print(f"{asset:<5} {tf:<4} {setup_name:<22} {filter_label:<14} {m['tr']:>4d} {m['wr']:>5.1f}% {m['pf']:>5.2f} {m['net']:>12.2f} {m['mdd']:>10.2f} {m['ret_dd']:>6.2f}x {m['avg']:>8.2f}")
        results.append({
            "asset": asset,
            "tf": tf,
            "setup": setup_name,
            "filter": filter_label,
            **m,
            "trades": trades
        })

    # Resumo dos Top Candidatos por Ativo
    for a in ["WIN", "WDO"]:
        print(f"\n=======================================================")
        print(f"  TOP CANDIDATOS SELECIONADOS PARA LOTES VAGOS: {a}")
        print(f"=======================================================")
        cands = [r for r in results if r["asset"] == a and r["tr"] >= 30 and r["pf"] >= 1.30 and r["net"] > 0]
        cands.sort(key=lambda x: x["ret_dd"], reverse=True)
        for i, c in enumerate(cands[:6], 1):
            print(f"  #{i} [{c['tf']}] {c['setup']} ({c['filter']}): {c['tr']} tr | WR {c['wr']}% | PF {c['pf']} | Net R$ {c['net']:.2f} | DD R$ {c['mdd']:.2f} | Ret/DD {c['ret_dd']:.2f}x | Avg R$ {c['avg']:.2f}")

if __name__ == "__main__":
    main()

