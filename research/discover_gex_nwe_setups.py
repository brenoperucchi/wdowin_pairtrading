"""
MOTOR DE BUSCA E OTIMIZAÇÃO MULTI-ETAPAS DE SETUPS MT5 — WIN$N (MAGIC WALLS + NWE)

Executa uma busca estruturada em 5 Fases sobre os 115 pregões reais sincronizados
(Maio/2026 a Outubro/2026) no banco `irai_live.db`:

- Fase 1: Calibração do Envelope NWE (Lookback, Bandwidth, Mult MAE) em confluência com as Walls
- Fase 2: Operacional SCALPER WALL + NWE (Toque/Proximidade da Wall + Extremo NWE, filtro Width 1/2/3, Stop/Take/Alvo MidWall)
- Fase 3: Operacional GRID / AUMENTO DE MÃO (Entrada inicial na Wall + Scaling-in na MidWall / próxima Wall, saída no Preço Médio + Alvo ou retorno à Wall)
- Fase 4: Operacional INTRADAY / POSICIONAL DO DIA (Entrada no início do dia 09:00-10:30 com viés GammaFlip + NWE Slope + Pullback em Wall, carregando até 17:00 EOD com Trailing Stop pelas Walls)
- Fase 5: Consolidação do Portfólio Combinado MT5 (combinando os campeões descorrelacionados: Scalper + Grid + Posicional Intraday)

Regras de Realismo (Zero Look-Ahead):
- Usa exclusivamente a coleta matinal do GEX de cada pregão.
- Normaliza automaticamente o fuso das barras M5 para BRT (09:00 às 17:55).
- Custos operacionais considerados: Slippage/Spread de 10 pts por trade (R$ 2,00 por contrato).
"""
import os
import json
import time
import sqlite3
import numpy as np
import pandas as pd

DB_PATH = r"C:\Users\ryzen\Downloads\Antigravity\rastro_irado\data\irai_live.db"
OUT_DIR = r"C:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\data\reports\gex_nwe_setups"
os.makedirs(OUT_DIR, exist_ok=True)


def compute_nwe_series(closes: np.ndarray, lookback: int = 95, bw: float = 8.0, mult: float = 3.0):
    """Calcula NWE causal contínuo sobre o array de preços de fechamento."""
    n = len(closes)
    center = np.zeros(n, dtype=float)
    mae_raw = np.zeros(n, dtype=float)
    w_full = np.exp(-np.arange(lookback) ** 2 / (2.0 * bw * bw))

    for t in range(n):
        l_idx = min(t, lookback - 1)
        w_t = w_full[: l_idx + 1]
        p_t = closes[t - l_idx : t + 1][::-1]
        center[t] = np.sum(w_t * p_t) / np.sum(w_t)

    errors = np.abs(closes - center)
    for t in range(n):
        l_idx = min(t, lookback - 1)
        mae_raw[t] = np.mean(errors[t - l_idx : t + 1])

    upper = center + mae_raw * mult
    lower = center - mae_raw * mult
    slope = np.zeros(n, dtype=float)
    slope[1:] = center[1:] - center[:-1]
    return center, upper, lower, mae_raw, slope


def load_aligned_data():
    conn = sqlite3.connect(DB_PATH)
    df_bars = pd.read_sql_query(
        """
        SELECT timestamp_utc, open, high, low, close, volume, delta
        FROM market_bars
        WHERE symbol = 'WIN$N' AND timeframe = 'M5' AND timestamp_utc >= '2026-04-15'
        ORDER BY timestamp_utc ASC
        """,
        conn
    )

    # Normalize timestamp_utc to BRT (09:00 - 18:25)
    # Before 2026-06-25, bars were stored directly in BRT (09:00..18:25).
    # From 2026-06-25 onwards, collector added +6 hours (15:00..00:25 next day).
    ts_dt = pd.to_datetime(df_bars['timestamp_utc'])
    # Check per row: if hour >= 15 or hour <= 2 on dates >= 2026-06-24, subtract 6 hours
    is_shifted = ts_dt >= pd.Timestamp("2026-06-24T14:00:00Z")
    ts_brt = ts_dt.copy()
    ts_brt.loc[is_shifted] = ts_dt.loc[is_shifted] - pd.Timedelta(hours=6)

    df_bars['dt_brt'] = ts_brt
    df_bars['session_date'] = df_bars['dt_brt'].dt.strftime('%Y-%m-%d')
    df_bars['hour'] = df_bars['dt_brt'].dt.hour
    df_bars['minute'] = df_bars['dt_brt'].dt.minute
    df_bars['t_min'] = df_bars['hour'] * 60 + df_bars['minute']

    # Filter regular B3 session hours (09:00 to 17:55 BRT)
    df_bars = df_bars[(df_bars['t_min'] >= 9 * 60) & (df_bars['t_min'] <= 17 * 60 + 55)].copy()
    df_bars.reset_index(drop=True, inplace=True)

    # Load morning GEX levels for WIN$N
    c = conn.cursor()
    c.execute(
        """
        SELECT session_date, run_name, levels_json
        FROM gex_levels
        WHERE target = 'WIN$N'
        ORDER BY session_date ASC, run_name ASC
        """
    )
    gex_by_date = {}
    for s_date, r_name, l_json in c.fetchall():
        if s_date not in gex_by_date:
            lvls = json.loads(l_json)
            walls = sorted([x for x in lvls if x['type'] == 'wall'], key=lambda x: x['price'])
            mid_walls = sorted([x for x in lvls if x['type'] == 'mid_wall'], key=lambda x: x['price'])
            gex_by_date[s_date] = {
                'run_name': r_name,
                'levels': lvls,
                'walls': np.array([x['price'] for x in walls], dtype=float),
                'wall_widths': np.array([int(x.get('width', 1)) for x in walls], dtype=int),
                'mid_walls': np.array([x['price'] for x in mid_walls], dtype=float),
                'gamma_flip': next((float(x['price']) for x in lvls if x['type'] == 'gamma_flip'), None),
                'max_gamma': next((float(x['price']) for x in lvls if x['type'] == 'max_gamma'), None),
                'min_gamma': next((float(x['price']) for x in lvls if x['type'] == 'min_gamma'), None),
            }
    conn.close()
    return df_bars, gex_by_date


