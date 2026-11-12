# -*- coding: utf-8 -*-
"""
Gera `data/processed/portfolio_4_sistematicas_equity_v1.json` (Versão 4.0)
contendo TODAS AS 11 ESTRATÉGIAS ATIVAS (7 WIN + 4 WDO) 100% alinhadas ao
Strategy Tester do MT5, incluindo:
  1) Base MT5 Oficial (Otimização TP/SL/BE nas Walls & MidWalls + Filtro NWE Direção/Bandas)
  2) Modo C/ Filtro de Fluxo/Janela do Dashboard (Melhor filtro de fluxo/janela por estratégia)
  3) Tabela Comparativa Completa das 11 Estratégias (Sem NWE vs Base MT5 Walls+NWE vs C/ Fluxo/Janela)
  4) Compatibilidade total com as chaves legadas (WDO_11 -> WDO_02, WDO_S2 -> WDO_10)

Custos operacionais B3 embutidos:
  - WIN: R$ 2,00 por contrato negociado (10 pts = R$ 2,00/lote)
  - WDO: R$ 5,00 por contrato negociado (0,5 pt = R$ 5,00/lote)
"""
import os
import sys
import glob
import json
import functools
from datetime import datetime, timezone
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from research.optimizers import optimize_existing_16_setups as o16
from research.optimizers import sg_sim
from research.optimizers import wdo_mt5_sim as wsim
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
from research.flow_window_asg.flow_filters import load_flow_tables, make_sig_filter

sg_sim.load_m5_m1_wdo_gex = functools.lru_cache(maxsize=1)(sg_sim.load_m5_m1_wdo_gex)

START_DATE = "2026-01-02"
END_DATE = os.environ.get("JUMBA_BT_END", "2026-11-11")   # último pregão fechado no BT (12/11/2026: estendido de 06/11)
SPLIT_DATE = "2026-05-06"

COST_WIN_PTS = 10.0   # R$ 2,00 / contrato WIN
COST_WDO_PTS = 0.5    # R$ 5,00 / contrato WDO

ALL_11_IDS = [
    "EST_01", "EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "EST_16",
    "WDO_01", "WDO_02", "WDO_05", "WDO_07", "WDO_09", "WDO_10",
]

# Melhor filtro de Divergência Preço vs. Absorção/Agressão Não-Varejo (Profit 4-Players) por estratégia
BEST_FLOW_FILTER_MAP = {
    "EST_01": "14_NR_BREAKOUT_SQUEEZE",
    "EST_04": "15_NR_IGNITION_DIV",
    "EST_07": "16_NR_DIV_ABS_OR_AGGR",
    "EST_13": "11_PROFIT_WALL_SHIELD",
    "EST_14": "12_NR_WALL_TRAP_DIV",
    "EST_15": "14_NR_BREAKOUT_SQUEEZE",
    "EST_16": "16_NR_DIV_ABS_OR_AGGR",
    "WDO_01": "13_NR_PRICE_ABS_DIV",
    "WDO_02": "17_NR_SQUEEZE_CLEAN",
    "WDO_05": "13_NR_PRICE_ABS_DIV",
    "WDO_07": "12_NR_WALL_TRAP_DIV",
    "WDO_09": "18_NR_ASG_PLUS_DIV",
    "WDO_10": "6_COMBO_SMART",
    "WIN_E2": "13_NR_PRICE_ABS_DIV",
}

