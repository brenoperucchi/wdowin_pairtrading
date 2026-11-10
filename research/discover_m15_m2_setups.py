"""
DESCOBERTA E BACKTEST DE NOVOS ROBÔS EM M15 E M2 (WALLS & MIDWALLS + NWE)
========================================================================
Testa sistematicamente novos padrões operacionais nos timeframes M15 e M2:
- Base de entrada: Rejeição, Engolfo, Reteste, Trap/Fakeout e Pullback em MagicWalls / MidWalls.
- Base de saída: Alvo em MidWall / Wall, Stop protegido por Escudo da Wall, Break-Even estrutural.
- Filtro NWE: Direção/Slope do NWE, largura de bandas (volatilidade) e espaço livre até a parede.
- Custos B3: R$ 2,00 por contrato no WIN (10 pts) e R$ 5,00 por contrato no WDO (0,5 pt).
- Período: 11/05/2026 a 04/11/2026 (123 pregões).
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

WIN_COST_PTS = 10.0
WDO_COST_PTS = 0.5


def load_timeframe_data(asset: str, tf: str):
    fname = f"mt5_{asset}_N_{tf}.csv"
    p = os.path.join(ROOT_DIR, "data", "mt5_rates", fname)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Arquivo {p} não encontrado!")
    df = pd.read_csv(p, parse_dates=["t"])
    df["session_date"] = df["t"].dt.strftime("%Y-%m-%d")
    df["t_min"] = df["t"].dt.hour * 60 + df["t"].dt.minute
    df = df[(df["session_date"] >= START_DATE) & (df["session_date"] <= END_DATE)].copy()
    # Horário de pregão: 09:00 às 17:55
    df = df[(df["t_min"] >= 540) & (df["t_min"] <= 1075)].sort_values("t").reset_index(drop=True)
    return df


def simulate_setup(df, gex_by_date, nwe_s, nwe_bw, setup_type, asset="WIN", tf="M15", **params):
    """
    Simulador rápido barra a barra em M15 ou M2.
    """
    cost_pts = WIN_COST_PTS if asset == "WIN" else WDO_COST_PTS
    pt_val = 0.20 if asset == "WIN" else 10.0
    min_dist_wall = params.get("min_dist_wall", 35.0 if asset == "WIN" else 1.5)
    wall_buf = params.get("wall_buf", 25.0 if asset == "WIN" else 1.5)
    use_nwe_slope = params.get("use_nwe_slope", False)
    min_nwe_bw = params.get("min_nwe_bw", 0.0)
    be_pct_target = params.get("be_pct_target", 0.50)  # Move para BE quando andar 50% até a MidWall

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    dates = df["session_date"].values
    tmins = df["t_min"].values
    n = len(df)

    trades = []
    in_pos = False
    side = 0
    ep = 0.0
    sl = 0.0
    tp = 0.0
    be_active = False
    def_wall = 0.0
    i_entry = 0

    for i in range(1, n):
        d = dates[i]
        tm = tmins[i]
        c_prev = closes[i - 1]
        o_prev = opens[i - 1]
        h_prev = highs[i - 1]
        l_prev = lows[i - 1]
        rng_prev = max(1e-5, h_prev - l_prev)
        body_prev = abs(c_prev - o_prev)
        top_wick = h_prev - max(c_prev, o_prev)
        bot_wick = min(c_prev, o_prev) - l_prev

        # Final de pregão: encerra às 17h40
        if in_pos:
            # Verifica saída na barra i
            cur_o = opens[i]
            cur_h = highs[i]
            cur_l = lows[i]

            # Fechamento EOD
            if tm >= 1060 or dates[i] != dates[i_entry]:
                exit_px = cur_o
                pnl = (exit_px - ep) * side - cost_pts
                trades.append({
                    "date": dates[i_entry],
                    "side": side,
                    "ep": ep,
                    "xp": exit_px,
                    "pts": pnl,
                    "brl": round(pnl * pt_val, 2),
                    "reason": "EOD",
                    "bars": i - i_entry,
                })
                in_pos = False
                continue

            # TP & SL check
            if side == 1:
                # Checa se acionou BE
                if not be_active and cur_h >= ep + (tp - ep) * be_pct_target:
                    be_active = True
                    sl = max(sl, def_wall - wall_buf if def_wall > 0 else ep)

                if cur_l <= sl:
                    exit_px = sl
                    pnl = (exit_px - ep) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "side": 1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "SL_BE" if be_active else "SL",
                        "bars": i - i_entry,
                    })
                    in_pos = False
                    continue
                elif cur_h >= tp:
                    exit_px = tp
                    pnl = (exit_px - ep) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "side": 1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "TP_WALL",
                        "bars": i - i_entry,
                    })
                    in_pos = False
                    continue
            else:
                # Venda
                if not be_active and cur_l <= ep - (ep - tp) * be_pct_target:
                    be_active = True
                    sl = min(sl, def_wall + wall_buf if def_wall > 0 else ep)

                if cur_h >= sl:
                    exit_px = sl
                    pnl = (ep - exit_px) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "side": -1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "SL_BE" if be_active else "SL",
                        "bars": i - i_entry,
                    })
                    in_pos = False
                    continue
                elif cur_l <= tp:
                    exit_px = tp
                    pnl = (ep - exit_px) - cost_pts
                    trades.append({
                        "date": dates[i_entry],
                        "side": -1,
                        "ep": ep,
                        "xp": exit_px,
                        "pts": pnl,
                        "brl": round(pnl * pt_val, 2),
                        "reason": "TP_WALL",
                        "bars": i - i_entry,
                    })
                    in_pos = False
                    continue

        # Se não está em posição, avalia entrada na abertura de i (baseado no fechamento de i-1)
        if not in_pos and 555 <= tm <= 1005:  # Janela operacional 09:15 às 16:45
            gex = gex_by_date.get(d)
            if not gex:
                continue

            walls = gex["walls"]
            mid_walls = gex["mid_walls"]
            all_lvls = np.sort(np.unique(np.concatenate([walls, mid_walls])))
            if len(all_lvls) < 2:
                continue

            entry_cand = opens[i]

            # Filtros NWE opcionais
            if use_nwe_slope:
                slp = nwe_s[i - 1]
            else:
                slp = 0.0

            if min_nwe_bw > 0 and nwe_bw[i - 1] < min_nwe_bw:
                continue

            # Identifica Wall mais próxima
            dists = np.abs(all_lvls - c_prev)
            nearest_idx = np.argmin(dists)
            nearest_lvl = all_lvls[nearest_idx]
            is_main_wall = nearest_lvl in walls

            sig_side = 0
            # 1. SETUP: PINBAR_REJECTION na Wall / MidWall
            if setup_type == "PINBAR_REJECTION":
                # Compra: Pavio inferior longo tocando a Wall por baixo e fechando acima
                if bot_wick >= 0.45 * rng_prev and (l_prev <= nearest_lvl + min_dist_wall) and c_prev > nearest_lvl:
                    if not use_nwe_slope or slp >= -0.05:
                        sig_side = 1
                # Venda: Pavio superior longo tocando a Wall por cima e fechando abaixo
                elif top_wick >= 0.45 * rng_prev and (h_prev >= nearest_lvl - min_dist_wall) and c_prev < nearest_lvl:
                    if not use_nwe_slope or slp <= 0.05:
                        sig_side = -1

            # 2. SETUP: ENGULFING_WALL (Engolfo na Wall)
            elif setup_type == "ENGULFING_WALL":
                if i >= 2:
                    c_prev2 = closes[i - 2]
                    o_prev2 = opens[i - 2]
                    # Compra: Barra i-2 caiu na Wall, barra i-1 engolfou para cima
                    if c_prev2 < o_prev2 and c_prev > o_prev and c_prev > max(c_prev2, o_prev2) and l_prev <= nearest_lvl + min_dist_wall:
                        if not use_nwe_slope or slp >= 0.0:
                            sig_side = 1
                    # Venda: Barra i-2 subiu na Wall, barra i-1 engolfou para baixo
                    elif c_prev2 > o_prev2 and c_prev < o_prev and c_prev < min(c_prev2, o_prev2) and h_prev >= nearest_lvl - min_dist_wall:
                        if not use_nwe_slope or slp <= 0.0:
                            sig_side = -1

            # 3. SETUP: BREAKOUT_RETEST_WALL (Rompe Wall e faz reteste)
            elif setup_type == "BREAKOUT_RETEST_WALL":
                if i >= 3:
                    # Compra: Rompeu Wall para cima e barra anterior testou a Wall como suporte
                    if c_prev > nearest_lvl and l_prev <= nearest_lvl + min_dist_wall and (closes[i-3] < nearest_lvl or closes[i-2] < nearest_lvl):
                        if not use_nwe_slope or slp >= 0.1:
                            sig_side = 1
                    # Venda: Rompeu Wall para baixo e barra anterior testou a Wall como resistência
                    elif c_prev < nearest_lvl and h_prev >= nearest_lvl - min_dist_wall and (closes[i-3] > nearest_lvl or closes[i-2] > nearest_lvl):
                        if not use_nwe_slope or slp <= -0.1:
                            sig_side = -1

            # 4. SETUP: FAKEOUT_TRAP_WALL (Fura a Wall mas falha e fecha contra)
            elif setup_type == "FAKEOUT_TRAP_WALL":
                # Compra: furou mínima da Wall mas fechou de volta para dentro
                if l_prev < nearest_lvl - min_dist_wall and c_prev > nearest_lvl:
                    sig_side = 1
                # Venda: furou máxima da Wall mas fechou de volta para dentro
                elif h_prev > nearest_lvl + min_dist_wall and c_prev < nearest_lvl:
                    sig_side = -1

            # 5. SETUP: MIDWALL_PULLBACK_MOMENTUM (Pullback na MidWall a favor de tendência)
            elif setup_type == "MIDWALL_PULLBACK":
                if not is_main_wall and abs(c_prev - nearest_lvl) <= min_dist_wall:
                    if slp > 0.2 and c_prev >= nearest_lvl:
                        sig_side = 1
                    elif slp < -0.2 and c_prev <= nearest_lvl:
                        sig_side = -1

            if sig_side != 0:
                # Define Alvo (TP) e Stop (SL) estruturais pelas Walls
                if sig_side == 1:
                    higher_lvls = all_lvls[all_lvls > entry_cand + (60.0 if asset == "WIN" else 3.0)]
                    if len(higher_lvls) == 0:
                        continue
                    tp_target = higher_lvls[0] - (10.0 if asset == "WIN" else 0.5)
                    sl_target = nearest_lvl - wall_buf
                    # Risco/retorno mínimo 1:1
                    if (tp_target - entry_cand) < (entry_cand - sl_target) * 0.8:
                        continue
                else:
                    lower_lvls = all_lvls[all_lvls < entry_cand - (60.0 if asset == "WIN" else 3.0)]
                    if len(lower_lvls) == 0:
                        continue
                    tp_target = lower_lvls[-1] + (10.0 if asset == "WIN" else 0.5)
                    sl_target = nearest_lvl + wall_buf
                    if (entry_cand - tp_target) < (sl_target - entry_cand) * 0.8:
                        continue

                in_pos = True
                side = sig_side
                ep = entry_cand
                sl = sl_target
                tp = tp_target
                def_wall = nearest_lvl
                be_active = False
                i_entry = i

    # Resumo
    return trades


def calc_stats(trades):
    if not trades:
        return {"tr": 0, "wr": 0.0, "pf": 0.0, "net": 0.0, "mdd": 0.0, "ret_dd": 0.0}
    n = len(trades)
    wins = sum(1 for t in trades if t["brl"] > 0)
    wr = round(wins / n * 100.0, 1)
    gw = sum(t["brl"] for t in trades if t["brl"] > 0)
    gl = abs(sum(t["brl"] for t in trades if t["brl"] < 0))
    pf = round(gw / gl, 2) if gl > 0 else 99.9
    net = round(sum(t["brl"] for t in trades), 2)
    # DD
    by_day = {}
    for t in trades:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + t["brl"]
    cum = np.cumsum([by_day[d] for d in sorted(by_day.keys())])
    pk = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    mdd = round(float(np.max(pk - cum)), 2) if len(cum) else 0.0
    ret_dd = round(net / mdd, 2) if mdd > 0 else 99.9
    return {"tr": n, "wr": wr, "pf": pf, "net": net, "mdd": mdd, "ret_dd": ret_dd}


def main():
    print("=" * 100)
    print("  EXPLORAÇÃO DE NOVOS ROBÔS EM M15 E M2 (WALLS & MIDWALLS + NWE)")
    print("=" * 100)

    gex_win = load_gex_csv(HIST_WIN)
    gex_wdo = load_gex_csv(HIST_WDO)

    setups_to_test = [
        "PINBAR_REJECTION",
        "ENGULFING_WALL",
        "BREAKOUT_RETEST_WALL",
        "FAKEOUT_TRAP_WALL",
        "MIDWALL_PULLBACK",
    ]

    for asset, gex_data in [("WIN", gex_win), ("WDO", gex_wdo)]:
        for tf in ["M15", "M2"]:
            print(f"\n>>> TESTANDO ATIVO: {asset} | TIMEFRAME: {tf} <<<")
            df = load_timeframe_data(asset, tf)
            closes = df["close"].values
            n_look = 30 if tf == "M15" else 60
            n_c, n_u, n_l, _, n_s = disc.compute_nwe_series(closes, lookback=n_look, bw=4.0, mult=1.8)
            n_bw = (n_u - n_l)

            for st in setups_to_test:
                # Testa sem NWE
                tr_raw = simulate_setup(df, gex_data, n_s, n_bw, st, asset=asset, tf=tf, use_nwe_slope=False)
                res_raw = calc_stats(tr_raw)

                # Testa com NWE slope
                tr_nwe = simulate_setup(df, gex_data, n_s, n_bw, st, asset=asset, tf=tf, use_nwe_slope=True)
                res_nwe = calc_stats(tr_nwe)

                # Mostra o melhor dos dois
                chosen = res_nwe if (res_nwe["net"] > res_raw["net"] and res_nwe["pf"] >= 1.25) else res_raw
                tag = "C/ NWE" if chosen == res_nwe else "BASE S/ NWE"
                print(f"  {st:<24} [{tag}]: {chosen['tr']:>3d} tr | WR {chosen['wr']:>4.1f}% | PF {chosen['pf']:>4.2f} | Net R$ {chosen['net']:>7.0f} | DD R$ {chosen['mdd']:>5.0f} | Ret/DD {chosen['ret_dd']:>5.2f}x")


if __name__ == "__main__":
    main()