def calc_metrics(trades_list, label=""):
    """
    Calcula métricas estatísticas completas de uma lista de trades.
    Cada trade em trades_list é um dict: {'date', 'pnl_pts', 'contracts', 'pnl_brl', 'type', ...}
    onde 1 ponto de WIN = R$ 0,20 por contrato.
    """
    if not trades_list:
        return {
            'Setup': label, 'Trades': 0, 'WinRate': 0.0, 'ProfitFactor': 0.0,
            'TotalPtsEq': 0.0, 'TotalBRL': 0.0, 'MaxDD_BRL': 0.0,
            'Ret_DD': 0.0, 'SharpeDaily': 0.0, 'AvgPtsPerContract': 0.0
        }
    df_t = pd.DataFrame(trades_list)
    n_trades = len(df_t)
    wins = df_t[df_t['pnl_brl'] > 0]
    losses = df_t[df_t['pnl_brl'] <= 0]
    wr = (len(wins) / n_trades) * 100.0
    gross_win = wins['pnl_brl'].sum() if len(wins) > 0 else 0.0
    gross_loss = abs(losses['pnl_brl'].sum()) if len(losses) > 0 else 1e-6
    pf = gross_win / gross_loss if gross_loss > 0 else 99.9

    cum_brl = df_t['pnl_brl'].cumsum().values
    peak = np.maximum.accumulate(np.insert(cum_brl, 0, 0.0))[1:]
    dd_arr = peak - cum_brl
    max_dd_brl = float(np.max(dd_arr)) if len(dd_arr) > 0 else 0.0
    total_brl = float(cum_brl[-1])
    total_pts_eq = total_brl / 0.20  # Equivalente em pontos para 1 contrato
    ret_dd = total_brl / max_dd_brl if max_dd_brl > 0 else 99.9

    # Daily Sharpe
    daily_pnl = df_t.groupby('date')['pnl_brl'].sum()
    if len(daily_pnl) > 2 and daily_pnl.std() > 0:
        sharpe = (daily_pnl.mean() / daily_pnl.std()) * np.sqrt(252)
    else:
        sharpe = 0.0

    avg_pts = float(df_t['pnl_pts'].mean())

    return {
        'Setup': label,
        'Trades': n_trades,
        'WinRate': round(wr, 2),
        'ProfitFactor': round(pf, 2),
        'TotalPtsEq': round(total_pts_eq, 0),
        'TotalBRL': round(total_brl, 2),
        'MaxDD_BRL': round(max_dd_brl, 2),
        'Ret_DD': round(ret_dd, 2),
        'SharpeDaily': round(sharpe, 2),
        'AvgPts': round(avg_pts, 1),
    }


# ==============================================================================
# SIMULADORES DAS FAMÍLIAS DE SETUPS
# ==============================================================================

