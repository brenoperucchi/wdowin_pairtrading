# -*- coding: utf-8 -*-
"""
Benchmark A/B Isolado: Fluxo A.S.G (5174) vs. Fluxo Smart Money (5176)
======================================================================
Compara sobre todo o histórico de 2026 (02/01/2026 a 06/11/2026) o impacto
de substituir o cálculo de Fluxo/Janela A.S.G atual da 5174 pela metodologia
do Fluxo Smart Money (3 Motores: Absorção Wyckoff + Porte Lote + Não-Varejo) da 5176:

  - Cenário 1 (Baseline 5174 — A.S.G Atual):
      85% Oscilador CVD Institucional Agressor (EMA 5/18 WIN, 4/22 WDO) + 15% Canal Preço,
      suavizado e com trava de histerese flip_thr = ±11.0.

  - Cenário 2A (Smart Money Direto — Janela Pura s/ Histerese):
      Janela guiada diretamente pelo sinal de `smart_swing_wave` (>= 0 Compra, < 0 Venda)
      e inclinação imediata da onda (`wave_slope`), mantendo os insumos brutos das barras.

  - Cenário 2B (Smart Money Direto Total — Janela + Insumos i5/i15 substituídos pela Força Efetiva):
      Além da janela direta por `smart_swing_wave`, substitui `inst_5m` e `inst_15m`
      pela Força Efetiva dos 3 Motores (`bar_force` e `swing_impulse_3b`).

  - Cenário 3A (Smart Money + Histerese de Janela ±11):
      Normaliza a onda `smart_swing_wave` (3 Motores) para a escala [-100, +100] via
      passo adaptativo EMA, aplica suavização e trava de virada `flip_thr = ±11.0`.

  - Cenário 3B (Smart Money + Histerese ±11 + Insumos 3 Motores):
      Janela Smart Money com histerese ±11 combinada com `bar_force` / `swing_impulse_3b`
      nos filtros de fluxo.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.profit_wall_players_engine import _build_from_profit_min_m1_m5, _load_profit_min_index
from research.flow_window_asg.flow_filters import FILTER_NAMES, _bar_masks, _session_features
from research.flow_window_asg import generate_portfolio_6_json as gp
from core.setups_runner import _load_market

TOP8_IDS = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]
ALL_EVAL_IDS = [
    "EST_04", "EST_07", "EST_13", "EST_14", "EST_15",
    "WDO_01", "WDO_05", "WDO_07",
    "EST_01", "EST_16", "WIN_E2", "WDO_02", "WDO_09", "WDO_10",
]


def _compute_smart_money_features(
    m5_series: list,
    is_win: bool,
    use_hysteresis: bool = False,
    replace_inst_with_3motor: bool = False,
    flip_thr: float = 11.0,
) -> Tuple[List[dict], int]:
    """
    Calcula as features por barra M5 usando o motor de Fluxo Smart Money (5176):
      1) Absorção Oculta na Pedra (Wyckoff Effort vs Result): 45%
      2) Assimetria de Porte / Ticket Médio (Urgência de Lote Grande): 25%
      3) Pressão Institucional + Defesa Passiva vs Armadilha de Varejo: 30%
    Retorna (lista_de_features_para_bar_masks, numero_de_viradas_de_janela_no_dia).
    """
    if not m5_series:
        return [], 0

    tick_sz_val = 5.0 if is_win else 0.5
    smooth_a = 0.45 if is_win else 0.60
    alpha_band = 2.0 / (7.0 + 1.0)

    cum_eff = 0.0
    ema_eff_fast = 0.0
    ema_eff_slow = 0.0
    ema_wave_scale = 2500.0 if is_win else 350.0
    ema_hist = 0.0
    prev_hist = 0.0
    active_win_dir = 0
    flips_count = 0

    forces: List[float] = []
    out: List[dict] = []

    for idx, b in enumerate(m5_series):
        dt = datetime.fromtimestamp(int(b.get("time", 0)), tz=timezone.utc)
        t_min = dt.hour * 60 + dt.minute
        o = float(b.get("open", b.get("close", 0.0)))
        h = float(b.get("high", o))
        l = float(b.get("low", o))
        c = float(b.get("close", o))
        rng_e = max(h - l, tick_sz_val)

        bv_e = float(b.get("buy_vol", 0.0))
        sv_e = float(b.get("sell_vol", 0.0))
        tv_e = max(1.0, bv_e + sv_e)
        lw_e = max(0.0, min(o, c) - l)
        uw_e = max(0.0, h - max(o, c))

        # Motor 1: Absorção Oculta Wyckoff na Pedra (45%)
        abs_buy_w = sv_e * ((c - l) / rng_e) * (0.80 + 1.40 * (lw_e / rng_e))
        abs_sell_w = bv_e * ((h - c) / rng_e) * (0.80 + 1.40 * (uw_e / rng_e))
        phi_wyckoff = round(abs_buy_w - abs_sell_w, 0)

        # Motor 2: Assimetria de Porte / Ticket Médio (25%)
        avg_buy = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
        avg_sell = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))
        lot_imb = float(b.get("lot_imb", avg_buy / max(avg_sell, 0.1)))
        phi_porte = round(tv_e * ((avg_buy - avg_sell) / max(0.5, avg_buy + avg_sell)) * 2.2, 0)

        # Motor 3: Não-Varejo (Agressor + Passivo) vs Varejo (30%)
        inst_5m = float(b.get("inst_delta_bar", 0.0))
        inst_aggr_5m = float(b.get("inst_aggr_delta", inst_5m))
        inst_pass_5m = float(b.get("inst_pass_delta", 0.0))
        ret_5m = float(b.get("ret_delta_bar", 0.0))
        hft_5m = float(b.get("hft_delta_bar", 0.0))
        hft_churn = float(b.get("hft_churn_pct", 0.0))
        rlp_pct = float(b.get("rlp_pct", 0.0))
        delta_5m = float(b.get("delta_bar", 0.0))

        phi_inst = round(0.55 * inst_aggr_5m + 1.15 * inst_pass_5m - 0.85 * ret_5m, 0)

        # Força Efetiva da Barra (combinação física dos 3 motores)
        bar_force = round(0.45 * phi_wyckoff + 0.25 * phi_porte + 0.30 * phi_inst, 0)
        forces.append(bar_force)

        f_prev1 = forces[idx - 1] if idx >= 1 else bar_force
        f_prev2 = forces[idx - 2] if idx >= 2 else f_prev1
        swing_impulse_3b = round(0.45 * bar_force + 0.35 * f_prev1 + 0.20 * f_prev2, 0)

        cum_eff += bar_force
        if idx == 0:
            ema_eff_fast = cum_eff
            ema_eff_slow = cum_eff
        else:
            ema_eff_fast = 0.50 * cum_eff + 0.50 * ema_eff_fast
            ema_eff_slow = (2.0 / 11.0) * cum_eff + (1.0 - 2.0 / 11.0) * ema_eff_slow

        detrended_cvd = ema_eff_fast - ema_eff_slow
        smart_wave = round(0.55 * detrended_cvd + 0.45 * swing_impulse_3b, 0)

        # Normalização para escala [-100, +100]
        ema_wave_scale = alpha_band * max(abs(smart_wave), 600.0 if is_win else 90.0) + (1.0 - alpha_band) * ema_wave_scale
        raw_norm = float(np.clip((smart_wave / max(1.0, ema_wave_scale * 1.15)) * 55.0, -100.0, 100.0))

        if use_hysteresis:
            ema_hist = smooth_a * raw_norm + (1.0 - smooth_a) * ema_hist
            hist_val = round(float(np.clip(ema_hist, -100.0, 100.0)), 1)
            prev_dir = active_win_dir
            if active_win_dir == 0:
                active_win_dir = 1 if (hist_val >= 4.0 or smart_wave >= 0) else -1
            elif active_win_dir == 1 and hist_val <= -flip_thr:
                active_win_dir = -1
            elif active_win_dir == -1 and hist_val >= flip_thr:
                active_win_dir = 1
            if prev_dir != 0 and active_win_dir != prev_dir:
                flips_count += 1
        else:
            # Smart Money Direto (sem histerese: vira imediatamente no cruzamento de zero da onda)
            hist_val = round(raw_norm, 1)
            prev_dir = active_win_dir
            active_win_dir = 1 if smart_wave >= 0 else -1
            if prev_dir != 0 and active_win_dir != prev_dir:
                flips_count += 1

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

        eff_i5 = bar_force if replace_inst_with_3motor else inst_5m
        eff_i15 = sum(forces[max(0, idx - 2) : idx + 1]) if replace_inst_with_3motor else inst_15m

        out.append(dict(
            t_min=t_min, o=o, h=h, l=l, c=c,
            dp1=dp1, dp2=dp2, dp3=dp3,
            window_dir=active_win_dir,
            flow_hist=hist_val,
            hist_slope=hist_val - prev_hist,
            inst_5m=eff_i5,
            inst_15m=eff_i15,
            delta_5m=bar_force if replace_inst_with_3motor else delta_5m,
            inst_aggr_5m=inst_aggr_5m,
            inst_aggr_15m=inst_aggr_15m,
            inst_pass_5m=inst_pass_5m + (0.35 * phi_wyckoff if replace_inst_with_3motor else 0.0),
            inst_pass_10m=inst_pass_10m,
            inst_pass_15m=inst_pass_15m,
            ret_5m=ret_5m,
            ret_15m=ret_15m,
            hft_5m=hft_5m,
            hft_churn=hft_churn,
            nr5=(bar_force if replace_inst_with_3motor else (inst_aggr_5m + inst_pass_5m + hft_5m)),
            nr15=(eff_i15 if replace_inst_with_3motor else (inst_aggr_15m + inst_pass_15m)),
            rlp_pct=rlp_pct,
            avg_buy=avg_buy,
            avg_sell=avg_sell,
            lot_imb=lot_imb,
        ))
        prev_hist = hist_val

    return out, flips_count


def _count_asg_flips(feats: List[dict]) -> int:
    flips = 0
    prev = 0
    for f in feats:
        d = f["window_dir"]
        if prev != 0 and d != prev:
            flips += 1
        prev = d
    return flips


def summarize_trades(trades: List[dict]) -> dict:
    if not trades:
        return {"ops": 0, "wr": 0.0, "pf": 0.0, "brl": 0.0, "pts": 0.0, "mdd": 0.0, "ret_dd": 0.0, "m_pos": 0, "m_tot": 0}
    df = pd.DataFrame(trades).sort_values(["date", "time"]).reset_index(drop=True)
    brl = df["brl_1c"].astype(float).values
    pts = df["pts"].astype(float).values
    wins = int((brl > 0).sum())
    ops = len(brl)
    wr = (wins / ops) * 100.0 if ops else 0.0
    gains = float(brl[brl > 0].sum())
    losses = float(abs(brl[brl < 0].sum()))
    pf = (gains / losses) if losses > 0 else (9.99 if gains > 0 else 0.0)

    # Drawdown diário acumulado (mesma métrica oficial do dashboard)
    by_day = df.groupby("date")["brl_1c"].sum()
    cum = by_day.cumsum().values
    peak = np.maximum.accumulate(np.insert(cum, 0, 0.0))[1:]
    dd = peak - cum
    mdd = float(dd.max()) if len(dd) else 0.0
    tot_brl = float(brl.sum())
    ret_dd = (tot_brl / mdd) if mdd > 0 else 99.9

    df["month"] = df["date"].str.slice(0, 7)
    by_m = df.groupby("month")["brl_1c"].sum()
    m_pos = int((by_m > 0).sum())
    m_tot = len(by_m)

    return {
        "ops": ops,
        "wr": round(wr, 1),
        "pf": round(pf, 2),
        "brl": round(tot_brl, 0),
        "pts": round(float(pts.sum()), 1),
        "mdd": round(mdd, 0),
        "ret_dd": round(ret_dd, 2),
        "m_pos": m_pos,
        "m_tot": m_tot,
    }


def main():
    t0 = time.time()
    start_d, end_d = "2026-01-02", "2026-11-06"
    print(f"[1/3] Carregando séries M5 do .min ({start_d} a {end_d})...")

    raw_series: Dict[str, Dict[str, list]] = {"WIN": {}, "WDO": {}}
    for asset in ("WIN", "WDO"):
        is_win = asset == "WIN"
        idx_map = _load_profit_min_index(asset)
        dates = [d for d in sorted(idx_map) if start_d <= d <= end_d]
        for d in dates:
            pay = _build_from_profit_min_m1_m5(
                idx_map[d], asset, d, [], 60.0 if is_win else 2.5, 5.0 if is_win else 0.5
            )
            raw_series[asset][d] = (pay or {}).get("m5_cvd_series", [])
        print(f"  -> {asset}: {len(dates)} pregões carregados ({time.time() - t0:.1f}s)")

    # Construir as tabelas de fluxo para os 5 cenários
    scenarios = {
        "C1_ASG_ATUAL": "Cenário 1 · A.S.G Atual (Baseline 5174)",
        "C2A_SM_DIRETO_JANELA": "Cenário 2A · Smart Money Direto (Só Janela)",
        "C2B_SM_DIRETO_TOTAL": "Cenário 2B · Smart Money Direto (Janela + 3 Motores)",
        "C3A_SM_HISTERESE_JANELA": "Cenário 3A · Smart Money + Histerese ±11 (Só Janela)",
        "C3B_SM_HISTERESE_TOTAL": "Cenário 3B · Smart Money + Histerese ±11 (Janela + 3 Motores)",
    }

    flow_by_scen = {
        sc: {a: {fn: {} for fn in FILTER_NAMES[1:]} for a in ("WIN", "WDO")}
        for sc in scenarios
    }
    flips_stats = {sc: {"WIN": [], "WDO": []} for sc in scenarios}
    agreement_stats = {sc: {"WIN": [0, 0], "WDO": [0, 0]} for sc in scenarios if sc != "C1_ASG_ATUAL"}

    print("[2/3] Calculando janelas, viradas e máscaras dos 18 filtros para cada cenário...")
    for asset in ("WIN", "WDO"):
        is_win = asset == "WIN"
        for d, series in raw_series[asset].items():
            # C1: ASG Atual
            f_c1 = _session_features(series, is_win=is_win)
            flips_stats["C1_ASG_ATUAL"][asset].append(_count_asg_flips(f_c1))
            c1_wdir_map = {}
            for f in f_c1:
                c1_wdir_map[f["t_min"]] = f["window_dir"]
                for fn, ok in _bar_masks(f, is_win=is_win).items():
                    flow_by_scen["C1_ASG_ATUAL"][asset][fn][(d, f["t_min"])] = ok

            # C2A: Smart Money Direto (Só Janela)
            f_c2a, fl_2a = _compute_smart_money_features(series, is_win, use_hysteresis=False, replace_inst_with_3motor=False)
            flips_stats["C2A_SM_DIRETO_JANELA"][asset].append(fl_2a)
            for f in f_c2a:
                agreement_stats["C2A_SM_DIRETO_JANELA"][asset][1] += 1
                if f["window_dir"] == c1_wdir_map.get(f["t_min"]):
                    agreement_stats["C2A_SM_DIRETO_JANELA"][asset][0] += 1
                for fn, ok in _bar_masks(f, is_win=is_win).items():
                    flow_by_scen["C2A_SM_DIRETO_JANELA"][asset][fn][(d, f["t_min"])] = ok

            # C2B: Smart Money Direto Total (Janela + 3 Motores)
            f_c2b, fl_2b = _compute_smart_money_features(series, is_win, use_hysteresis=False, replace_inst_with_3motor=True)
            flips_stats["C2B_SM_DIRETO_TOTAL"][asset].append(fl_2b)
            for f in f_c2b:
                agreement_stats["C2B_SM_DIRETO_TOTAL"][asset][1] += 1
                if f["window_dir"] == c1_wdir_map.get(f["t_min"]):
                    agreement_stats["C2B_SM_DIRETO_TOTAL"][asset][0] += 1
                for fn, ok in _bar_masks(f, is_win=is_win).items():
                    flow_by_scen["C2B_SM_DIRETO_TOTAL"][asset][fn][(d, f["t_min"])] = ok

            # C3A: Smart Money + Histerese ±11 (Só Janela)
            f_c3a, fl_3a = _compute_smart_money_features(series, is_win, use_hysteresis=True, replace_inst_with_3motor=False, flip_thr=11.0)
            flips_stats["C3A_SM_HISTERESE_JANELA"][asset].append(fl_3a)
            for f in f_c3a:
                agreement_stats["C3A_SM_HISTERESE_JANELA"][asset][1] += 1
                if f["window_dir"] == c1_wdir_map.get(f["t_min"]):
                    agreement_stats["C3A_SM_HISTERESE_JANELA"][asset][0] += 1
                for fn, ok in _bar_masks(f, is_win=is_win).items():
                    flow_by_scen["C3A_SM_HISTERESE_JANELA"][asset][fn][(d, f["t_min"])] = ok

            # C3B: Smart Money + Histerese ±11 Total (Janela + 3 Motores)
            f_c3b, fl_3b = _compute_smart_money_features(series, is_win, use_hysteresis=True, replace_inst_with_3motor=True, flip_thr=11.0)
            flips_stats["C3B_SM_HISTERESE_TOTAL"][asset].append(fl_3b)
            for f in f_c3b:
                agreement_stats["C3B_SM_HISTERESE_TOTAL"][asset][1] += 1
                if f["window_dir"] == c1_wdir_map.get(f["t_min"]):
                    agreement_stats["C3B_SM_HISTERESE_TOTAL"][asset][0] += 1
                for fn, ok in _bar_masks(f, is_win=is_win).items():
                    flow_by_scen["C3B_SM_HISTERESE_TOTAL"][asset][fn][(d, f["t_min"])] = ok

    print(f"[3/3] Rodando simuladores MT5 para os 5 cenários ({time.time() - t0:.1f}s)...")
    gp.START_DATE, gp.END_DATE = start_d, end_d
    mk = _load_market()

    results_by_scen = {}
    for sc, sc_label in scenarios.items():
        t_sc = time.time()
        out = gp.run_all_strategies_for_mode(*mk, flow_by_scen[sc], use_flow=True)
        for sid in out:
            out[sid] = [t for t in out[sid] if start_d <= t["date"] <= end_d]
        results_by_scen[sc] = out
        print(f"  -> {sc_label} concluído em {time.time() - t_sc:.1f}s")

    # ── RELATÓRIO 1: VIRADAS DE JANELA POR DIA & CONCORDÂNCIA DIRETA COM A.S.G ──
    print("\n" + "=" * 105)
    print("1. DINÂMICA DE VIRADAS DE JANELA (MÉDIA DE VIRADAS/DIA NOS 212 PREGÕES) & CONCORDÂNCIA COM A.S.G")
    print("=" * 105)
    print(f"{'CENÁRIO':<56} | {'WIN Flips/Dia':>13} | {'WDO Flips/Dia':>13} | {'Acordo WIN':>10} | {'Acordo WDO':>10}")
    print("-" * 105)
    for sc, sc_label in scenarios.items():
        w_fl = np.mean(flips_stats[sc]["WIN"])
        d_fl = np.mean(flips_stats[sc]["WDO"])
        if sc == "C1_ASG_ATUAL":
            ag_w, ag_d = "100.0%", "100.0%"
        else:
            aw = agreement_stats[sc]["WIN"]
            ad = agreement_stats[sc]["WDO"]
            ag_w = f"{(aw[0] / max(1, aw[1])) * 100.0:.1f}%"
            ag_d = f"{(ad[0] / max(1, ad[1])) * 100.0:.1f}%"
        print(f"{sc_label:<56} | {w_fl:>13.2f} | {d_fl:>13.2f} | {ag_w:>10} | {ag_d:>10}")

    # ── RELATÓRIO 2: CARTEIRA TOP 8 ELITE M5 DA 5174 (5 WIN + 3 WDO) E SUBCARTEIRAS ──
    print("\n" + "=" * 105)
    print("2. IMPACTO CONSOLIDADO NA CARTEIRA OFICIAL DA 5174 (TOP 8 ELITE: 5 WIN + 3 WDO)")
    print("=" * 105)
    print(f"{'CENÁRIO':<56} | {'Ops':>5} | {'WR%':>5} | {'PF':>5} | {'Lucro R$':>10} | {'MaxDD R$':>9} | {'Ret/DD':>7} | {'Meses+'}")
    print("-" * 105)
    for sc, sc_label in scenarios.items():
        top8_trades = [t for sid in TOP8_IDS for t in results_by_scen[sc].get(sid, [])]
        st = summarize_trades(top8_trades)
        print(
            f"{sc_label:<56} | {st['ops']:>5d} | {st['wr']:>4.1f}% | {st['pf']:>5.2f} | "
            f"R$ {st['brl']:>7.0f} | -R$ {st['mdd']:>5.0f} | {st['ret_dd']:>6.2f}x | {st['m_pos']}/{st['m_tot']}"
        )

    print("\n--- Subcarteira WIN (EST_04 + EST_07 + EST_13 + EST_14 + EST_15) ---")
    for sc, sc_label in scenarios.items():
        win5_trades = [t for sid in ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15"] for t in results_by_scen[sc].get(sid, [])]
        st = summarize_trades(win5_trades)
        print(
            f"{sc_label:<56} | {st['ops']:>5d} | {st['wr']:>4.1f}% | {st['pf']:>5.2f} | "
            f"R$ {st['brl']:>7.0f} | -R$ {st['mdd']:>5.0f} | {st['ret_dd']:>6.2f}x | {st['m_pos']}/{st['m_tot']}"
        )

    print("\n--- Subcarteira WDO (WDO_01 + WDO_05 + WDO_07) ---")
    for sc, sc_label in scenarios.items():
        wdo3_trades = [t for sid in ["WDO_01", "WDO_05", "WDO_07"] for t in results_by_scen[sc].get(sid, [])]
        st = summarize_trades(wdo3_trades)
        print(
            f"{sc_label:<56} | {st['ops']:>5d} | {st['wr']:>4.1f}% | {st['pf']:>5.2f} | "
            f"R$ {st['brl']:>7.0f} | -R$ {st['mdd']:>5.0f} | {st['ret_dd']:>6.2f}x | {st['m_pos']}/{st['m_tot']}"
        )

    # ── RELATÓRIO 3: DETALHAMENTO POR ESTRATÉGIA (C1 vs C2A vs C2B vs C3A vs C3B) ──
    print("\n" + "=" * 105)
    print("3. COMPARATIVO ESTRATÉGIA POR ESTRATÉGIA (LUCRO R$ | PF | RET/DD | OPS)")
    print("=" * 105)
    for sid in ALL_EVAL_IDS:
        flt_name = gp.BEST_FLOW_FILTER_MAP.get(sid, "")
        print(f"\n>>> {sid} (Filtro: {flt_name})")
        print(f"  {'Cenário':<54} | {'Ops':>5} | {'WR%':>5} | {'PF':>5} | {'Lucro R$':>10} | {'MaxDD R$':>9} | {'Ret/DD':>7} | {'Meses+'}")
        for sc, sc_label in scenarios.items():
            st = summarize_trades(results_by_scen[sc].get(sid, []))
            print(
                f"  {sc_label:<54} | {st['ops']:>5d} | {st['wr']:>4.1f}% | {st['pf']:>5.2f} | "
                f"R$ {st['brl']:>7.0f} | -R$ {st['mdd']:>5.0f} | {st['ret_dd']:>6.2f}x | {st['m_pos']}/{st['m_tot']}"
            )


if __name__ == "__main__":
    main()