STRAT_METADATA = {
    "EST_01": {
        "id": "EST_01", "asset": "WIN", "name": "EST-01 · WIN Rejeição/Pinbar Wall",
        "short": "EST-01 Rejeição", "window": "15:00–16:40", "lotes": "1c",
        "tp_rule": "TP_MAIN_WALL (Alvo Wall Principal)",
        "sl_be_rule": "SL 240p + BE_WALL_SHIELD (Buf 25p)",
        "nwe_rule": "Banda NWE50 >= 475.8 pts",
        "flow_rule": "14_NR_BREAKOUT_SQUEEZE (Sweep Não-Varejo + Squeeze s/ Absorção Contra)",
    },
    "EST_04": {
        "id": "EST_04", "asset": "WIN", "name": "EST-04 · WIN Pullback Tendência WDO",
        "short": "EST-04 Pullback", "window": "14:00–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall)",
        "sl_be_rule": "SL 220p + BE_WALL_2STAGE (Escudo 15p -> +45p)",
        "nwe_rule": "NWE50 Slope + Micro-Canal WDO Alinhado",
        "flow_rule": "15_NR_IGNITION_DIV (Divergência Preço 15m vs Distribuição Não-Varejo)",
    },
    "EST_07": {
        "id": "EST_07", "asset": "WIN", "name": "EST-07 · WIN Ignição/Rompimento Wall",
        "short": "EST-07 Rompimento", "window": "14:00–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall)",
        "sl_be_rule": "SL 260p + BE_WALL_SHIELD (Buf 15p)",
        "nwe_rule": "2_NWE_DUAL_SLOPE (NWE50 + NWE30 Alinhadas)",
        "flow_rule": "16_NR_DIV_ABS_OR_AGGR (Divergência Preço na Wall vs Absorção/Agressão Não-Varejo)",
    },
    "EST_13": {
        "id": "EST_13", "asset": "WIN", "name": "EST-13 · WIN SmartGrid Longa Descontada Wall (35% B1 · TP 360p)",
        "short": "EST-13 Grid Longa", "window": "15:00–16:30", "lotes": "1+2c",
        "tp_rule": "TP_MIDWALL Estendido 360p (170p na 2ª perna)",
        "sl_be_rule": "Limite 35% B1 (perto da Wall) + NextWall 1+2L + BE_WALL_SHIELD (145p)",
        "nwe_rule": "Banda NWE50 >= 475.8 pts + Z-Score WDO",
        "flow_rule": "11_PROFIT_WALL_SHIELD (Janela S + Escudo Inst/Varejo na Wall)",
    },
    "EST_14": {
        "id": "EST_14", "asset": "WIN", "name": "EST-14 · WIN SmartGrid Média Defesa Pavio (50% B1 · TP 280p)",
        "short": "EST-14 Grid Média", "window": "15:00–16:30", "lotes": "1+2c",
        "tp_rule": "TP_MIDWALL Intermediário 280p (170p na 2ª perna)",
        "sl_be_rule": "Limite 50% B1 + NextWall 1+2L + BE_WALL_SHIELD (130p)",
        "nwe_rule": "Defesa de Pavio na Wall + Gamma Flip",
        "flow_rule": "12_NR_WALL_TRAP_DIV (Divergência Armadilha Varejo vs Absorção/Agressão Não-Varejo)",
    },
    "EST_15": {
        "id": "EST_15", "asset": "WIN", "name": "EST-15 · WIN SmartGrid Curta Z30 Reversal (55% B1 · TP 210p)",
        "short": "EST-15 Grid Curta", "window": "15:00–16:30", "lotes": "1+2c",
        "tp_rule": "TP_MIDWALL Encurtado 210p (170p na 2ª perna)",
        "sl_be_rule": "Limite 55% B1 + NextWall 1+2L + BE_WALL_SHIELD (110p)",
        "nwe_rule": "4_NWE_ROOM_70 (Espaço >= 70p até Centro NWE50)",
        "flow_rule": "14_NR_BREAKOUT_SQUEEZE (Sweep Não-Varejo + Squeeze s/ Absorção Contra)",
    },
    "EST_16": {
        "id": "EST_16", "asset": "WIN", "name": "EST-16 · WIN Divergência Preço vs Não-Varejo na Wall",
        "short": "EST-16 Divergência NR", "window": "10:00–16:30", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall)",
        "sl_be_rule": "SL 240p + BE_WALL_SHIELD (Buf 20p)",
        "nwe_rule": "Divergência de Preço na Wall + NWE50/30",
        "flow_rule": "16_NR_DIV_ABS_OR_AGGR (Divergência Preço vs Absorção/Agressão Não-Varejo)",
    },
    "WDO_01": {
        "id": "WDO_01", "asset": "WDO", "name": "WDO-01 · WDO Scalper Curto Wall NY (TP 6.0p–8.0p)",
        "short": "WDO-01 Scalper Curto", "window": "09:05–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL Curto (6.0p a 8.0p)",
        "sl_be_rule": "SL 9.5p + BE_WALL_SHIELD (Buf 1.0p)",
        "nwe_rule": "Defesa de Wall NY + Banda NWE50",
        "flow_rule": "13_NR_PRICE_ABS_DIV (Divergência Preço vs Absorção/Agressão Não-Varejo)",
    },
    "WDO_02": {
        "id": "WDO_02", "asset": "WDO", "name": "WDO-02 · WDO Scalper Híbrido Core",
        "short": "WDO-02 Scalper", "window": "15:00–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall, mín 6.5p)",
        "sl_be_rule": "SL 8.5p + BE_WALL_SHIELD (Buf 1.0p)",
        "nwe_rule": "Banda NWE50 >= 7.15 pts + Micro-Tendência",
        "flow_rule": "17_NR_SQUEEZE_CLEAN (Divergência Limpa Preço 15m vs Fluxo Não-Varejo)",
    },
    "WDO_05": {
        "id": "WDO_05", "asset": "WDO", "name": "WDO-05 · WDO Cluster NWE30+50 Limit Wall (TP 7.0p–9.5p)",
        "short": "WDO-05 Cluster Limit", "window": "09:05–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL Intermediário (7.0p a 9.5p)",
        "sl_be_rule": "Limite B1±0.5p + SL 10.0p + BE_WALL_SHIELD (Buf 1.0p)",
        "nwe_rule": "Cluster NWE30 + NWE50 na Wall (OOS PF 1.31)",
        "flow_rule": "13_NR_PRICE_ABS_DIV (Divergência Preço vs Absorção/Agressão Não-Varejo)",
    },
    "WDO_07": {
        "id": "WDO_07", "asset": "WDO", "name": "WDO-07 · WDO Absorção Longa Mkt Wall NY (TP 11.0p)",
        "short": "WDO-07 Absorção Longa", "window": "09:05–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL Estendido (até 11.0p)",
        "sl_be_rule": "SL 11.5p + BE_WALL_SHIELD (Buf 1.0p)",
        "nwe_rule": "Absorção de Pavio na Wall + WIN Ret3",
        "flow_rule": "12_NR_WALL_TRAP_DIV (Divergência Armadilha Varejo vs Absorção/Agressão Não-Varejo)",
    },
    "WDO_09": {
        "id": "WDO_09", "asset": "WDO", "name": "WDO-09 · WDO Defesa Pavio Wall + Divergência Não-Varejo",
        "short": "WDO-09 Defesa NR", "window": "15:00–16:40", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall, mín 6.5p)",
        "sl_be_rule": "SL_WALL_SHIELD (Buf 2.0p) + BE_WALL_2STAGE (Buf 1.5p)",
        "nwe_rule": "Defesa Pavio na Wall + Banda NWE50 >= 7.15 pts",
        "flow_rule": "18_NR_ASG_PLUS_DIV (Janela S + Divergência Preço vs Não-Varejo)",
    },
    "WDO_10": {
        "id": "WDO_10", "asset": "WDO", "name": "WDO-10 · WDO Lunch Reversão NWE (12h–14h30)",
        "short": "WDO-10 Lunch", "window": "12:00–14:30", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall, mín 6.0p)",
        "sl_be_rule": "SL 9.5p + BE_WALL_SHIELD (Buf 1.5p)",
        "nwe_rule": "Banda NWE50 >= 7.15 pts + Z30 Extremo Almoço",
        "flow_rule": "6_COMBO_SMART (Janela S + Absorção Não-Varejo · Ret/DD 15.72x)",
    },
    "WIN_E2": {
        "id": "WIN_E2", "asset": "WIN", "name": "WIN-E2 · ⚪ WALL GASTA 3º+ Toque + Divergência Não-Varejo",
        "short": "WIN-E2 Wall Gasta NR", "window": "09:05–16:30", "lotes": "1c",
        "tp_rule": "TP_MIDWALL (Alvo MidWall / Wall, teto 260p)",
        "sl_be_rule": "SL 230p + BE_WALL_SHIELD (Buf 20p após +130p)",
        "nwe_rule": "NWE50 + NWE30 Alinhadas + Divergência Não-Varejo na Wall (3º+ Toque)",
        "flow_rule": "13_NR_PRICE_ABS_DIV + NR_WALL_DIV (Sem Absorção Passiva Contra + Sweep/Squeeze NR)",
    },
}

WALLS_FLOW_6_IDS = ["EST_14", "EST_04", "EST_07", "WIN_E2", "WDO_07", "WDO_01"]
TOP_8_5174_IDS = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"]