def simulate_scalper_hybrid_wall_nwe(
    df_bars, gex_by_date, nwe_center, nwe_upper, nwe_lower, nwe_slope,
    wmode_reject="NY_1000_1630", wmode_limit="NY_1000_1630",
    slope_min=9.0, lim_off=0.0,
    prox_pct=0.22, rsi_buy=35.0, rsi_sell=65.0,
    dist_touch=65.0, max_close_dist=80.0,
    tp_pts=400.0, sl_pts=220.0, be_trigger=140.0, be_lock=20.0,
    trail_trigger=250.0, trail_dist=100.0, max_hold_bars=15, cost_pts=10.0
):
    """
    Família 1 Otimizada (Robô 1A / 1B): SCALPER HÍBRIDO WALL/MIDWALL + NWE + RSI(7) + LIMIT PULLBACK
    Combina dois gatilhos não-conflitantes de alta frequência com TP > 100, SL > 100 e BE > 100:
      - Perna 1 (LIMIT_PULLBACK): Quando a barra i-1 testa uma Wall/MidWall (<= 50 pts) e fecha rejeitando-a
        a favor de uma inclinação forte do NWE (|slope| >= slope_min), apregoa ordem Limit (Wall ± lim_off)
        na barra i (com verificação pessimista intrabar).
      - Perna 2 (MKT_REJECT): Quando a barra i testa uma Wall/MidWall (<= dist_touch) em exaustão da banda NWE
        (prox_pct) + RSI(7) (<= rsi_buy / >= rsi_sell) e fecha próxima ao nível (<= max_close_dist), entra a mercado.
    """
    y = pd.Series(df_bars['close'].values)
    delta_p = y.diff()
    gain = delta_p.clip(lower=0).rolling(7).mean()
    loss = (-delta_p.clip(upper=0)).rolling(7).mean().replace(0, 1e-6)
    rsi7s = (100.0 - (100.0 / (1.0 + (gain / loss)))).fillna(50.0).values

    def _time_ok(t_min, wm):
        if wm == "FULL_09_17":
            return 540 <= t_min < 1020
        elif wm == "CORE_09_1615":
            return 540 <= t_min <= 975
        elif wm == "NY_1000_1630":
            return 600 <= t_min <= 990
        return True

    trades = []
    dates = df_bars['session_date'].values
    opens = df_bars['open'].values
    highs = df_bars['high'].values
    lows = df_bars['low'].values
    closes = df_bars['close'].values
    t_mins = df_bars['t_min'].values

    n = len(df_bars)
    i = 2
    while i < n - 1:
        s_date = dates[i]
        if s_date < "2026-05-11" or s_date not in gex_by_date or dates[i - 1] != s_date:
            i += 1
            continue

        g = gex_by_date[s_date]
        lvls = np.sort(np.concatenate([g['walls'], g['mid_walls']])) if len(g['mid_walls']) > 0 else g['walls']
        if len(lvls) == 0:
            i += 1
            continue

        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        u_b, l_b, m_b, slp = nwe_upper[i], nwe_lower[i], nwe_center[i], nwe_slope[i]
        bw = u_b - l_b

        o_p, h_p, l_p, c_p = opens[i - 1], highs[i - 1], lows[i - 1], closes[i - 1]
        u_p, l_b_p, m_p, slp_p = nwe_upper[i - 1], nwe_lower[i - 1], nwe_center[i - 1], nwe_slope[i - 1]
        bw_p = u_p - l_b_p

        signal = 0
        entry_p = 0.0
        filled_intrabar = False
        order_tag = ""

        if _time_ok(t_mins[i], wmode_limit):
            d_lp = np.abs(lvls - l_p)
            idx_lp = np.argmin(d_lp)
            if (slp_p >= slope_min and c_p <= m_p + bw_p * 0.15) and d_lp[idx_lp] <= 50.0 and c_p > lvls[idx_lp] + lim_off:
                lim_p = lvls[idx_lp] + lim_off
                if o >= lim_p and l <= lim_p:
                    signal = 1
                    entry_p = lim_p
                    filled_intrabar = True
                    order_tag = "LIMIT_BUY"

            d_hp = np.abs(lvls - h_p)
            idx_hp = np.argmin(d_hp)
            if signal == 0 and (slp_p <= -slope_min and c_p >= m_p - bw_p * 0.15) and d_hp[idx_hp] <= 50.0 and c_p < lvls[idx_hp] - lim_off:
                lim_p = lvls[idx_hp] - lim_off
                if o <= lim_p and h >= lim_p:
                    signal = -1
                    entry_p = lim_p
                    filled_intrabar = True
                    order_tag = "LIMIT_SELL"

        if signal == 0 and _time_ok(t_mins[i], wmode_reject):
            d_l = np.abs(lvls - l)
            idx_l = np.argmin(d_l)
            lvl_supp = lvls[idx_l]
            touched_supp = (d_l[idx_l] <= dist_touch) and (c >= lvl_supp - 35.0) and ((c - lvl_supp) <= max_close_dist)

            d_h = np.abs(lvls - h)
            idx_h = np.argmin(d_h)
            lvl_res = lvls[idx_h]
            touched_res = (d_h[idx_h] <= dist_touch) and (c <= lvl_res + 35.0) and ((lvl_res - c) <= max_close_dist)

            if touched_supp and c <= (l_b + bw * prox_pct) and rsi7s[i] <= rsi_buy:
                signal = 1
                entry_p = c
                filled_intrabar = False
                order_tag = "MKT_REJECT_BUY"
            elif touched_res and c >= (u_b - bw * prox_pct) and rsi7s[i] >= rsi_sell:
                signal = -1
                entry_p = c
                filled_intrabar = False
                order_tag = "MKT_REJECT_SELL"

        if signal != 0:
            curr_sl = entry_p - sl_pts if signal == 1 else entry_p + sl_pts
            curr_tp = entry_p + tp_pts if signal == 1 else entry_p - tp_pts
            be_active = False
            max_fav = 0.0
            exit_p = entry_p
            bars_held = 0
            closed_on_entry_bar = False

            if filled_intrabar:
                if signal == 1:
                    if l <= curr_sl:
                        exit_p = curr_sl
                        closed_on_entry_bar = True
                    elif c >= curr_tp:
                        exit_p = curr_tp
                        closed_on_entry_bar = True
                    else:
                        fav_c = c - entry_p
                        if fav_c > max_fav:
                            max_fav = fav_c
                        if be_trigger > 0 and fav_c >= be_trigger:
                            curr_sl = max(curr_sl, entry_p + be_lock)
                            be_active = True
                else:
                    if h >= curr_sl:
                        exit_p = curr_sl
                        closed_on_entry_bar = True
                    elif c <= curr_tp:
                        exit_p = curr_tp
                        closed_on_entry_bar = True
                    else:
                        fav_c = entry_p - c
                        if fav_c > max_fav:
                            max_fav = fav_c
                        if be_trigger > 0 and fav_c >= be_trigger:
                            curr_sl = min(curr_sl, entry_p - be_lock)
                            be_active = True

            j = i + 1
            if not closed_on_entry_bar:
                while j < n and dates[j] == s_date:
                    bars_held += 1
                    hj, lj, cj = highs[j], lows[j], closes[j]
                    if signal == 1:
                        if lj <= curr_sl:
                            exit_p = curr_sl
                            break
                        if hj >= curr_tp:
                            exit_p = curr_tp
                            break
                        fav = hj - entry_p
                        if fav > max_fav:
                            max_fav = fav
                        if be_trigger > 0 and not be_active and fav >= be_trigger:
                            curr_sl = max(curr_sl, entry_p + be_lock)
                            be_active = True
                        if trail_trigger > 0 and max_fav >= trail_trigger:
                            curr_sl = max(curr_sl, entry_p + (max_fav - trail_dist))
                    else:
                        if hj >= curr_sl:
                            exit_p = curr_sl
                            break
                        if lj <= curr_tp:
                            exit_p = curr_tp
                            break
                        fav = entry_p - lj
                        if fav > max_fav:
                            max_fav = fav
                        if be_trigger > 0 and not be_active and fav >= be_trigger:
                            curr_sl = min(curr_sl, entry_p - be_lock)
                            be_active = True
                        if trail_trigger > 0 and max_fav >= trail_trigger:
                            curr_sl = min(curr_sl, entry_p - (max_fav - trail_dist))

                    if bars_held >= max_hold_bars or t_mins[j] >= 17 * 60 + 20:
                        exit_p = cj
                        break
                    j += 1
                else:
                    exit_p = closes[min(j, n - 1)]
            else:
                j = i

            pts = (exit_p - entry_p) * signal - cost_pts
            trades.append({
                'date': s_date,
                'side': int(signal),
                'pnl_pts': pts,
                'contracts': 1,
                'pnl_brl': pts * 0.20,
                'bars_held': bars_held,
                'order_tag': order_tag,
                'type': 'SCALPER_HYBRID'
            })
            i = max(i + 1, j)
        else:
            i += 1

    return trades


