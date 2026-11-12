"""
Filtros de Fluxo / Janela A.S.G do Dashboard (versão independente de simulador)
==============================================================================
Reproduz exatamente as métricas do painel de fluxo (histograma A.S.G, janela
verde/vermelha, fluxo institucional 5m/15m, absorção no pavio) a partir das
sessões salvas em data/processed/gex_historical_sessions_v1/<data>.json
(série `m5_cvd_series` de WIN e WDO), e devolve uma tabela de consulta:

    FLOW[asset][filter_name][(date, b1_tmin)] = (compra_ok, venda_ok)

Uso nos simuladores alinhados ao MT5: o sinal gerado na barra fechada b1
(decidido na abertura da barra seguinte) só é aceito se o filtro permitir
aquela direção. Barras sem dados de fluxo são liberadas (mesma regra do
estudo original `eval_mt5_with_dashboard_filters.py`).

Fórmulas copiadas de `eval_mt5_with_dashboard_filters.py`
(`compute_dashboard_series_for_asset` + `build_filter_masks`).
"""
import os
import glob
import json
import pickle
from datetime import datetime, timezone

import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SESSIONS_DIR = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")
PKL_FLOW_2026 = os.path.join(ROOT_DIR, "data", "processed", "mt5_tick_flow_tables_2026.pkl")

FILTER_NAMES = [
    "0_BASE_MT5",
    "1_JANELA_ASG",
    "2_JANELA_S_EXPLOSAO",
    "3_FLUXO_INST",
    "4_FLUXO_ABSORCAO",
    "5_COMBO_ESTRITO",
    "6_COMBO_SMART",
    "7_PROFIT_DEFENSE",
    "8_PROFIT_SWEEP",
    "9_PROFIT_INST_RET",
    "10_PROFIT_SMART_WALL",
    "11_PROFIT_WALL_SHIELD",
    "12_NR_WALL_TRAP_DIV",
    "13_NR_PRICE_ABS_DIV",
    "14_NR_BREAKOUT_SQUEEZE",
    "15_NR_IGNITION_DIV",
    "16_NR_DIV_ABS_OR_AGGR",
    "17_NR_SQUEEZE_CLEAN",
    "18_NR_ASG_PLUS_DIV",
]

FILTER_LABELS = {
    "0_BASE_MT5": "Sem filtro (MT5)",
    "1_JANELA_ASG": "Janela A.S.G a favor",
    "2_JANELA_S_EXPLOSAO": "Janela s/ explosão contra",
    "3_FLUXO_INST": "Fluxo institucional a favor",
    "4_FLUXO_ABSORCAO": "Fluxo ou absorção",
    "5_COMBO_ESTRITO": "Janela + fluxo/absorção",
    "6_COMBO_SMART": "Janela s/ explosão + fluxo/absorção",
    "7_PROFIT_DEFENSE": "Profit 4-Players · Absorção Passiva + Armadilha Varejo",
    "8_PROFIT_SWEEP": "Profit 4-Players · Sweep Institucional Agressor + Ticket",
    "9_PROFIT_INST_RET": "Profit 4-Players · Inst vs Varejo Divergência + Ticket",
    "10_PROFIT_SMART_WALL": "Profit 4-Players · Janela S + Defesa Passiva na Wall",
    "11_PROFIT_WALL_SHIELD": "Profit 4-Players · Janela S + Escudo Inst/Varejo na Wall",
    "12_NR_WALL_TRAP_DIV": "Divergência Armadilha Varejo vs Absorção/Agressão Não-Varejo na Wall",
    "13_NR_PRICE_ABS_DIV": "Divergência Preço vs Absorção Passiva / Agressão Não-Varejo",
    "14_NR_BREAKOUT_SQUEEZE": "Sweep Não-Varejo + Squeeze Varejo s/ Absorção Contrária",
    "15_NR_IGNITION_DIV": "Divergência Ignição 15m vs Distribuição Não-Varejo",
    "16_NR_DIV_ABS_OR_AGGR": "Divergência Preço na Wall vs Absorção Passiva ou Agressão Não-Varejo",
    "17_NR_SQUEEZE_CLEAN": "Divergência Limpa Preço 15m vs Fluxo Não-Varejo",
    "18_NR_ASG_PLUS_DIV": "Janela A.S.G + Divergência Preço vs Absorção/Agressão Não-Varejo",
}