# Métricas antes do filtro NWE (Baseline Anterior) para a Tabela Comparativa de 3 Estágios
PRE_NWE_BASELINE = {
    "EST_01": {"ops": 527, "wr_pct": 33.4, "pf": 1.11, "tot_brl_1c": 1221.0, "max_dd_brl_1c": 417.0, "ret_dd": 2.93},
    "EST_04": {"ops": 177, "wr_pct": 47.5, "pf": 1.67, "tot_brl_1c": 2055.0, "max_dd_brl_1c": 264.0, "ret_dd": 7.78},
    "EST_07": {"ops": 359, "wr_pct": 38.7, "pf": 1.24, "tot_brl_1c": 1848.0, "max_dd_brl_1c": 403.0, "ret_dd": 4.59},
    "EST_13": {"ops": 259, "wr_pct": 63.3, "pf": 1.37, "tot_brl_1c": 2639.0, "max_dd_brl_1c": 706.0, "ret_dd": 3.74},
    "EST_14": {"ops": 284, "wr_pct": 65.1, "pf": 1.54, "tot_brl_1c": 4284.0, "max_dd_brl_1c": 460.0, "ret_dd": 9.31},
    "EST_15": {"ops": 307, "wr_pct": 63.8, "pf": 1.21, "tot_brl_1c": 2033.0, "max_dd_brl_1c": 885.0, "ret_dd": 2.30},
    "EST_16": {"ops": 135, "wr_pct": 69.6, "pf": 1.15, "tot_brl_1c": 616.0, "max_dd_brl_1c": 653.0, "ret_dd": 0.94},
    "WDO_01": {"ops": 705, "wr_pct": 51.3, "pf": 1.17, "tot_brl_1c": 3940.0, "max_dd_brl_1c": 1325.0, "ret_dd": 2.97},
    "WDO_02": {"ops": 338, "wr_pct": 51.5, "pf": 1.29, "tot_brl_1c": 3240.0, "max_dd_brl_1c": 450.0, "ret_dd": 7.20},
    "WDO_05": {"ops": 745, "wr_pct": 61.9, "pf": 1.24, "tot_brl_1c": 5995.0, "max_dd_brl_1c": 880.0, "ret_dd": 6.81},
    "WDO_07": {"ops": 247, "wr_pct": 55.1, "pf": 1.48, "tot_brl_1c": 3125.0, "max_dd_brl_1c": 390.0, "ret_dd": 8.01},
    "WDO_09": {"ops": 182, "wr_pct": 45.6, "pf": 1.35, "tot_brl_1c": 1970.0, "max_dd_brl_1c": 725.0, "ret_dd": 2.72},
    "WDO_10": {"ops": 173, "wr_pct": 55.5, "pf": 1.54, "tot_brl_1c": 2745.0, "max_dd_brl_1c": 570.0, "ret_dd": 4.82},
}


def format_win_o16_trades(trades_raw, df_win, strat_id: str):
    ts_arr = df_win["t"].values
    out = []
    for t in trades_raw:
        i_sig = int(t["i_sig"])
        j_ex = int(t["j_exit"])
        t_in = pd.Timestamp(ts_arr[i_sig]).strftime("%H:%M")
        t_out = pd.Timestamp(ts_arr[j_ex]).strftime("%H:%M")
        d_str = str(t["date"])
        side_str = "COMPRA" if int(t["side"]) == 1 else "VENDA"
        lots = int(t.get("contracts", 1))
        pts_net = float(t["pnl_pts"])
        pts_raw = pts_net + COST_WIN_PTS * lots
        brl_net = round(pts_net * 0.20, 2)
        brl_raw = round(pts_raw * 0.20, 2)
        ep = float(t.get("avg_px", 0.0))
        xp = float(t.get("exit_px", 0.0))
        tp = float(t.get("tp_px", 0.0))
        sl = float(t.get("sl_last", 0.0))
        sl0 = float(t.get("sl0", sl))
        if abs(xp - tp) <= 10.0 and pts_net > 0:
            lbl = f"✅ ALVO WALL ({pts_net:+.0f} pts)"
        elif pts_net > 0:
            lbl = f"✅ ESCUDO WALL / TEMPO ({pts_net:+.0f} pts)"
        elif abs(xp - sl0) > 15.0 and abs(xp - sl) <= 15.0:
            lbl = f"🛡️ ESCUDO WALL ({pts_net:+.0f} pts)"
        else:
            lbl = f"❌ STOP / TEMPO ({pts_net:+.0f} pts)"
        out.append({
            "date": d_str,
            "month": d_str[:7],
            "time": t_in,
            "exit_time": t_out,
            "asset": "WIN",
            "strategy_id": strat_id,
            "direction": side_str,
            "type": f"{strat_id} · {side_str}",
            "entry_price": round(ep, 1),
            "exit_price": round(xp, 1),
            "stop_price": round(sl, 1),
            "tp_price": round(tp, 1),
            "contracts": lots,
            "pts": round(pts_net, 1),
            "pts_nocost": round(pts_raw, 1),
            "brl_1c": brl_net,
            "brl_1c_nocost": brl_raw,
            "label": lbl,
            "status": "FECHADA",
        })
    return out


def format_sg_trades(df_sg):
    out = []
    if df_sg is None or df_sg.empty:
        return out
    for _, r in df_sg.iterrows():
        k = int(r["k"])
        strat_id = f"EST_{k:02d}"
        t_in_ts = pd.Timestamp(r["t_in"])
        t_out_ts = pd.Timestamp(r["t_out"])
        d_str = t_in_ts.strftime("%Y-%m-%d")
        t_in = t_in_ts.strftime("%H:%M")
        t_out = t_out_ts.strftime("%H:%M")
        side_str = "COMPRA" if int(r["side"]) == 1 else "VENDA"
        lots = int(r["lots"])
        brl_net = round(float(r["brl"]), 2)
        brl_raw = round(float(r.get("brl_nocost", brl_net + lots * 2.0)), 2)
        pts_net = round(brl_net / 0.20, 1)
        pts_raw = round(brl_raw / 0.20, 1)
        why = str(r.get("why", ""))
        leg_tag = " 1+2L" if pd.notna(r.get("leg2")) else ""
        if why == "TP" or pts_net > 0:
            lbl = f"✅ {'ALVO WALL' if why == 'TP' else 'ESCUDO / TEMPO'}{leg_tag} ({pts_net:+.0f} pts)"
        else:
            lbl = f"❌ {why}{leg_tag} ({pts_net:+.0f} pts)"
        out.append({
            "date": d_str,
            "month": d_str[:7],
            "time": t_in,
            "exit_time": t_out,
            "asset": "WIN",
            "strategy_id": strat_id,
            "direction": side_str,
            "type": f"{strat_id} · {side_str}{leg_tag}",
            "entry_price": round(float(r.get("avg_px", r["px_in"])), 1),
            "exit_price": round(float(r["px_out"]), 1),
            "stop_price": round(float(r.get("sl", 0.0)), 1),
            "tp_price": round(float(r.get("tp", 0.0)), 1),
            "contracts": lots,
            "pts": pts_net,
            "pts_nocost": pts_raw,
            "brl_1c": brl_net,
            "brl_1c_nocost": brl_raw,
            "label": lbl,
            "status": "FECHADA",
        })
    return out