def simulate_scalper_wall_nwe(
    df_bars, gex_by_date, nwe_center, nwe_upper, nwe_lower, nwe_slope,
    dist_wall=60.0, min_width=1, nwe_mode="band_prox", prox_pct=0.15,
    tp_mode="fixed", tp_pts=250.0, sl_pts=200.0, be_trigger=120.0,
    cooldown_bars=3, max_hold_bars=18, start_h=9, end_h=16, cost_pts=10.0
):
    """
    Família 1: SCALPER WALL + NWE
    Quando o preço (low ou high da barra M5) chega a <= dist_wall pontos de uma MagicWall (com width >= min_width):
    - Confluência NWE:
      * 'band_prox': Compra se close <= lower + (upper-lower)*prox_pct; Vende se close >= upper - (upper-lower)*prox_pct
      * 'center_reversion': Compra se close < nwe_center (esticado abaixo da média kernel); Vende se close > nwe_center
      * 'wall_only': Apenas o toque na Wall + rejeição (fechamento a favor da reversão)
    - Alvo (tp_mode):
      * 'fixed': tp_pts fixo
      * 'midwall': distância até a MidWall (~507 pts)
      * 'nwe_center': saída quando toca a linha central do NWE (ou tp_pts máximo)
    """
    trades = []
    dates = df_bars['session_date'].values
    opens = df_bars['open'].values
    highs = df_bars['high'].values
    lows = df_bars['low'].values
    closes = df_bars['close'].values
    hours = df_bars['hour'].values
    t_mins = df_bars['t_min'].values

    n = len(df_bars)
    i = 0
    while i < n - 1:
        s_date = dates[i]
        if s_date < "2026-05-11" or s_date not in gex_by_date:
            i += 1
            continue
        if hours[i] < start_h or hours[i] > end_h:
            i += 1
            continue

        gex = gex_by_date[s_date]
        walls = gex['walls']
        widths = gex['wall_widths']
        valid_walls = walls[widths >= min_width]
        if len(valid_walls) == 0:
            i += 1
            continue

        c = closes[i]
        h = highs[i]
        l = lows[i]
        o = opens[i]
        u_band = nwe_upper[i]
        l_band = nwe_lower[i]
        mid_nwe = nwe_center[i]
        bw_width = u_band - l_band

        # Check NWE condition
        if nwe_mode == "band_prox":
            can_buy_nwe = c <= (l_band + bw_width * prox_pct)
            can_sell_nwe = c >= (u_band - bw_width * prox_pct)
        elif nwe_mode == "center_ext":
            # Esticado pelo menos prox_pct da banda a partir do centro
            can_buy_nwe = c <= (mid_nwe - (bw_width * 0.5) * prox_pct)
            can_sell_nwe = c >= (mid_nwe + (bw_width * 0.5) * prox_pct)
        else:  # wall_rejection
            can_buy_nwe = (c > o)  # Candle de rejeição comprador
            can_sell_nwe = (c < o) # Candle de rejeição vendedor

        signal = 0
        wall_ref = 0.0

        # Check buy at support wall (low touched near wall and close held above wall - 40)
        if can_buy_nwe:
            dists_buy = np.abs(valid_walls - l)
            min_idx = np.argmin(dists_buy)
            if dists_buy[min_idx] <= dist_wall and c >= valid_walls[min_idx] - 30.0:
                signal = 1
                wall_ref = valid_walls[min_idx]

        # Check sell at resistance wall (high touched near wall and close held below wall + 40)
        if signal == 0 and can_sell_nwe:
            dists_sell = np.abs(valid_walls - h)
            min_idx = np.argmin(dists_sell)
            if dists_sell[min_idx] <= dist_wall and c <= valid_walls[min_idx] + 30.0:
                signal = -1
                wall_ref = valid_walls[min_idx]

        if signal != 0:
            entry_price = c
            curr_sl = entry_price - sl_pts if signal == 1 else entry_price + sl_pts
            target_pts = 500.0 if tp_mode == "midwall" else tp_pts
            curr_tp = entry_price + target_pts if signal == 1 else entry_price - target_pts
            be_active = False

            exit_price = entry_price
            bars_held = 0
            j = i + 1
            while j < n and dates[j] == s_date:
                bars_held += 1
                hj, lj, cj = highs[j], lows[j], closes[j]

                # Check SL / TP
                if signal == 1:
                    if lj <= curr_sl:
                        exit_price = curr_sl
                        break
                    if hj >= curr_tp:
                        exit_price = curr_tp
                        break
                    if tp_mode == "nwe_center" and hj >= nwe_center[j] and (nwe_center[j] - entry_price) >= 100.0:
                        exit_price = nwe_center[j]
                        break
                    if be_trigger > 0 and not be_active and (hj - entry_price) >= be_trigger:
                        curr_sl = entry_price + 15.0
                        be_active = True
                else:
                    if hj >= curr_sl:
                        exit_price = curr_sl
                        break
                    if lj <= curr_tp:
                        exit_price = curr_tp
                        break
                    if tp_mode == "nwe_center" and lj <= nwe_center[j] and (entry_price - nwe_center[j]) >= 100.0:
                        exit_price = nwe_center[j]
                        break
                    if be_trigger > 0 and not be_active and (entry_price - lj) >= be_trigger:
                        curr_sl = entry_price - 15.0
                        be_active = True

                if bars_held >= max_hold_bars or t_mins[j] >= 17 * 60 + 25:
                    exit_price = cj
                    break
                j += 1
            else:
                exit_price = closes[min(j, n - 1)]

            raw_pts = (exit_price - entry_price) * signal - cost_pts
            trades.append({
                'date': s_date,
                'side': int(signal),
                'pnl_pts': raw_pts,
                'contracts': 1,
                'pnl_brl': raw_pts * 0.20,
                'type': 'SCALPER'
            })
            i = j + cooldown_bars
        else:
            i += 1

    return trades