def _session_features(m5_series, is_win: bool):
    """
    Histograma e Janela de Fluxo Smart Money Unificados por barra M5 (alinhado entre WIN e WDO):
      - 3 Motores Físicos (0% Preço):
          * 12% Absorção Oculta na Pedra (Wyckoff Effort vs. Result)
          * 18% Assimetria de Porte / Ticket Médio (Urgência de Lote Grande)
          * 70% Saldo Institucional Não-Varejo (0.90 Agressor + 0.75 Passivo na Pedra - 0.25 Varejo)
      - Memória Estrutural: EMA Rápida 4 / EMA Lenta 20 do CVD Efetivo (92% Detrended CVD + 8% Impulso 3b)
      - Suavização e Histerese de Janela: flip_thr = ±11.0
    """
    fast_p = 4.0
    slow_p = 20.0
    smooth_a = 0.45 if is_win else 0.60
    flip_thr = 11.0
    alpha_fast = 2.0 / (fast_p + 1.0)
    alpha_slow = 2.0 / (slow_p + 1.0)
    alpha_band = 2.0 / (7.0 + 1.0)
    tick_sz = 5.0 if is_win else 0.5
    min_step = 500.0 if is_win else 100.0
    def_lot = 3.1 if is_win else 4.0
    if not m5_series:
        return []

    cum_eff = 0.0
    ema_eff_f = 0.0
    ema_eff_s = 0.0
    ema_step = 2500.0 if is_win else 400.0
    ema_hist = 0.0
    active_win_dir = 0
    prev_cum_eff = 0.0
    prev_hist = 0.0
    forces = []
    out = []

    for idx, b in enumerate(m5_series):
        dt = datetime.fromtimestamp(int(b.get("time", 0)), tz=timezone.utc)
        t_min = dt.hour * 60 + dt.minute
        o = float(b.get("open", b.get("close", 0.0)))
        h = float(b.get("high", o))
        l = float(b.get("low", o))
        c = float(b.get("close", o))
        rng = max(h - l, tick_sz)

        bv = float(b.get("buy_vol", 0.0))
        sv = float(b.get("sell_vol", 0.0))
        tv = max(1.0, bv + sv)
        lw = max(0.0, min(o, c) - l)
        uw = max(0.0, h - max(o, c))
        phi_wyk = (
            sv * ((c - l) / rng) * (0.80 + 1.40 * (lw / rng))
            - bv * ((h - c) / rng) * (0.80 + 1.40 * (uw / rng))
        )

        avg_buy = float(b.get("avg_buy_lot", def_lot))
        avg_sell = float(b.get("avg_sell_lot", def_lot))
        lot_imb = float(b.get("lot_imb", avg_buy / max(avg_sell, 0.1)))
        phi_port = tv * ((avg_buy - avg_sell) / max(0.5, avg_buy + avg_sell)) * 2.2

        inst_5m = float(b.get("inst_delta_bar", 0.0))
        inst_aggr_5m = float(b.get("inst_aggr_delta", inst_5m))
        inst_pass_5m = float(b.get("inst_pass_delta", 0.0))
        ret_5m = float(b.get("ret_delta_bar", 0.0))
        hft_5m = float(b.get("hft_delta_bar", 0.0))
        hft_churn = float(b.get("hft_churn_pct", 0.0))
        rlp_pct = float(b.get("rlp_pct", 0.0))
        delta_5m = float(b.get("delta_bar", 0.0))

        phi_inst = 0.90 * inst_aggr_5m + 0.75 * inst_pass_5m - 0.25 * ret_5m
        bar_force = 0.12 * phi_wyk + 0.18 * phi_port + 0.70 * phi_inst
        forces.append(bar_force)

        fp1 = forces[idx - 1] if idx >= 1 else bar_force
        fp2 = forces[idx - 2] if idx >= 2 else fp1
        imp3 = 0.45 * bar_force + 0.35 * fp1 + 0.20 * fp2

        cum_eff += bar_force
        if idx == 0:
            ema_eff_f = cum_eff
            ema_eff_s = cum_eff
            prev_cum_eff = 0.0
        else:
            ema_eff_f = alpha_fast * cum_eff + (1.0 - alpha_fast) * ema_eff_f
            ema_eff_s = alpha_slow * cum_eff + (1.0 - alpha_slow) * ema_eff_s

        smart_wave = 0.92 * (ema_eff_f - ema_eff_s) + 0.08 * imp3
        ema_step = alpha_band * max(abs(cum_eff - prev_cum_eff), min_step) + (1.0 - alpha_band) * ema_step
        prev_cum_eff = cum_eff

        raw_score = float(np.clip((smart_wave / max(1.0, ema_step * 1.4)) * 55.0, -100.0, 100.0))
        ema_hist = smooth_a * raw_score + (1.0 - smooth_a) * ema_hist
        hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)

        if active_win_dir == 0:
            active_win_dir = 1 if (hist_val >= 4.0 or (bar_force >= 0.0 and round(c, 2) >= round(o, 2))) else -1
        elif active_win_dir == 1 and hist_val <= -flip_thr:
            active_win_dir = -1
        elif active_win_dir == -1 and hist_val >= flip_thr:
            active_win_dir = 1

        inst_15m = sum(float(m5_series[k].get("inst_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))
        inst_aggr_15m = sum(float(m5_series[k].get("inst_aggr_delta", m5_series[k].get("inst_delta_bar", 0.0))) for k in range(max(0, idx - 2), idx + 1))
        inst_pass_10m = sum(float(m5_series[k].get("inst_pass_delta", 0.0)) for k in range(max(0, idx - 1), idx + 1))
        inst_pass_15m = sum(float(m5_series[k].get("inst_pass_delta", 0.0)) for k in range(max(0, idx - 2), idx + 1))
        ret_15m = sum(float(m5_series[k].get("ret_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))
        c_prev1 = float(m5_series[idx - 1].get("close", o)) if idx >= 1 else o
        c_prev2 = float(m5_series[idx - 2].get("close", o)) if idx >= 2 else c_prev1
        c_prev3 = float(m5_series[idx - 3].get("close", o)) if idx >= 3 else c_prev2
        dp1 = c - o
        dp2 = c - c_prev2
        dp3 = c - c_prev3

        out.append(dict(
            t_min=t_min, o=o, h=h, l=l, c=c,
            dp1=dp1, dp2=dp2, dp3=dp3,
            window_dir=active_win_dir, flow_hist=hist_val,
            hist_slope=hist_val - prev_hist,
            inst_5m=inst_5m, inst_15m=inst_15m, delta_5m=delta_5m,
            inst_aggr_5m=inst_aggr_5m, inst_aggr_15m=inst_aggr_15m,
            inst_pass_5m=inst_pass_5m, inst_pass_10m=inst_pass_10m, inst_pass_15m=inst_pass_15m,
            ret_5m=ret_5m, ret_15m=ret_15m,
            hft_5m=hft_5m, hft_churn=hft_churn,
            nr5=inst_aggr_5m + inst_pass_5m + hft_5m,
            nr15=inst_aggr_15m + inst_pass_15m,
            rlp_pct=rlp_pct, avg_buy=avg_buy, avg_sell=avg_sell, lot_imb=lot_imb,
        ))
        prev_hist = hist_val
    return out


def _bar_masks(f: dict, is_win: bool) -> dict:
    """Regras de `build_filter_masks` + 4 Players Profit + Divergência Preço vs Não-Varejo aplicadas a uma barra."""
    wdir, fhist, hslope = f["window_dir"], f["flow_hist"], f["hist_slope"]
    i5, i15, d5 = f["inst_5m"], f["inst_15m"], f["delta_5m"]
    ia5, ia15 = f.get("inst_aggr_5m", i5), f.get("inst_aggr_15m", i15)
    ip5, ip10, ip15 = f.get("inst_pass_5m", 0.0), f.get("inst_pass_10m", 0.0), f.get("inst_pass_15m", 0.0)
    r5, r15 = f.get("ret_5m", 0.0), f.get("ret_15m", 0.0)
    nr5, nr15 = f.get("nr5", ia5 + ip5), f.get("nr15", ia15 + ip15)
    dp1, dp2, dp3 = f.get("dp1", 0.0), f.get("dp2", 0.0), f.get("dp3", 0.0)
    lot_imb = f.get("lot_imb", 1.0)
    o, h, l, c = f["o"], f["h"], f["l"], f["c"]
    rng = max(h - l, 5.0 if is_win else 0.5)
    lwick = min(o, c) - l
    uwick = h - max(o, c)

    b1 = wdir == 1
    s1 = wdir == -1
    b2 = (wdir == 1) or (fhist >= -14.0) or (hslope >= 0.0)
    s2 = (wdir == -1) or (fhist <= 14.0) or (hslope <= 0.0)
    b3 = (i5 >= 0.0) or (i15 >= 0.0)
    s3 = (i5 <= 0.0) or (i15 <= 0.0)
    abs_buy = (lwick >= 0.22 * rng) or (c >= o)
    abs_sell = (uwick >= 0.22 * rng) or (c <= o)
    crash_thr = -12000.0 if is_win else -800.0
    surge_thr = 12000.0 if is_win else 800.0
    b4 = ((i5 >= 0.0) or (d5 >= 0.0) or abs_buy) and (i5 >= crash_thr)
    s4 = ((i5 <= 0.0) or (d5 <= 0.0) or abs_sell) and (i5 <= surge_thr)

    # 7_PROFIT_DEFENSE (Absorção Passiva Inst + Armadilha Varejo + Bloqueio Sweep Violento Contra)
    sweep_crash = (ia5 < (-4200.0 if is_win else -480.0)) and (lot_imb < 0.88) and (ip5 <= 0.0)
    sweep_surge = (ia5 > (4200.0 if is_win else 480.0)) and (lot_imb > 1.14) and (ip5 >= 0.0)
    b7 = ((i5 >= 0.0) or (i15 >= 0.0) or (ip5 > 0.0) or (r5 < 0.0 and ia5 >= -2500.0) or abs_buy) and (not sweep_crash)
    s7 = ((i5 <= 0.0) or (i15 <= 0.0) or (ip5 < 0.0) or (r5 > 0.0 and ia5 <= 2500.0) or abs_sell) and (not sweep_surge)

    # 8_PROFIT_SWEEP (Sweep / Ignição Institucional + Ticket Médio Agressor a Favor)
    b8 = ((ia5 >= 0.0) or (ia15 >= 0.0) or (lot_imb >= 1.02) or (b2 and b4)) and (ia5 >= (-5500.0 if is_win else -450.0)) and (lot_imb >= 0.88)
    s8 = ((ia5 <= 0.0) or (ia15 <= 0.0) or (lot_imb <= 0.98) or (s2 and s4)) and (ia5 <= (5500.0 if is_win else 450.0)) and (lot_imb <= 1.14)

    # 9_PROFIT_INST_RET (Fluxo Institucional + Divergência Varejo + Ticket Médio sem Sweep Oposto)
    sweep_crash_w = (ia5 < (-9000.0 if is_win else -650.0)) and (lot_imb < 0.82)
    sweep_surge_w = (ia5 > (9000.0 if is_win else 650.0)) and (lot_imb > 1.22)
    b9 = ((i5 >= 0.0) or (i15 >= 0.0) or (ip5 > 0.0 and r5 < 0.0) or (lot_imb >= 1.04)) and (not sweep_crash_w)
    s9 = ((i5 <= 0.0) or (i15 <= 0.0) or (ip5 < 0.0 and r5 > 0.0) or (lot_imb <= 0.96)) and (not sweep_surge_w)

    # 10_PROFIT_SMART_WALL (Janela s/ Explosão + Profit Defense)
    b10 = b2 and b7
    s10 = s2 and s7

    # 11_PROFIT_WALL_SHIELD (Janela s/ Explosão + Profit Inst/Ret Divergence)
    b11 = b2 and b9
    s11 = s2 and s9

    # 12_NR_WALL_TRAP_DIV (Divergência Armadilha Varejo na Wall vs Absorção/Agressão Não-Varejo - WDO_07 [8.73x], EST_14 [7.27x])
    b12 = (
        ((r5 < 0 or r15 < 0) and (ip5 >= 0 or ia5 > 0 or nr15 > 0))
        or ((i5 > 0 and i15 > 0) and lot_imb >= 1.02)
        or (lwick >= 0.28 * rng and (ip5 > 0 or ia5 >= 0))
    ) and (not sweep_crash) and b2
    s12 = (
        ((r5 > 0 or r15 > 0) and (ip5 <= 0 or ia5 < 0 or nr15 < 0))
        or ((i5 < 0 and i15 < 0) and lot_imb <= 0.98)
        or (uwick >= 0.28 * rng and (ip5 < 0 or ia5 <= 0))
    ) and (not sweep_surge) and s2

    # 13_NR_PRICE_ABS_DIV (Divergência Preço vs Absorção Passiva / Agressão Não-Varejo - WDO_01 [9.35x], WDO_05 [8.93x])
    fomo_retail_buy = (r5 > (500.0 if is_win else 70.0)) and (ip5 < (-300.0 if is_win else -45.0)) and (ia5 <= 0)
    fomo_retail_sell = (r5 < (-500.0 if is_win else -70.0)) and (ip5 > (300.0 if is_win else 45.0)) and (ia5 >= 0)
    nr_heavy_against_buy = (ia5 < (-2000.0 if is_win else -250.0)) and (ip5 <= 0) and (i15 < (-2500.0 if is_win else -300.0))
    nr_heavy_against_sell = (ia5 > (2000.0 if is_win else 250.0)) and (ip5 >= 0) and (i15 > (2500.0 if is_win else 300.0))
    b13 = b9 and (not fomo_retail_buy) and (not nr_heavy_against_buy)
    s13 = s9 and (not fomo_retail_sell) and (not nr_heavy_against_sell)

    # 14_NR_BREAKOUT_SQUEEZE (Sweep Não-Varejo + Squeeze Varejo s/ Absorção Contrária - EST_15 [6.66x], EST_01 [3.57x])
    b14 = b8 and b13
    s14 = s8 and s13

    # 15_NR_IGNITION_DIV (Divergência Ignição 15m vs Distribuição Não-Varejo - EST_04 [5.71x])
    price_up_nr_selling = (dp3 > (150.0 if is_win else 3.5)) and (nr15 < (-1200.0 if is_win else -180.0))
    price_dn_nr_buying = (dp3 < (-150.0 if is_win else -3.5)) and (nr15 > (1200.0 if is_win else 180.0))
    b15 = b13 and (not price_up_nr_selling) and (lot_imb >= 0.89 or ip5 > 0)
    s15 = s13 and (not price_dn_nr_buying) and (lot_imb <= 1.12 or ip5 < 0)

    # 16_NR_DIV_ABS_OR_AGGR (Divergência Explícita Preço na Wall vs Absorção Passiva ou Agressão Não-Varejo - EST_07 [8.60x], EST_16 [4.30x])
    b16 = (
        ((dp1 <= 0 or dp2 <= 0) and (ip5 > 0 or ip10 > 0 or nr5 > 0))
        or (r5 < 0 and (ip5 >= 0 or ia5 > 0 or i15 > 0))
        or (ia5 > 0 and i15 > 0 and lot_imb >= 1.03 and r5 <= ia5)
    ) and (ia5 >= (-3000.0 if is_win else -350.0))
    s16 = (
        ((dp1 >= 0 or dp2 >= 0) and (ip5 < 0 or ip10 < 0 or nr5 < 0))
        or (r5 > 0 and (ip5 <= 0 or ia5 < 0 or i15 < 0))
        or (ia5 < 0 and i15 < 0 and lot_imb <= 0.97 and r5 >= ia5)
    ) and (ia5 <= (3000.0 if is_win else 350.0))

    # 17_NR_SQUEEZE_CLEAN (Divergência Limpa Preço 15m vs Fluxo Não-Varejo - WDO_02 [3.38x])
    b17 = (
        ((i5 >= 0) or (i15 >= 0) or (ip5 > 0 and r5 < 0) or (lot_imb >= 1.03))
        and not (r5 > (400.0 if is_win else 60.0) and (ip5 < (-250.0 if is_win else -40.0) or ia5 < 0))
        and not (dp3 > (120.0 if is_win else 3.0) and nr15 < (-800.0 if is_win else -120.0))
        and not (ia5 < (-2200.0 if is_win else -250.0) and lot_imb < 0.92)
    )
    s17 = (
        ((i5 <= 0) or (i15 <= 0) or (ip5 < 0 and r5 > 0) or (lot_imb <= 0.97))
        and not (r5 < (-400.0 if is_win else -60.0) and (ip5 > (250.0 if is_win else 40.0) or ia5 > 0))
        and not (dp3 < (-120.0 if is_win else -3.0) and nr15 > (800.0 if is_win else 120.0))
        and not (ia5 > (2200.0 if is_win else 250.0) and lot_imb > 1.08)
    )

    # 18_NR_ASG_PLUS_DIV (Janela S Explosão + Divergência Preço vs Não-Varejo - WDO_09 [4.42x])
    ret_fomo_top = (r5 > (1200.0 if is_win else 180.0)) and (ia5 < (-1200.0 if is_win else -180.0)) and (ip5 < 0)
    ret_panic_bot = (r5 < (-1200.0 if is_win else -180.0)) and (ia5 > (1200.0 if is_win else 180.0)) and (ip5 > 0)
    nr_trap_b = (r5 > (600.0 if is_win else 90.0)) and (ip5 < (-400.0 if is_win else -60.0)) and (ia5 <= 0)
    nr_trap_s = (r5 < (-600.0 if is_win else -90.0)) and (ip5 > (400.0 if is_win else 60.0)) and (ia5 >= 0)
    b18 = b2 and (not ret_fomo_top) and (not nr_trap_b) and (not sweep_crash)
    s18 = s2 and (not ret_panic_bot) and (not nr_trap_s) and (not sweep_surge)

    return {
        "1_JANELA_ASG": (b1, s1),
        "2_JANELA_S_EXPLOSAO": (b2, s2),
        "3_FLUXO_INST": (b3, s3),
        "4_FLUXO_ABSORCAO": (b4, s4),
        "5_COMBO_ESTRITO": (b1 and b4, s1 and s4),
        "6_COMBO_SMART": (b2 and b4, s2 and s4),
        "7_PROFIT_DEFENSE": (b7, s7),
        "8_PROFIT_SWEEP": (b8, s8),
        "9_PROFIT_INST_RET": (b9, s9),
        "10_PROFIT_SMART_WALL": (b10, s10),
        "11_PROFIT_WALL_SHIELD": (b11, s11),
        "12_NR_WALL_TRAP_DIV": (b12, s12),
        "13_NR_PRICE_ABS_DIV": (b13, s13),
        "14_NR_BREAKOUT_SQUEEZE": (b14, s14),
        "15_NR_IGNITION_DIV": (b15, s15),
        "16_NR_DIV_ABS_OR_AGGR": (b16, s16),
        "17_NR_SQUEEZE_CLEAN": (b17, s17),
        "18_NR_ASG_PLUS_DIV": (b18, s18),
    }


FLOW_MIN_PKL = os.path.join(ROOT_DIR, "data", "research", "setup_flow_min_v1", "flow_masks.pkl")
FLOW_MIN_MANIFEST = os.path.join(ROOT_DIR, "research", "setup_parity", "flow_min_manifest.json")


def load_flow_tables(source: str = "min"):
    """
    FLOW[asset][filtro][(date, tmin)] = (compra_ok, venda_ok) + datas cobertas.

    source="min" (padrão, decisão de 10/11/2026): os 18 filtros calculados do `.min` do Profit por
    `research/setup_parity/build_flow_min.py` — a mesma fonte do motor ao vivo. Falha se o hash não bater.
    source="legacy": caminho antigo (`.pkl` MT5 + JSONs de sessão). Tem o bug de deixar os filtros 12–18
    sem dado nos dias cobertos pelo `.pkl`; mantido só para comparação.
    """
    if source == "min":
        import hashlib
        man = json.load(open(FLOW_MIN_MANIFEST, encoding="utf-8"))
        if hashlib.sha256(open(FLOW_MIN_PKL, "rb").read()).hexdigest() != man["sha256"]:
            raise RuntimeError("flow_masks.pkl diverge do manifest — rode research/setup_parity/build_flow_min.py")
        with open(FLOW_MIN_PKL, "rb") as pf:
            data = pickle.load(pf)
        covered = sorted(set(data["days"]["WIN"]) | set(data["days"]["WDO"]))
        return data["flow"], covered
    return _load_flow_tables_legacy()


def _load_flow_tables_legacy():
    flow = {a: {fn: {} for fn in FILTER_NAMES[1:]} for a in ("WIN", "WDO")}
    covered_dates = set()
    covered_dates = set()
    if os.path.exists(PKL_FLOW_2026):
        with open(PKL_FLOW_2026, "rb") as pf:
            pkl_data = pickle.load(pf)
        for asset in ("WIN", "WDO"):
            if asset in pkl_data:
                for fn, tbl in pkl_data[asset].items():
                    if fn in flow[asset]:
                        flow[asset][fn].update(tbl)
                        for dt_str, _ in tbl.keys():
                            covered_dates.add(str(dt_str))

    files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json")))
    for fp in files:
        date = os.path.basename(fp).replace(".json", "")
        if date in covered_dates:
            continue
        with open(fp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for asset in ("WIN", "WDO"):
            series = data.get(asset, {}).get("m5_cvd_series", [])
            for f in _session_features(series, is_win=(asset == "WIN")):
                for fn, ok in _bar_masks(f, is_win=(asset == "WIN")).items():
                    flow[asset][fn][(date, f["t_min"])] = ok
        covered_dates.add(date)
    return flow, sorted(covered_dates)


MISSING_FLOW_LOOKUPS = {"WIN": 0, "WDO": 0}


def make_sig_filter(flow: dict, asset: str, filter_name: str, strict: bool = True):
    """
    Callable f(date, b1_tmin, direção) -> bool para os simuladores. None = sem filtro.
    strict=True (padrão desde 10/11/2026): barra sem dado de fluxo BLOQUEIA a entrada — no ao vivo isso
    protege contra `.min` atrasado. O contador `MISSING_FLOW_LOOKUPS` registra quantas vezes aconteceu.
    """
    if filter_name == "0_BASE_MT5":
        return None
    table = flow[asset][filter_name]

    def _f(date: str, b1_tmin: int, sig_dir: int) -> bool:
        ok = table.get((str(date), int(b1_tmin)))
        if ok is None:
            MISSING_FLOW_LOOKUPS[asset] += 1
            return not strict
        return bool(ok[0] if sig_dir == 1 else ok[1])

    return _f