def format_wdo_trades(trades_raw, strat_id: str):
    out = []
    for t in trades_raw:
        d_str = str(t["date"])
        t_in = pd.Timestamp(t["entry_time"]).strftime("%H:%M")
        t_out = pd.Timestamp(t["exit_time"]).strftime("%H:%M")
        side_str = "COMPRA" if int(t["side"]) == 1 else "VENDA"
        lots = int(t.get("contracts", 1))
        pts_net = round(float(t["pnl_pts"]), 2)
        pts_raw = round(float(t["raw_pts"]), 2)
        brl_net = round(float(t["pnl_brl"]), 2)
        brl_raw = round(float(t["pnl_brl_nocost"]), 2)
        reason = str(t.get("reason", ""))
        if "TP" in reason or pts_net > 0:
            lbl = f"✅ {'ALVO WALL' if 'TP' in reason else 'ESCUDO / TEMPO'} ({pts_net:+.1f} pts)"
        else:
            lbl = f"❌ {reason} ({pts_net:+.1f} pts)"
        out.append({
            "date": d_str,
            "month": d_str[:7],
            "time": t_in,
            "exit_time": t_out,
            "asset": "WDO",
            "strategy_id": strat_id,
            "direction": side_str,
            "type": f"{strat_id} · {side_str}",
            "entry_price": round(float(t["avg_px"]), 1),
            "exit_price": round(float(t["exit_px"]), 1),
            "stop_price": round(float(t.get("sl_last", 0.0)), 1),
            "tp_price": round(float(t.get("tp_px", 0.0)), 1),
            "contracts": lots,
            "pts": pts_net,
            "pts_nocost": pts_raw,
            "brl_1c": brl_net,
            "brl_1c_nocost": brl_raw,
            "label": lbl,
            "status": "FECHADA",
        })
    return out


def simulate_win_e2_wall_gasta(df_win, gex_win, n50w, n30w, flow_tables, use_flow: bool = True, sig_filter=None):
    """
    Simula WIN_E2 (⚪ WALL GASTA · Rompimento 3º+ Toque da Wall c/ Divergência & Confirmação Não-Varejo):
      - No modo `use_flow=True`: exige `NR_WALL_DIV` na barra do 3º+ toque da Wall (sem Absorção Passiva
        Institucional contrária ao rompimento c/ Varejo sozinho, e com Sweep Não-Varejo `ia5 > 0`/`i15 > 0`
        ou Squeeze de Varejo `r5 <= 0` / `lot_imb >= 1.0`), máx 2 trades/dia + `13_NR_PRICE_ABS_DIV`.
      - Entrada Limite no ponto médio da barra rompida (mid_b1), válida por 2 barras
      - Stop inicial 230p + BE_WALL_SHIELD (20p atrás da Wall rompida após +130p)
      - Alvo TP_MIDWALL (teto 260p)
    """
    sessions_dir = os.path.join(ROOT_DIR, "data", "processed", "gex_historical_sessions_v1")
    wall_tab = {}
    for fp in sorted(glob.glob(os.path.join(sessions_dir, "*.json"))):
        date = os.path.basename(fp).replace(".json", "")
        if date not in gex_win:
            continue
        w_arr = gex_win[date]["walls"]
        mw_arr = gex_win[date]["mid_walls"]
        lvls = np.sort(np.concatenate([w_arr, mw_arr])) if len(mw_arr) > 0 else w_arr
        gex_win[date]["all_levels"] = lvls
        if len(lvls) == 0:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        series = data.get("WIN", {}).get("m5_cvd_series", [])
        if not series:
            continue
        w_state = {float(w): {"touches": 0} for w in lvls}
        for idx, b in enumerate(series):
            dt = datetime.fromtimestamp(int(b.get("time", 0)), tz=timezone.utc)
            t_min = dt.hour * 60 + dt.minute
            o = float(b.get("open", b.get("close", 0.0)))
            h = float(b.get("high", o))
            l = float(b.get("low", o))
            c = float(b.get("close", o))
            i5 = float(b.get("inst_delta_bar", 0.0))
            ia5 = float(b.get("inst_aggr_delta", i5))
            ip5 = float(b.get("inst_pass_delta", 0.0))
            r5 = float(b.get("ret_delta_bar", 0.0))
            lot_imb = float(b.get("lot_imb", 1.0))
            i15 = sum(float(series[k].get("inst_delta_bar", 0.0)) for k in range(max(0, idx - 2), idx + 1))
            rng = max(h - l, 5.0)
            body_r = abs(c - o) / rng
            exbr_b = exbr_s = False
            for wp, st in w_state.items():
                if l - 70.0 <= wp <= h + 70.0:
                    st["touches"] += 1
                    if st["touches"] >= 3:
                        if c > wp and c > o and (body_r >= 0.35 or i5 >= 0 or i15 >= 0):
                            if not use_flow or (
                                not (ip5 < -500.0 and r5 > 400.0)
                                and (ia5 > 0 or i15 > 0 or r5 <= 0 or lot_imb >= 1.0)
                            ):
                                exbr_b = True
                        if c < wp and c < o and (body_r >= 0.35 or i5 <= 0 or i15 <= 0):
                            if not use_flow or (
                                not (ip5 > 500.0 and r5 < -400.0)
                                and (ia5 < 0 or i15 < 0 or r5 >= 0 or lot_imb <= 1.0)
                            ):
                                exbr_s = True
            wall_tab[(date, t_min)] = (exbr_b, exbr_s)

    flow_fn = make_sig_filter(flow_tables, "WIN", BEST_FLOW_FILTER_MAP.get("WIN_E2", "13_NR_PRICE_ABS_DIV")) if use_flow else None
    if sig_filter is not None:  # pesquisa (research/div_gate): filtro externo substitui o de fluxo na entrada
        flow_fn = sig_filter
    dates = df_win["session_date"].values
    t_arr = df_win["t"].values
    tmins = df_win["t_min"].values
    opens = df_win["open"].values
    highs = df_win["high"].values
    lows = df_win["low"].values
    closes = df_win["close"].values
    c50, u50, l50, _, s50 = n50w
    c30, u30, l30, _, s30 = n30w
    rnd = o16.round5

    trades = []
    n = len(df_win)
    i = 3
    day_cnt = {}

    while i < n - 1:
        b1 = i - 1
        d_str = str(dates[i])
        if d_str < START_DATE or d_str > END_DATE or d_str not in gex_win or str(dates[b1]) != d_str:
            i += 1
            continue
        if day_cnt.get(d_str, 0) >= 2:
            i += 1
            continue
        tm = int(tmins[b1])
        if not (545 <= tm <= 990):
            i += 1
            continue
        ex_pair = wall_tab.get((d_str, tm))
        if ex_pair is None:
            i += 1
            continue
        g = gex_win[d_str]
        lvls = g["all_levels"]
        walls = g["walls"]
        if len(lvls) == 0:
            i += 1
            continue

        o1, h1, l1, c1 = opens[b1], highs[b1], lows[b1], closes[b1]
        bw50 = max(u50[b1] - l50[b1], 10.0)
        pos50 = (c1 - l50[b1]) / bw50
        dc, lc = wsim.find_nearest_level(lvls, c1)

        sig = 0
        def_w = 0.0
        if ex_pair[0] and dc <= 85.0 and c1 > lc and c1 > o1 and s50[b1] > 0.0 and s30[b1] > 0.0 and 0.35 <= pos50 <= 0.80:
            sig, def_w = 1, lc
        elif ex_pair[1] and dc <= 85.0 and c1 < lc and c1 < o1 and s50[b1] < 0.0 and s30[b1] < 0.0 and 0.20 <= pos50 <= 0.65:
            sig, def_w = -1, lc

        if sig == 0 or (flow_fn is not None and not flow_fn(d_str, tm, sig)):
            i += 1
            continue

        lim_px = rnd(0.5 * (h1 + l1))
        if (sig == 1 and opens[i] < lim_px) or (sig == -1 and opens[i] > lim_px):
            i += 1
            continue

        filled, fbar, ep = False, i, lim_px
        for v in range(2):
            eb = i + v
            if eb >= n or str(dates[eb]) != d_str or int(tmins[eb]) >= 1005:
                break
            if (sig == 1 and lows[eb] <= lim_px) or (sig == -1 and highs[eb] >= lim_px):
                filled, fbar, ep = True, eb, lim_px
                break

        if not filled:
            i += 1
            continue

        tp_mid, _, _, _ = o16.find_structural_targets(ep, sig, walls, lvls, 20.0)
        tp_px = min(tp_mid, rnd(ep + 260.0)) if sig == 1 else max(tp_mid, rnd(ep - 260.0))
        sl_init_px = rnd(ep - sig * 230.0)
        sl_px = sl_init_px
        be_on = False
        mfe = 0.0
        k = fbar
        bars_held = 0
        xp = closes[fbar]

        while k < n:
            if str(dates[k]) != d_str or int(tmins[k]) >= 1030:
                xp = opens[k] if str(dates[k]) == d_str else closes[k - 1]
                break
            if (sig == 1 and lows[k] <= sl_px) or (sig == -1 and highs[k] >= sl_px):
                xp = sl_px
                break
            if (sig == 1 and highs[k] >= tp_px) or (sig == -1 and lows[k] <= tp_px):
                xp = tp_px
                break
            bars_held += 1
            fav = (highs[k] - ep) if sig == 1 else (ep - lows[k])
            if fav > mfe:
                mfe = fav
            if k + 1 < n and str(dates[k + 1]) == d_str:
                no = opens[k + 1]
                if not be_on and mfe >= 130.0:
                    w_cand = rnd(def_w - sig * 20.0)
                    max_lock = rnd(ep + sig * 15.0)
                    cand = min(w_cand, max_lock) if sig == 1 else max(w_cand, max_lock)
                    min_improve = rnd(ep - sig * 85.0)
                    cand = max(cand, min_improve) if sig == 1 else min(cand, min_improve)
                    if (sig == 1 and cand > sl_px and no > cand) or (sig == -1 and cand < sl_px and no < cand):
                        sl_px = cand
                        be_on = True
                if bars_held >= 18:
                    xp = no
                    k += 1
                    break
            k += 1

        pts_raw = (xp - ep) * sig
        pts_net = pts_raw - COST_WIN_PTS
        side_str = "COMPRA" if sig == 1 else "VENDA"
        if abs(xp - tp_px) <= 10.0 and pts_net > 0:
            lbl = f"✅ ALVO WALL ({pts_net:+.0f} pts)"
        elif pts_net > 0:
            lbl = f"✅ ESCUDO WALL / TEMPO ({pts_net:+.0f} pts)"
        elif be_on and abs(xp - sl_px) <= 15.0:
            lbl = f"🛡️ ESCUDO WALL ({pts_net:+.0f} pts)"
        else:
            lbl = f"❌ STOP / TEMPO ({pts_net:+.0f} pts)"

        trades.append({
            "date": d_str,
            "month": d_str[:7],
            "time": pd.Timestamp(t_arr[fbar]).strftime("%H:%M"),
            "exit_time": pd.Timestamp(t_arr[min(k, n - 1)]).strftime("%H:%M"),
            "asset": "WIN",
            "strategy_id": "WIN_E2",
            "direction": side_str,
            "type": f"WIN_E2 · {side_str}",
            "entry_price": round(float(ep), 1),
            "exit_price": round(float(xp), 1),
            "stop_price": round(float(sl_px), 1),
            "tp_price": round(float(tp_px), 1),
            "contracts": 1,
            "pts": round(float(pts_net), 1),
            "pts_nocost": round(float(pts_raw), 1),
            "brl_1c": round(float(pts_net * 0.20), 2),
            "brl_1c_nocost": round(float(pts_raw * 0.20), 2),
            "label": lbl,
            "status": "FECHADA",
        })
        day_cnt[d_str] = day_cnt.get(d_str, 0) + 1
        i = max(i + 1, k + 1)

    return trades