def simulate_grid_martingale_wall(
    df_bars, gex_by_date, nwe_center, nwe_upper, nwe_lower,
    prox_pct=0.20, step2_dist=500.0, step3_dist=1000.0,
    lot1=1, lot2=2, lot3=0,
    tp_avg_pts=220.0, max_sl_pts=750.0, max_hold_bars=30,
    start_h=9, end_h=15, cooldown_bars=4, cost_pts=10.0
):
    """
    Família 2: OPERACIONAL COM AUMENTO DE MÃO (SCALING-IN NAS WALLS/MIDWALLS)
    - Lote 1 (`lot1` contratos): entra na MagicWall quando em confluência com o NWE (`prox_pct`).
    - Lote 2 (`lot2` contratos): se o preço for contra até a MidWall (`step2_dist`, ~500 pts),
      aumenta a mão exatamente na barreira seguinte, melhorando o Preço Médio!
    - Lote 3 (`lot3` contratos, opcional): se for até a próxima MagicWall (`step3_dist`, ~1000 pts),
      adiciona a 3ª camada.
    - Saída Unificada:
      * Gain quando o preço retorna `tp_avg_pts` a favor do Preço Médio ponderado!
      * Stop de proteção total se passar de `max_sl_pts` a partir do Preço Médio (ou no fim do dia 17:20).
    """
    trades = []
    dates = df_bars['session_date'].values
    highs = df_bars['high'].values
    lows = df_bars['low'].values
    closes = df_bars['close'].values
    hours = df_bars['hour'].values
    t_mins = df_bars['t_min'].values

    n = len(df_bars)
    i = 0
    while i < n - 1:
        s_date = dates[i]
        if s_date < "2026-05-11" or s_date not in gex_by_date:
            i += 1
            continue
        if hours[i] < start_h or hours[i] > end_h:
            i += 1
            continue

        gex = gex_by_date[s_date]
        walls = gex['walls']
        if len(walls) == 0:
            i += 1
            continue

        c = closes[i]
        h = highs[i]
        l = lows[i]
        u_band = nwe_upper[i]
        l_band = nwe_lower[i]
        bw_width = u_band - l_band

        can_buy = c <= (l_band + bw_width * prox_pct)
        can_sell = c >= (u_band - bw_width * prox_pct)

        signal = 0
        entry1_price = 0.0

        if can_buy:
            dists = np.abs(walls - l)
            idx = np.argmin(dists)
            if dists[idx] <= 65.0 and c >= walls[idx] - 40.0:
                signal = 1
                entry1_price = c
        if signal == 0 and can_sell:
            dists = np.abs(walls - h)
            idx = np.argmin(dists)
            if dists[idx] <= 65.0 and c <= walls[idx] + 40.0:
                signal = -1
                entry1_price = c

        if signal != 0:
            total_qty = lot1
            avg_price = entry1_price
            filled_step2 = False
            filled_step3 = False

            lvl2_price = entry1_price - step2_dist if signal == 1 else entry1_price + step2_dist
            lvl3_price = entry1_price - step3_dist if signal == 1 else entry1_price + step3_dist

            exit_price = entry1_price
            bars_held = 0
            j = i + 1
            while j < n and dates[j] == s_date:
                bars_held += 1
                hj, lj, cj = highs[j], lows[j], closes[j]

                # Check scaling-in fills first if price moves against
                if signal == 1:
                    if not filled_step2 and lot2 > 0 and lj <= lvl2_price:
                        avg_price = (avg_price * total_qty + lvl2_price * lot2) / (total_qty + lot2)
                        total_qty += lot2
                        filled_step2 = True
                    if filled_step2 and not filled_step3 and lot3 > 0 and lj <= lvl3_price:
                        avg_price = (avg_price * total_qty + lvl3_price * lot3) / (total_qty + lot3)
                        total_qty += lot3
                        filled_step3 = True

                    # Check TP and SL from avg_price
                    tp_price = avg_price + tp_avg_pts
                    sl_price = avg_price - max_sl_pts
                    if lj <= sl_price:
                        exit_price = sl_price
                        break
                    if hj >= tp_price:
                        exit_price = tp_price
                        break
                else:
                    if not filled_step2 and lot2 > 0 and hj >= lvl2_price:
                        avg_price = (avg_price * total_qty + lvl2_price * lot2) / (total_qty + lot2)
                        total_qty += lot2
                        filled_step2 = True
                    if filled_step2 and not filled_step3 and lot3 > 0 and hj >= lvl3_price:
                        avg_price = (avg_price * total_qty + lvl3_price * lot3) / (total_qty + lot3)
                        total_qty += lot3
                        filled_step3 = True

                    tp_price = avg_price - tp_avg_pts
                    sl_price = avg_price + max_sl_pts
                    if hj >= sl_price:
                        exit_price = sl_price
                        break
                    if lj <= tp_price:
                        exit_price = tp_price
                        break

                if bars_held >= max_hold_bars or t_mins[j] >= 17 * 60 + 25:
                    exit_price = cj
                    break
                j += 1
            else:
                exit_price = closes[min(j, n - 1)]

            net_pts_per_lot = (exit_price - avg_price) * signal - cost_pts
            total_brl = net_pts_per_lot * total_qty * 0.20
            trades.append({
                'date': s_date,
                'side': int(signal),
                'pnl_pts': net_pts_per_lot,
                'contracts': total_qty,
                'pnl_brl': total_brl,
                'type': 'GRID_SCALE_IN'
            })
            i = j + cooldown_bars
        else:
            i += 1

    return trades


def simulate_intraday_positional_eod(
    df_bars, gex_by_date, nwe_center, nwe_upper, nwe_lower, nwe_slope,
    entry_mode="wall_bounce_trend", entry_end_h=11,
    sl_pts=450.0, tp_pts=1500.0, trail_step_wall=True, be_trigger=350.0,
    cost_pts=10.0
):
    """
    Família 3: OPERACIONAL COMEÇO DO DIA -> FINAL DO DIA (INTRADAY POSICIONAL EOD)
    Faz no máximo 1 operação estrutural por dia, entrando na janela da manhã (09:05 até `entry_end_h`h)
    e encerrando no final do dia (17:15 BRT) ou no alvo longo / trailing stop pelas Walls:
    - Modos de Entrada (`entry_mode`):
      * 'wall_bounce_trend': Preço testa uma Wall (ou MidWall) na manhã e rejeita a favor da inclinação do NWE (`nwe_slope`).
      * 'wall_breakout_nwe': Preço rompe a primeira Wall da manhã com fechamento forte + `nwe_slope` a favor, buscando a próxima Wall distante (+1014 / +1500 pts).
      * 'gamma_flip_regime': Opera a favor do regime do Gamma Flip + NWE Slope no primeiro pullback até uma Wall/MidWall pela manhã.
      * 'morning_extreme_fade': Compra a primeira Wall testada abaixo da abertura da manhã (ou vende a primeira Wall testada acima da abertura) se esticado no NWE, carregando para reversão diária até o fim da tarde.
    """
    trades = []
    dates = df_bars['session_date'].values
    opens = df_bars['open'].values
    highs = df_bars['high'].values
    lows = df_bars['low'].values
    closes = df_bars['close'].values
    hours = df_bars['hour'].values
    t_mins = df_bars['t_min'].values

    # Group indices by session_date
    df_idx_by_date = df_bars.groupby('session_date').indices

    for s_date, idxs in sorted(df_idx_by_date.items()):
        if s_date < "2026-05-11" or s_date not in gex_by_date or len(idxs) < 15:
            continue

        gex = gex_by_date[s_date]
        all_levels = np.sort(np.concatenate([gex['walls'], gex['mid_walls']]))
        walls = gex['walls']
        flip = gex['gamma_flip']
        if len(walls) == 0:
            continue

        day_open = opens[idxs[0]]
        signal = 0
        entry_idx = -1
        entry_price = 0.0

        # Scan morning window (from bar 1 of the day up to entry_end_h)
        for k in range(1, len(idxs) - 5):
            idx = idxs[k]
            if hours[idx] >= entry_end_h:
                break

            c = closes[idx]
            o = opens[idx]
            h = highs[idx]
            l = lows[idx]
            prev_c = closes[idxs[k - 1]]
            slp = nwe_slope[idx]
            mid_nwe = nwe_center[idx]

            if entry_mode == "wall_bounce_trend":
                # Rejeição de uma Wall a favor do NWE slope
                dists_l = np.abs(all_levels - l)
                if np.min(dists_l) <= 55.0 and c > o and slp >= 0:
                    signal = 1
                    entry_idx = k
                    entry_price = c
                    break
                dists_h = np.abs(all_levels - h)
                if np.min(dists_h) <= 55.0 and c < o and slp <= 0:
                    signal = -1
                    entry_idx = k
                    entry_price = c
                    break

            elif entry_mode == "wall_breakout_nwe":
                # Rompimento confirmado de Wall pela manhã com NWE slope forte
                for w in walls:
                    if prev_c <= w and c > w + 25.0 and slp > 2.0 and c > mid_nwe:
                        signal = 1
                        entry_idx = k
                        entry_price = c
                        break
                    if prev_c >= w and c < w - 25.0 and slp < -2.0 and c < mid_nwe:
                        signal = -1
                        entry_idx = k
                        entry_price = c
                        break
                if signal != 0:
                    break

            elif entry_mode == "gamma_flip_regime":
                # Acima do Gamma Flip = regime Long Gamma (compra pullback na Wall/MidWall);
                # Abaixo do Gamma Flip = regime Short Gamma (opera momentum a favor do NWE slope ao cruzar Wall)
                if flip is not None and c >= flip:
                    if np.min(np.abs(all_levels - l)) <= 60.0 and c > o:
                        signal = 1
                        entry_idx = k
                        entry_price = c
                        break
                    if np.min(np.abs(all_levels - h)) <= 60.0 and c < o:
                        signal = -1
                        entry_idx = k
                        entry_price = c
                        break
                else:
                    if slp > 3.0 and c > o and c > mid_nwe:
                        signal = 1
                        entry_idx = k
                        entry_price = c
                        break
                    elif slp < -3.0 and c < o and c < mid_nwe:
                        signal = -1
                        entry_idx = k
                        entry_price = c
                        break

            elif entry_mode == "morning_extreme_fade":
                # Reversão da primeira excursão matinal até uma MagicWall distante da abertura (> 400 pts)
                if (day_open - l) >= 350.0 and np.min(np.abs(walls - l)) <= 70.0 and c > o and c <= nwe_center[idx]:
                    signal = 1
                    entry_idx = k
                    entry_price = c
                    break
                if (h - day_open) >= 350.0 and np.min(np.abs(walls - h)) <= 70.0 and c < o and c >= nwe_center[idx]:
                    signal = -1
                    entry_idx = k
                    entry_price = c
                    break

        if signal != 0 and entry_idx != -1:
            curr_sl = entry_price - sl_pts if signal == 1 else entry_price + sl_pts
            curr_tp = entry_price + tp_pts if signal == 1 else entry_price - tp_pts
            be_active = False
            max_fav = 0.0
            exit_price = entry_price

            for m in range(entry_idx + 1, len(idxs)):
                idx_m = idxs[m]
                hm, lm, cm = highs[idx_m], lows[idx_m], closes[idx_m]

                if signal == 1:
                    if lm <= curr_sl:
                        exit_price = curr_sl
                        break
                    if hm >= curr_tp:
                        exit_price = curr_tp
                        break
                    fav = hm - entry_price
                    if fav > max_fav:
                        max_fav = fav
                    if be_trigger > 0 and not be_active and fav >= be_trigger:
                        curr_sl = entry_price + 30.0
                        be_active = True
                    # Step trailing stop along conquered Walls/MidWalls (every 500 pts of profit locks 50% of gain)
                    if trail_step_wall and max_fav >= 600.0:
                        lock_sl = entry_price + (max_fav - 350.0)
                        if lock_sl > curr_sl:
                            curr_sl = lock_sl
                else:
                    if hm >= curr_sl:
                        exit_price = curr_sl
                        break
                    if lm <= curr_tp:
                        exit_price = curr_tp
                        break
                    fav = entry_price - lm
                    if fav > max_fav:
                        max_fav = fav
                    if be_trigger > 0 and not be_active and fav >= be_trigger:
                        curr_sl = entry_price - 30.0
                        be_active = True
                    if trail_step_wall and max_fav >= 600.0:
                        lock_sl = entry_price - (max_fav - 350.0)
                        if lock_sl < curr_sl:
                            curr_sl = lock_sl

                # Encerramento no final do dia (17:15 BRT)
                if t_mins[idx_m] >= 17 * 60 + 15 or m == len(idxs) - 1:
                    exit_price = cm
                    break

            raw_pts = (exit_price - entry_price) * signal - cost_pts
            trades.append({
                'date': s_date,
                'side': int(signal),
                'pnl_pts': raw_pts,
                'contracts': 1,
                'pnl_brl': raw_pts * 0.20,
                'type': 'INTRADAY_EOD'
            })

    return trades