def run_all_strategies_for_mode(df_win, gex_win, n50w, n30w, rsi7w, df_wdo, gex_wdo, n50d, n30d, rsi7d, flow_tables, use_flow: bool):
    """Executa as 11 estratégias em modo Base MT5 (`use_flow=False`) ou C/ Filtro de Fluxo (`use_flow=True`)."""
    A = (df_win, gex_win, n50w[0], n50w[1], n50w[2], n50w[4], n30w[0], n30w[1], n30w[2], n30w[4], rsi7w)

    trades_by_strat = {}

    # 1) EST_01, EST_07 & EST_16 (evoluído p/ Divergência Preço vs Não-Varejo na Wall via Slot 3) via o16
    for est_id, sid, ent, be_m, buf, tp_m in [
        (1, "EST_01", "CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
        (7, "EST_07", "CURRENT", "BE_WALL_SHIELD", 15.0, "TP_MIDWALL"),
        (3, "EST_16", "CURRENT", "BE_WALL_SHIELD", 20.0, "TP_MIDWALL"),
    ]:
        f_key = BEST_FLOW_FILTER_MAP[sid] if use_flow else "0_BASE_MT5"
        sf = make_sig_filter(flow_tables, "WIN", f_key)
        tr_raw, _ = o16.simulate_single_est_slot(
            est_id, *A,
            entry_override=ent, be_mode=be_m, wall_shield_buf=buf,
            tp_mode=tp_m, cost_pts=COST_WIN_PTS, sig_filter=sf, start_date=START_DATE,
        )
        tr_raw = [t for t in tr_raw if START_DATE <= str(t["date"]) <= END_DATE]
        trades_by_strat[sid] = format_win_o16_trades(tr_raw, df_win, sid)

    # 2) EST_04 via simulate_aligned_win_wdo_slot
    f_key_04 = BEST_FLOW_FILTER_MAP["EST_04"] if use_flow else "0_BASE_MT5"
    sf_04 = make_sig_filter(flow_tables, "WIN", f_key_04)
    tr_04, _ = simulate_aligned_win_wdo_slot(
        4, *A,
        be_mode="BE_WALL_2STAGE_177K", wall_shield_buf=15.0, tp_mode="TP_MIDWALL",
        entry_override="ALIGNED", cost_pts=COST_WIN_PTS, sig_filter=sf_04, start_date=START_DATE,
    )
    tr_04 = [t for t in tr_04 if START_DATE <= str(t["date"]) <= END_DATE]
    trades_by_strat["EST_04"] = format_win_o16_trades(tr_04, df_win, "EST_04")

    # 3) EST_13..15 via sg_sim
    for k in (13, 14, 15):
        sid = f"EST_{k:02d}"
        f_key = BEST_FLOW_FILTER_MAP[sid] if use_flow else "0_BASE_MT5"
        sf = make_sig_filter(flow_tables, "WIN", f_key)
        df_sg = sg_sim.run(slots=(k,), start=START_DATE, cost_pts=COST_WIN_PTS, sig_filter=sf)
        trades_by_strat[sid] = [t for t in format_sg_trades(df_sg) if START_DATE <= t["date"] <= END_DATE]

    # 4) WDO_01, WDO_02, WDO_05, WDO_07, WDO_09 (evoluído p/ Defesa Pavio + Divergência NR via Slot 3), WDO_10 via wdo_mt5_sim
    for slot_id, sid in [
        (1, "WDO_01"),
        (2, "WDO_02"),
        (5, "WDO_05"),
        (7, "WDO_07"),
        (3, "WDO_09"),
        (10, "WDO_10"),
    ]:
        f_key = BEST_FLOW_FILTER_MAP[sid] if use_flow else "0_BASE_MT5"
        sf = make_sig_filter(flow_tables, "WDO", f_key)
        tr_wdo = wsim.simulate_wdo_core_slot(
            slot_id, df_wdo, gex_wdo,
            n50d[0], n50d[1], n50d[2], n50d[4],
            n30d[0], n30d[1], n30d[2], n30d[4], rsi7d,
            start_date=START_DATE, end_date=END_DATE,
            cost_pts=COST_WDO_PTS, sig_filter=sf,
        )
        trades_by_strat[sid] = format_wdo_trades(tr_wdo, sid)

    # 5) WIN_E2 (⚪ WALL GASTA · Rompimento 3º+ Toque na Wall)
    trades_by_strat["WIN_E2"] = simulate_win_e2_wall_gasta(df_win, gex_win, n50w, n30w, flow_tables, use_flow=use_flow)

    return trades_by_strat


def compute_summary_from_trades(trades_list, all_dates, mult_default=1.0):
    ops = len(trades_list)
    if ops == 0:
        return {
            "ops": 0, "wins": 0, "wr_pct": 0.0, "pf": 0.0,
            "gross_win_1c": 0.0, "gross_loss_1c": 0.0,
            "tot_pts": 0.0, "tot_brl_1c": 0.0, "tot_brl_nocost": 0.0, "pf_nocost": 0.0,
            "max_dd_brl_1c": 0.0, "ret_dd": 0.0,
            "pos_months": 0, "total_months": 0, "by_month_1c": {},
            "is_net": 0.0, "is_pf": 0.0, "is_dd": 0.0, "is_ret_dd": 0.0, "is_ops": 0,
            "oos_net": 0.0, "oos_pf": 0.0, "oos_dd": 0.0, "oos_ret_dd": 0.0, "oos_ops": 0,
        }
    wins = sum(1 for t in trades_list if t["brl_1c"] > 0)
    gw = sum(t["brl_1c"] for t in trades_list if t["brl_1c"] > 0)
    gl = abs(sum(t["brl_1c"] for t in trades_list if t["brl_1c"] < 0))
    pf = round(gw / gl, 2) if gl > 0 else 99.9

    gw_nc = sum(t.get("brl_1c_nocost", t["brl_1c"]) for t in trades_list if t.get("brl_1c_nocost", t["brl_1c"]) > 0)
    gl_nc = abs(sum(t.get("brl_1c_nocost", t["brl_1c"]) for t in trades_list if t.get("brl_1c_nocost", t["brl_1c"]) < 0))
    pf_nc = round(gw_nc / gl_nc, 2) if gl_nc > 0 else 99.9
    tot_nc = round(sum(t.get("brl_1c_nocost", t["brl_1c"]) for t in trades_list), 2)

    tot_pts = round(sum(t["pts"] for t in trades_list), 1)
    tot_brl = round(sum(t["brl_1c"] for t in trades_list), 2)

    # Max DD trade-by-trade (ordenado por data + hora) e também diário
    tr_sorted = sorted(trades_list, key=lambda x: (x["date"], x["time"], x["exit_time"]))
    cum_tr = np.cumsum([t["brl_1c"] for t in tr_sorted])
    pk_tr = np.maximum.accumulate(np.insert(cum_tr, 0, 0.0))[1:]
    max_dd_tr = round(float(np.max(pk_tr - cum_tr)), 2) if len(cum_tr) else 0.0

    # Daily equity DD (usado quando combinamos múltiplas estratégias no portfólio)
    by_day = {d: 0.0 for d in all_dates}
    for t in trades_list:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + t["brl_1c"]
    daily_arr = np.array([by_day[d] for d in all_dates], dtype=float)
    cum_day = np.cumsum(daily_arr)
    pk_day = np.maximum.accumulate(np.insert(cum_day, 0, 0.0))[1:]
    max_dd_day = round(float(np.max(pk_day - cum_day)), 2) if len(cum_day) else 0.0

    # Daily equity DD (alinhado 100% ao relatório `backtest_11_flow_filters.py` e ao gráfico SVG do Dashboard)
    max_dd = max_dd_day
    ret_dd = round(tot_brl / max_dd, 2) if max_dd > 0 else 99.9

    by_month = {}
    for d in all_dates:
        m = d[:7]
        by_month.setdefault(m, 0.0)
    for t in trades_list:
        m = t["month"]
        by_month[m] = round(by_month.get(m, 0.0) + t["brl_1c"], 2)
    pos_m = sum(1 for v in by_month.values() if v > 0)

    # IS vs OOS
    is_tr = [t for t in tr_sorted if t["date"] <= SPLIT_DATE]
    oos_tr = [t for t in tr_sorted if t["date"] > SPLIT_DATE]

    def sub_stats(sub):
        if not sub:
            return 0.0, 0.0, 0.0, 0.0, 0
        s_net = round(sum(x["brl_1c"] for x in sub), 2)
        s_gw = sum(x["brl_1c"] for x in sub if x["brl_1c"] > 0)
        s_gl = abs(sum(x["brl_1c"] for x in sub if x["brl_1c"] < 0))
        s_pf = round(s_gw / s_gl, 2) if s_gl > 0 else 99.9
        c = np.cumsum([x["brl_1c"] for x in sub])
        p = np.maximum.accumulate(np.insert(c, 0, 0.0))[1:]
        s_dd = round(float(np.max(p - c)), 2)
        s_rdd = round(s_net / s_dd, 2) if s_dd > 0 else 99.9
        return s_net, s_pf, s_dd, s_rdd, len(sub)

    is_net, is_pf, is_dd, is_rdd, is_ops = sub_stats(is_tr)
    oos_net, oos_pf, oos_dd, oos_rdd, oos_ops = sub_stats(oos_tr)

    return {
        "ops": ops,
        "wins": wins,
        "wr_pct": round(wins / ops * 100.0, 1),
        "pf": pf,
        "pf_nocost": pf_nc,
        "gross_win_1c": round(gw, 2),
        "gross_loss_1c": round(gl, 2),
        "tot_pts": tot_pts,
        "tot_brl_1c": tot_brl,
        "tot_brl_nocost": tot_nc,
        "max_dd_brl_1c": max_dd,
        "max_dd_daily_brl": max_dd_day,
        "ret_dd": ret_dd,
        "ret_dd_daily": round(tot_brl / max_dd_day, 2) if max_dd_day > 0 else 99.9,
        "pos_months": pos_m,
        "total_months": len(by_month),
        "by_month_1c": by_month,
        "is_net": is_net, "is_pf": is_pf, "is_dd": is_dd, "is_ret_dd": is_rdd, "is_ops": is_ops,
        "oos_net": oos_net, "oos_pf": oos_pf, "oos_dd": oos_dd, "oos_ret_dd": oos_rdd, "oos_ops": oos_ops,
    }


def main():
    print("=" * 105)
    print("  GERANDO JSON V4.0: 11 ESTRATÉGIAS ATIVAS (7 WIN + 4 WDO) · WALLS TP/SL/BE + NWE + FLUXO")
    print("=" * 105)

    flow_tables, _ = load_flow_tables()

    df_win, gex_win = o16.load_win_and_wdo_aligned()
    closes_w = df_win["close"].values
    n50w = o16.compute_nwe_series(closes_w, lookback=50, bw=5.0, mult=2.0)
    n30w = o16.compute_nwe_series(closes_w, lookback=30, bw=3.0, mult=1.6)
    dp_w = pd.Series(closes_w).diff()
    rsi7w = (100.0 - (100.0 / (1.0 + (dp_w.clip(lower=0).rolling(7).mean() / (-dp_w.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values

    df_wdo, gex_wdo = wsim.load_wdo_mt5_raw()
    closes_d = df_wdo["close"].values
    n50d = wsim.compute_nwe_series(closes_d, lookback=50, bw=5.0, mult=2.0)
    n30d = wsim.compute_nwe_series(closes_d, lookback=30, bw=3.0, mult=1.6)
    rsi7d = wsim.compute_rsi7_series(closes_d)

    # Executa Base MT5 (Walls TP/SL/BE + NWE) e Modo C/ Filtro de Fluxo/Janela
    base_trades_map = run_all_strategies_for_mode(
        df_win, gex_win, n50w, n30w, rsi7w,
        df_wdo, gex_wdo, n50d, n30d, rsi7d,
        flow_tables, use_flow=False,
    )
    flow_trades_map = run_all_strategies_for_mode(
        df_win, gex_win, n50w, n30w, rsi7w,
        df_wdo, gex_wdo, n50d, n30d, rsi7d,
        flow_tables, use_flow=True,
    )

    # Todas as datas de pregão no intervalo
    win_dates = sorted(set(str(d) for d in df_win["session_date"].unique() if START_DATE <= str(d) <= END_DATE and str(d) in gex_win))
    wdo_dates = sorted(set(str(d) for d in df_wdo["session_date"].unique() if START_DATE <= str(d) <= END_DATE and str(d) in gex_wdo))
    all_dates = sorted(set(win_dates) | set(wdo_dates))

    summary_1c = {}
    all_11_comparison = []

    for sid in ALL_11_IDS:
        st_base = compute_summary_from_trades(base_trades_map[sid], all_dates)
        st_flow = compute_summary_from_trades(flow_trades_map[sid], all_dates)
        st_pre = PRE_NWE_BASELINE[sid]
        meta = STRAT_METADATA[sid]

        summary_1c[sid] = {
            **st_flow,
            "meta": meta,
            "base_mt5_variant": st_base,
            "flow_variant": st_flow,
            "pre_nwe_variant": st_pre,
        }
        summary_1c[f"{sid}_BASE"] = st_base
        summary_1c[f"{sid}_FLOW"] = st_flow

        all_11_comparison.append({
            "id": sid,
            "asset": meta["asset"],
            "name": meta["name"],
            "short": meta["short"],
            "window": meta["window"],
            "lotes": meta["lotes"],
            "tp_rule": meta["tp_rule"],
            "sl_be_rule": meta["sl_be_rule"],
            "nwe_rule": meta["nwe_rule"],
            "flow_rule": meta["flow_rule"],
            "best_flow_key": BEST_FLOW_FILTER_MAP[sid],
            "pre_nwe": st_pre,
            "base_mt5": {
                "ops": st_base["ops"],
                "wr_pct": st_base["wr_pct"],
                "pf": st_base["pf"],
                "pf_nocost": st_base["pf_nocost"],
                "tot_brl_1c": st_base["tot_brl_1c"],
                "tot_brl_nocost": st_base["tot_brl_nocost"],
                "max_dd_brl_1c": st_base["max_dd_brl_1c"],
                "ret_dd": st_base["ret_dd"],
                "is_net": st_base["is_net"],
                "oos_net": st_base["oos_net"],
                "oos_pf": st_base["oos_pf"],
            },
            "with_flow": {
                "ops": st_flow["ops"],
                "wr_pct": st_flow["wr_pct"],
                "pf": st_flow["pf"],
                "pf_nocost": st_flow["pf_nocost"],
                "tot_brl_1c": st_flow["tot_brl_1c"],
                "tot_brl_nocost": st_flow["tot_brl_nocost"],
                "max_dd_brl_1c": st_flow["max_dd_brl_1c"],
                "ret_dd": st_flow["ret_dd"],
                "is_net": st_flow["is_net"],
                "oos_net": st_flow["oos_net"],
                "oos_pf": st_flow["oos_pf"],
            },
        })

    # WIN_E2 (⚪ WALL GASTA · Rompimento 3º+ Toque na Wall) para o Localhost 2 (Fluxo nas Walls: 4 WIN + 2 WDO)
    st_e2_base = compute_summary_from_trades(base_trades_map["WIN_E2"], all_dates)
    st_e2_flow = compute_summary_from_trades(flow_trades_map["WIN_E2"], all_dates)
    summary_1c["WIN_E2"] = {
        **st_e2_flow,
        "meta": STRAT_METADATA["WIN_E2"],
        "base_mt5_variant": st_e2_base,
        "flow_variant": st_e2_flow,
    }
    summary_1c["WIN_E2_BASE"] = st_e2_base
    summary_1c["WIN_E2_FLOW"] = st_e2_flow

    # Aliases legados para retrocompatibilidade
    summary_1c["WDO_11"] = summary_1c["WDO_01"]
    summary_1c["WDO_S2"] = summary_1c["WDO_01"]

    # Resumos agregados:
    # - 5174 Proposta A ⭐ (Top 8 Elite M5 c/ Fluxo): EST_04, EST_07, EST_13, EST_14, EST_15, WDO_01, WDO_05, WDO_07
    # - 5176 Proposta B ⭐ (6 Walls V2 · 11/11 M+): EST_14, EST_04, EST_07, WIN_E2, WDO_07, WDO_01
    top8_ids = TOP_8_5174_IDS
    win_all_ids = [s for s in ALL_11_IDS if s.startswith("EST_")]
    wdo_all_ids = [s for s in ALL_11_IDS if s.startswith("WDO_")]

    summary_1c["WIN_TOTAL"] = compute_summary_from_trades([t for s in win_all_ids for t in flow_trades_map[s]], all_dates)
    summary_1c["WDO_TOTAL"] = compute_summary_from_trades([t for s in wdo_all_ids for t in flow_trades_map[s]], all_dates)
    summary_1c["PORTFOLIO_ALL_11"] = compute_summary_from_trades([t for s in ALL_11_IDS for t in flow_trades_map[s]], all_dates)
    summary_1c["PORTFOLIO_ALL_11_BASE"] = compute_summary_from_trades([t for s in ALL_11_IDS for t in base_trades_map[s]], all_dates)
    summary_1c["PORTFOLIO_TOP_8"] = compute_summary_from_trades([t for s in top8_ids for t in flow_trades_map[s]], all_dates)
    summary_1c["PORTFOLIO_TOP_8_BASE"] = compute_summary_from_trades([t for s in top8_ids for t in base_trades_map[s]], all_dates)
    summary_1c["PORTFOLIO_TOP_6"] = summary_1c["PORTFOLIO_TOP_8"]
    summary_1c["PORTFOLIO_TOP_6_BASE"] = summary_1c["PORTFOLIO_TOP_8_BASE"]
    summary_1c["PORTFOLIO_WALLS_6"] = compute_summary_from_trades([t for s in WALLS_FLOW_6_IDS for t in flow_trades_map[s]], all_dates)
    summary_1c["PORTFOLIO_1_1"] = summary_1c["PORTFOLIO_TOP_8"]
    summary_1c["ALL_11_COMPARISON"] = all_11_comparison

    # Constrói lista de dias com todos os trades (padrão = C/ Fluxo Campeão `in_flow=True`, guardando também `base_pts` e `in_base`)
    days_list = []
    for d in all_dates:
        day_obj = {
            "date": d,
            "month": d[:7],
            "is_live": False,
        }
        merged_trades = []

        for sid in ALL_11_IDS + ["WIN_E2"]:
            b_list = [t for t in base_trades_map[sid] if t["date"] == d]
            f_list = [t for t in flow_trades_map[sid] if t["date"] == d]

            b_pts = round(sum(t["pts"] for t in b_list), 2)
            f_pts = round(sum(t["pts"] for t in f_list), 2)

            day_obj[f"{sid}_pts"] = f_pts
            day_obj[f"{sid}_ops"] = len(f_list)
            day_obj[f"{sid}_base_pts"] = b_pts
            day_obj[f"{sid}_base_ops"] = len(b_list)
            day_obj[f"{sid}_flow_pts"] = f_pts
            day_obj[f"{sid}_flow_ops"] = len(f_list)

            # Trades principais do dia
            b_keys = {(t["time"], t["exit_time"], t["direction"], t["entry_price"], t["pts"]) for t in b_list}
            for t in f_list:
                tk = (t["time"], t["exit_time"], t["direction"], t["entry_price"], t["pts"])
                t_copy = dict(t)
                t_copy["in_flow"] = True
                t_copy["in_base"] = True
                t_copy["in_mt5_11"] = (sid in ALL_11_IDS)
                t_copy["in_walls_flow"] = (sid in WALLS_FLOW_6_IDS)
                t_copy["also_in_raw_base"] = tk in b_keys
                merged_trades.append(t_copy)

        # Aliases legados por dia
        day_obj["WDO_11_pts"] = day_obj["WDO_01_pts"]
        day_obj["WDO_11_ops"] = day_obj["WDO_01_ops"]
        day_obj["WDO_S2_pts"] = day_obj["WDO_01_pts"]
        day_obj["WDO_S2_ops"] = day_obj["WDO_01_ops"]

        merged_trades.sort(key=lambda x: (x["time"], x["exit_time"], x["strategy_id"]))
        day_obj["trades"] = merged_trades
        days_list.append(day_obj)

    payload = {
        "version": "6.0_PROPOSTAS_5174_TOP8_5176_WALLS6_2026",
        "start_date": all_dates[0],
        "last_bt_date": all_dates[-1],
        "total_bt_sessions": len(all_dates),
        "all_11_comparison": all_11_comparison,
        "summary_1c": summary_1c,
        "days": days_list,
    }

    out_path = os.environ.get("JUMBA_BT_OUT") or os.path.join(ROOT_DIR, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    print(f"\n  [OK] Salvo em: {out_path} ({os.path.getsize(out_path)/1024:.1f} KB)")
    print(f"  Pregões: {len(all_dates)} ({all_dates[0]} -> {all_dates[-1]})")
    print("-" * 105)
    print(f"  {'ID':<8} | {'BASE MT5 (Tr / WR / PF / Net / DD / RetDD)':<46} | {'C/ FLUXO (Filtro / Tr / PF / Net / DD / RetDD)'}")
    print("-" * 105)
    for row in all_11_comparison:
        b = row["base_mt5"]
        fl = row["with_flow"]
        print(
            f"  {row['id']:<8} | {b['ops']:>3d} tr | {b['wr_pct']:>4.1f}% | PF {b['pf']:>4.2f} | R$ {b['tot_brl_1c']:>6.0f} | DD {b['max_dd_brl_1c']:>4.0f} | {b['ret_dd']:>4.2f}x"
            f" | {row['best_flow_key']:<19} {fl['ops']:>3d} tr | PF {fl['pf']:>4.2f} | R$ {fl['tot_brl_1c']:>6.0f} | DD {fl['max_dd_brl_1c']:>4.0f} | {fl['ret_dd']:>4.2f}x"
        )
    p8 = summary_1c["PORTFOLIO_TOP_8"]
    pw6 = summary_1c["PORTFOLIO_WALLS_6"]
    print("-" * 105)
    print(f"  5174 PROPOSTA A ⭐ (TOP 8 ELITE M5 C/ FLUXO): {p8['ops']} tr | WR {p8['wr_pct']}% | PF {p8['pf']} | Net +R$ {p8['tot_brl_1c']:,.0f} | DD R$ {p8['max_dd_brl_1c']:,.0f} | Ret/DD {p8['ret_dd']}x | {p8['pos_months']}/{p8['total_months']} M+")
    print(f"  5176 PROPOSTA B ⭐ (6 WALLS V2 · 11/11 M+):   {pw6['ops']} tr | WR {pw6['wr_pct']}% | PF {pw6['pf']} | Net +R$ {pw6['tot_brl_1c']:,.0f} | DD R$ {pw6['max_dd_brl_1c']:,.0f} | Ret/DD {pw6['ret_dd']}x | {pw6['pos_months']}/{pw6['total_months']} M+")
    print("=" * 105)


if __name__ == "__main__":
    main()