def run_multi_stage_pipeline():
    t0 = time.time()
    print("=" * 85)
    print("  BUSCA MULTI-ETAPAS DE SETUPS MT5 — WIN$N (MAGIC WALLS + NWE)")
    print("=" * 85)

    df_bars, gex_by_date = load_aligned_data()
    closes = df_bars['close'].values

    # ==========================================================================
    # ETAPA 1: CALIBRAÇÃO DO MOTOR NWE EM CONFLUÊNCIA COM AS MAGIC WALLS
    # ==========================================================================
    print("\n" + "-" * 85)
    print("  ETAPA 1: CALIBRAÇÃO DOS PARÂMETROS DO NWE (LOOKBACK, BANDWIDTH, MULT MAE)")
    print("-" * 85)

    nwe_configs = [
        (50, 5.0, 2.0),
        (70, 6.0, 2.0),
        (95, 8.0, 2.0),
        (95, 8.0, 2.5),
        (95, 8.0, 3.0),
        (120, 8.0, 2.5),
        (150, 5.0, 2.5),
        (40, 3.0, 1.8),
    ]
    nwe_cache = {}
    stage1_rows = []

    for (lb, bw, mult) in nwe_configs:
        c_arr, u_arr, l_arr, mae_arr, slp_arr = compute_nwe_series(closes, lookback=lb, bw=bw, mult=mult)
        nwe_cache[(lb, bw, mult)] = (c_arr, u_arr, l_arr, mae_arr, slp_arr)
        trades = simulate_scalper_wall_nwe(
            df_bars, gex_by_date, c_arr, u_arr, l_arr, slp_arr,
            dist_wall=60.0, min_width=1, nwe_mode="band_prox", prox_pct=0.20,
            tp_mode="fixed", tp_pts=250.0, sl_pts=200.0, be_trigger=120.0
        )
        m = calc_metrics(trades, label=f"NWE(LB={lb}, BW={bw}, M={mult})")
        m['LB'], m['BW'], m['Mult'] = lb, bw, mult
        stage1_rows.append(m)

    df_s1 = pd.DataFrame(stage1_rows).sort_values('Ret_DD', ascending=False)
    df_s1.to_csv(os.path.join(OUT_DIR, "etapa1_nwe_calibration.csv"), index=False)
    print(df_s1[['Setup', 'Trades', 'WinRate', 'ProfitFactor', 'TotalPtsEq', 'TotalBRL', 'MaxDD_BRL', 'Ret_DD', 'SharpeDaily']].to_string(index=False))

    best_nwe_row = df_s1[df_s1['Trades'] >= 50].iloc[0] if len(df_s1[df_s1['Trades'] >= 50]) > 0 else df_s1.iloc[0]
    best_key = (int(best_nwe_row['LB']), float(best_nwe_row['BW']), float(best_nwe_row['Mult']))
    c_best, u_best, l_best, mae_best, slp_best = nwe_cache[best_key]
    print(f"\n  >> VENCEDOR ETAPA 1: LB={best_key[0]}, BW={best_key[1]}, Mult={best_key[2]} (Ret/DD={best_nwe_row['Ret_DD']}, Sharpe={best_nwe_row['SharpeDaily']})")

    # ==========================================================================
    # ETAPA 2: BUSCA DE SETUPS SCALPER NAS WALLS (PROXIMIDADE, WIDTH, STOPS E ALVOS)
    # ==========================================================================
    print("\n" + "-" * 85)
    print("  ETAPA 2: BUSCA DE OPERACIONAIS SCALPER (TOQUE NA MAGIC WALL + NWE)")
    print("-" * 85)

    stage2_rows = []
    stage2_trades_map = {}

    for nwe_mode in ["band_prox", "center_ext", "wall_rejection"]:
        for prox_pct in [0.15, 0.25, 0.35]:
            if nwe_mode == "wall_rejection" and prox_pct != 0.15:
                continue
            for min_w in [1, 2]:
                for dist_w in [45.0, 70.0]:
                    for (tp_m, tp_p, sl_p, be_t) in [
                        ("fixed", 150.0, 150.0, 80.0),
                        ("fixed", 250.0, 200.0, 120.0),
                        ("fixed", 350.0, 220.0, 150.0),
                        ("midwall", 500.0, 220.0, 150.0),
                        ("nwe_center", 400.0, 200.0, 120.0),
                    ]:
                        lbl = f"Scalp[{nwe_mode}|p={prox_pct}|W>={min_w}|d={int(dist_w)}|TP={tp_m}({int(tp_p)})/SL={int(sl_p)}]"
                        tr = simulate_scalper_wall_nwe(
                            df_bars, gex_by_date, c_best, u_best, l_best, slp_best,
                            dist_wall=dist_w, min_width=min_w, nwe_mode=nwe_mode, prox_pct=prox_pct,
                            tp_mode=tp_m, tp_pts=tp_p, sl_pts=sl_p, be_trigger=be_t
                        )
                        m = calc_metrics(tr, label=lbl)
                        stage2_rows.append(m)
                        stage2_trades_map[lbl] = tr

    df_s2 = pd.DataFrame(stage2_rows)
    df_s2_valid = df_s2[df_s2['Trades'] >= 45].sort_values(['Ret_DD', 'SharpeDaily'], ascending=False)
    df_s2_valid.to_csv(os.path.join(OUT_DIR, "etapa2_scalper_setups.csv"), index=False)
    print(df_s2_valid.head(12)[['Setup', 'Trades', 'WinRate', 'ProfitFactor', 'TotalPtsEq', 'TotalBRL', 'MaxDD_BRL', 'Ret_DD', 'SharpeDaily']].to_string(index=False))

    best_scalper_lbl = df_s2_valid.iloc[0]['Setup']
    best_scalper_trades = stage2_trades_map[best_scalper_lbl]
    print(f"\n  >> CAMPEÃO SCALPER (ETAPA 2): {best_scalper_lbl}")

    # ==========================================================================
    # ETAPA 3: BUSCA DE OPERACIONAIS COM AUMENTO DE MÃO (SCALING-IN WALL -> MIDWALL)
    # ==========================================================================
    print("\n" + "-" * 85)
    print("  ETAPA 3: BUSCA DE OPERACIONAIS COM AUMENTO DE MÃO (GRID / DEFESA DE PREÇO MÉDIO)")
    print("-" * 85)

    stage3_rows = []
    stage3_trades_map = {}

    for prox_pct in [0.15, 0.25, 0.35]:
        for (lot1, lot2, lot3) in [(1, 1, 0), (1, 2, 0), (1, 2, 3), (2, 3, 0)]:
            for step2_d in [450.0, 507.0]:  # 507 pts = distância exata Wall -> MidWall!
                for (tp_avg, max_sl) in [
                    (180.0, 650.0),
                    (250.0, 750.0),
                    (320.0, 800.0),
                    (400.0, 900.0),
                ]:
                    lbl = f"Grid[Lotes={lot1}+{lot2}+{lot3}|p={prox_pct}|Step={int(step2_d)}|TP_PM={int(tp_avg)}/SL_PM={int(max_sl)}]"
                    tr = simulate_grid_martingale_wall(
                        df_bars, gex_by_date, c_best, u_best, l_best,
                        prox_pct=prox_pct, step2_dist=step2_d, step3_dist=step2_d * 2.0,
                        lot1=lot1, lot2=lot2, lot3=lot3,
                        tp_avg_pts=tp_avg, max_sl_pts=max_sl
                    )
                    m = calc_metrics(tr, label=lbl)
                    stage3_rows.append(m)
                    stage3_trades_map[lbl] = tr

    df_s3 = pd.DataFrame(stage3_rows)
    df_s3_valid = df_s3[df_s3['Trades'] >= 45].sort_values(['Ret_DD', 'SharpeDaily'], ascending=False)
    df_s3_valid.to_csv(os.path.join(OUT_DIR, "etapa3_grid_scaling_setups.csv"), index=False)
    print(df_s3_valid.head(12)[['Setup', 'Trades', 'WinRate', 'ProfitFactor', 'TotalPtsEq', 'TotalBRL', 'MaxDD_BRL', 'Ret_DD', 'SharpeDaily']].to_string(index=False))

    best_grid_lbl = df_s3_valid.iloc[0]['Setup']
    best_grid_trades = stage3_trades_map[best_grid_lbl]
    print(f"\n  >> CAMPEÃO AUMENTO DE MÃO (ETAPA 3): {best_grid_lbl}")

    # ==========================================================================
    # ETAPA 4: OPERACIONAIS COMEÇO DO DIA -> FINAL DO DIA (INTRADAY POSICIONAL EOD)
    # ==========================================================================
    print("\n" + "-" * 85)
    print("  ETAPA 4: OPERACIONAIS INÍCIO DO DIA -> FIM DO DIA (1 TRADE/DIA ATÉ 17:15)")
    print("-" * 85)

    stage4_rows = []
    stage4_trades_map = {}

    for emode in ["wall_bounce_trend", "wall_breakout_nwe", "gamma_flip_regime", "morning_extreme_fade"]:
        for end_h in [11, 12]:
            for (sl_p, tp_p, be_t, tr_step) in [
                (350.0, 1200.0, 250.0, True),
                (450.0, 1500.0, 350.0, True),
                (500.0, 2000.0, 400.0, True),
                (450.0, 1500.0, 350.0, False),
                (600.0, 2500.0, 0.0, False),  # Pure EOD hold with wide catastrophe stop
            ]:
                lbl = f"EOD[{emode}|ate={end_h}h|TP={int(tp_p)}/SL={int(sl_p)}|BE={int(be_t)}|Trail={int(tr_step)}]"
                tr = simulate_intraday_positional_eod(
                    df_bars, gex_by_date, c_best, u_best, l_best, slp_best,
                    entry_mode=emode, entry_end_h=end_h,
                    sl_pts=sl_p, tp_pts=tp_p, trail_step_wall=tr_step, be_trigger=be_t
                )
                m = calc_metrics(tr, label=lbl)
                stage4_rows.append(m)
                stage4_trades_map[lbl] = tr

    df_s4 = pd.DataFrame(stage4_rows)
    df_s4_valid = df_s4[df_s4['Trades'] >= 30].sort_values(['Ret_DD', 'SharpeDaily'], ascending=False)
    df_s4_valid.to_csv(os.path.join(OUT_DIR, "etapa4_intraday_eod_setups.csv"), index=False)
    print(df_s4_valid.head(12)[['Setup', 'Trades', 'WinRate', 'ProfitFactor', 'TotalPtsEq', 'TotalBRL', 'MaxDD_BRL', 'Ret_DD', 'SharpeDaily']].to_string(index=False))

    best_eod_lbl = df_s4_valid.iloc[0]['Setup']
    best_eod_trades = stage4_trades_map[best_eod_lbl]
    print(f"\n  >> CAMPEÃO INTRADAY EOD (ETAPA 4): {best_eod_lbl}")

    # ==========================================================================
    # ETAPA 5: PORTFÓLIO COMBINADO DE ROBÔS MT5 (SCALPER + AUMENTO DE MÃO + EOD)
    # ==========================================================================
    print("\n" + "-" * 85)
    print("  ETAPA 5: SÍNTESE DO PORTFÓLIO MULTI-ROBÔS MT5 (COMBINANDO AS 3 ESTRATÉGIAS)")
    print("-" * 85)

    combined_trades = sorted(best_scalper_trades + best_grid_trades + best_eod_trades, key=lambda x: x['date'])
    p_rows = [
        calc_metrics(best_scalper_trades, label="Robô 1: Scalper Wall + NWE (Isolado)"),
        calc_metrics(best_grid_trades, label="Robô 2: Grid Scaling-In Wall->MidWall (Isolado)"),
        calc_metrics(best_eod_trades, label="Robô 3: Intraday Abertura->EOD 17:15 (Isolado)"),
        calc_metrics(combined_trades, label="PORTFÓLIO COMPLETO (Robôs 1 + 2 + 3 Juntos)"),
    ]
    df_p = pd.DataFrame(p_rows)
    df_p.to_csv(os.path.join(OUT_DIR, "etapa5_portfolio_summary.csv"), index=False)
    print(df_p[['Setup', 'Trades', 'WinRate', 'ProfitFactor', 'TotalPtsEq', 'TotalBRL', 'MaxDD_BRL', 'Ret_DD', 'SharpeDaily']].to_string(index=False))

    print(f"\nConcluído em {time.time() - t0:.1f}s. Relatórios salvos em: {OUT_DIR}")


if __name__ == "__main__":
    run_multi_stage_pipeline()
