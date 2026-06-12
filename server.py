# server.py — WIN×WDO Regime Monitor (Thin Controller)
"""
FastAPI server for WIN×WDO pair trading regime monitoring.
All computation logic lives in core/ modules.
"""
import time
import sqlite3
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import math
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen

import os
import asyncio
import firebase_admin
from firebase_admin import credentials, db as fdb

# ─── Firebase Init ───────────────────────────────────────────────────────────
firebase_initialized = False
try:
    if os.path.exists("serviceAccountKey.json"):
        cred = credentials.Certificate("serviceAccountKey.json")
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://wdo-win-dashboard-default-rtdb.firebaseio.com'
            })
        firebase_initialized = True
        print("[OK] Firebase Admin SDK inicializado.")
except Exception as e:
    print(f"[ERRO] Erro ao inicializar Firebase: {e}")

from core.config import (
    SYMBOL_A, SYMBOL_B, TIMEFRAME, WINDOW, BARS, KALMAN_BURN_IN,
    BETA_INITIAL, BETA_REF_BARS, BETA_REF_5D_BARS,
    BETA_ALERT_PCT, MT5_PATH,
    TIME_OFFSET, CACHE_TTL,
    DI_SYMBOL, DI_KALMAN_Q, DI_KALMAN_R, DI_KALMAN_W,
    DI_BARS, DI_BETA_INITIAL,
    DI_BETA_REF_BARS, DI_Z_ENTRY, DI_Z_ANOMALY, DI_Z_ATTENTION,
    JOH_WINDOW, JOH_RECHECK_BARS,
    NWE_BANDWIDTH, NWE_LOOKBACK, NWE_MULT_MAE,
    WDO_KALMAN_Q, WDO_KALMAN_R, WDO_KALMAN_W,
)
from core.mt5_client import (
    connect_mt5, fetch_bars, beta_state, save_beta_ultimo, load_beta_ultimo,
)
from core.signals import (
    calc_beta_ols, calc_half_life, calc_zscore,
    get_signal, get_rho_status, get_beta_status,
    calc_nwe_with_bands,
    _coint_cache,
)
from core.kalman_filter import KalmanBetaFilter
from core.trade_engine import TradeEngine
import core.hmm_background as hmm


# ─── B3 Order Flow / RTD Broker State ────────────────────────────────────────
import random
from collections import deque

_broker_list = ["XP", "UBS", "BTG", "IDEAL", "GENIAL", "JPMORGAN", "TULLETT", "MERRILL", "GOLDMAN", "MORGAN", "CITI", "ITAU", "BRADESCO"]
_broker_flow = {
    "WIN": {b: {"id": str(idx), "net": 0, "avg": 0.0, "vol": 0, "buy": 0, "sell": 0} for idx, b in enumerate(_broker_list)}
}
_flow_history_bars = []
_last_flow_update = {"WIN": 0.0}

# Real-time institutional flow synthetic indicator cache
_raw_flow_snapshots = deque(maxlen=1000)
_realtime_flow_cache = deque(maxlen=10000)
_last_win_price = 120000.0  # Safe cached WIN price to avoid thread-unsafe MT5 calls

def calculate_persistence(snapshots, P):
    N = 10
    avail_ticks = len(snapshots) - 1
    if avail_ticks < P:
        return 0.0
    num_periods = min(N, avail_ticks // P)
    if num_periods == 0:
        return 0.0
        
    sum_fl = 0.0
    sum_abs_fl = 0.0
    
    for i in range(num_periods):
        idx_end = -1 - i * P
        idx_start = -1 - (i + 1) * P
        
        snap_end = snapshots[idx_end]
        snap_start = snapshots[idx_start]
        
        buy_sum = 0
        sell_sum = 0
        for b in _broker_list:
            buy_sum += (snap_end["flow"][b]["buy"] - snap_start["flow"][b]["buy"])
            sell_sum += (snap_end["flow"][b]["sell"] - snap_start["flow"][b]["sell"])
        fl = buy_sum - sell_sum
        sum_fl += fl
        sum_abs_fl += abs(fl)
        
    if sum_abs_fl > 0:
        return sum_fl / sum_abs_fl
    return 0.0

def _calculate_window_score(snapshots, window_seconds):
    P = window_seconds // 5
    if len(snapshots) < P + 1:
        return 0.0
        
    latest = snapshots[-1]
    start = snapshots[-1 - P]
    
    # 1. FLN (Fluxo Normalizado)
    buy_sum = 0
    sell_sum = 0
    for b in _broker_list:
        buy_sum += (latest["flow"][b]["buy"] - start["flow"][b]["buy"])
        sell_sum += (latest["flow"][b]["sell"] - start["flow"][b]["sell"])
    
    fl = buy_sum - sell_sum
    va = buy_sum + sell_sum
    fln = fl / va if va > 0 else 0.0
    
    # 2. PERS (Persistência)
    pers = calculate_persistence(snapshots, P)
    
    # 3. CONC_DIR (Concentração Direcionada)
    broker_nets = []
    for b in _broker_list:
        b_buy = latest["flow"][b]["buy"] - start["flow"][b]["buy"]
        b_sell = latest["flow"][b]["sell"] - start["flow"][b]["sell"]
        b_net = b_buy - b_sell
        broker_nets.append((b, b_net))
        
    broker_nets.sort(key=lambda x: abs(x[1]), reverse=True)
    
    sum_abs_all = sum(abs(x[1]) for x in broker_nets)
    if sum_abs_all > 0:
        sum_abs_top3 = sum(abs(broker_nets[i][1]) for i in range(min(3, len(broker_nets))))
        conc = sum_abs_top3 / sum_abs_all
        fl_top3 = sum(broker_nets[i][1] for i in range(min(3, len(broker_nets))))
        conc_dir = conc * (1 if fl_top3 > 0 else (-1 if fl_top3 < 0 else 0))
    else:
        conc_dir = 0.0
        
    # 4. ABS_DIR (Absorção Direcional)
    price_delta = latest["price"] - start["price"]
    ticks = price_delta / 5.0
    absor_t = va / (abs(ticks) + 1.0)
    
    lookback = 120
    absor_history = []
    max_idx = len(snapshots)
    start_idx = max(P, max_idx - lookback)
    
    for j in range(start_idx, max_idx):
        snap_j = snapshots[j]
        snap_prev = snapshots[j - P]
        
        j_price_delta = snap_j["price"] - snap_prev["price"]
        j_ticks = j_price_delta / 5.0
        
        j_buy = 0
        j_sell = 0
        for b in _broker_list:
            j_buy += (snap_j["flow"][b]["buy"] - snap_prev["flow"][b]["buy"])
            j_sell += (snap_j["flow"][b]["sell"] - snap_prev["flow"][b]["sell"])
            
        j_va = j_buy + j_sell
        j_absor = j_va / (abs(j_ticks) + 1.0)
        absor_history.append(j_absor)
        
    if len(absor_history) >= 5:
        mean_absor = np.mean(absor_history)
        std_absor = np.std(absor_history)
        zabs = (absor_t - mean_absor) / std_absor if std_absor > 0 else 0.0
        abs_n = max(-1.0, min(1.0, zabs / 3.0))
    else:
        abs_n = 0.0
        
    if fl < 0 and price_delta >= 0:
        abs_dir = abs_n
    elif fl > 0 and price_delta <= 0:
        abs_dir = -abs_n
    else:
        abs_dir = 0.0
        
    # ScoreFluxo_t = 100 * (0.40 * FLN_t + 0.30 * PERS_t + 0.20 * CONC_DIR_t + 0.10 * ABS_DIR_t)
    score = 100.0 * (0.40 * fln + 0.30 * pers + 0.20 * conc_dir + 0.10 * abs_dir)
    return score

def _calculate_combined_flow_score(snapshots):
    if len(snapshots) < 2:
        return 0.0
    score_5s = _calculate_window_score(snapshots, 5)
    score_15s = _calculate_window_score(snapshots, 15)
    score_60s = _calculate_window_score(snapshots, 60)
    return 0.50 * score_5s + 0.30 * score_15s + 0.20 * score_60s

def _get_current_flow_data():
    return {
        "WIN": {b: {"net": _broker_flow["WIN"][b]["net"], "buy": _broker_flow["WIN"][b]["buy"], "sell": _broker_flow["WIN"][b]["sell"]} for b in _broker_list}
    }

def _seed_flow_history():
    """Pre-generate a full day of realistic broker flow data for chart visualization."""
    import math
    global _flow_history_bars
    
    # Only seed if we have no history yet
    if _flow_history_bars:
        return
    
    SESSION_START = 9 * 60   # 09:00
    SESSION_END = 18 * 60 + 20  # 18:20
    
    # Define broker personalities (bias, volatility, trend_strength)
    profiles = {
        # Smart Money — tend to build directional positions gradually
        "UBS":      {"bias": 0.6, "vol": 400, "trend": 0.85},
        "BTG":      {"bias": 0.5, "vol": 350, "trend": 0.80},
        "JPMORGAN": {"bias": 0.4, "vol": 300, "trend": 0.75},
        "TULLETT":  {"bias": 0.3, "vol": 250, "trend": 0.70},
        "MERRILL":  {"bias": -0.2, "vol": 200, "trend": 0.65},
        "GOLDMAN":  {"bias": 0.5, "vol": 350, "trend": 0.80},
        "MORGAN":   {"bias": 0.45, "vol": 320, "trend": 0.78},
        "CITI":     {"bias": 0.35, "vol": 280, "trend": 0.72},
        # Retail / Intermediaries — noisier, tend to follow price (opposite of smart money)
        "XP":       {"bias": -0.5, "vol": 500, "trend": 0.50},
        "GENIAL":   {"bias": -0.4, "vol": 400, "trend": 0.45},
        "IDEAL":    {"bias": 0.1, "vol": 300, "trend": 0.55},
        "ITAU":     {"bias": -0.1, "vol": 350, "trend": 0.60},
        "BRADESCO": {"bias": -0.3, "vol": 300, "trend": 0.50},
    }
    
    # Cumulative state per broker
    state = {
        "WIN": {b: 0.0 for b in _broker_list}
    }
    
    bars = []
    total_bars = (SESSION_END - SESSION_START) // 5 + 1  # 5-minute bars
    
    for idx in range(total_bars):
        t_min = SESSION_START + idx * 5
        h = t_min // 60
        m = t_min % 60
        time_str = f"{h:02d}:{m:02d}"
        
        # Intraday time factor (0=open, 1=close) for trend shaping
        progress = idx / max(1, total_bars - 1)
        
        # Market phase effects
        morning_boost = max(0, 1.0 - abs(progress - 0.15) * 5)  # peak at ~10:15
        lunch_dip = max(0, 1.0 - abs(progress - 0.45) * 4)       # low at ~13:00
        afternoon_push = max(0, 1.0 - abs(progress - 0.75) * 4)  # peak at ~16:00
        
        activity = 1.0 + morning_boost * 0.8 - lunch_dip * 0.6 + afternoon_push * 0.5
        
        # Macro trend
        macro_trend = math.sin(progress * math.pi * 1.2) * 0.5
        
        sym = "WIN"
        sym_flip = 1.0
        
        for b in _broker_list:
            p = profiles[b]
            drift = (p["bias"] + macro_trend) * sym_flip * activity * 80
            noise = random.gauss(0, p["vol"] * activity)
            change = drift + noise
            state[sym][b] = state[sym][b] * p["trend"] + change
        
        win_brokers = {}
        for b in _broker_list:
            net_win = int(state["WIN"][b])
            agg_win = int(net_win * 0.7 + math.sin(progress * math.pi) * 1000)
            vol_win = int(abs(agg_win) * 1.3 + idx * 150)
            buy_win = max(0, (vol_win + agg_win) // 2)
            sell_win = max(0, (vol_win - agg_win) // 2)
            win_brokers[b] = {"net": net_win, "buy": buy_win, "sell": sell_win}

        snapshot = {
            "time": time_str,
            "timestamp": int(time.time()) - (total_bars - idx) * 300,
            "WIN": win_brokers,
        }
        bars.append(snapshot)
    
    _flow_history_bars.extend(bars)
    # Also set _broker_flow to the last snapshot values
    for b in _broker_list:
        _broker_flow["WIN"][b]["net"] = bars[-1]["WIN"][b]["net"]
        _broker_flow["WIN"][b]["buy"] = bars[-1]["WIN"][b]["buy"]
        _broker_flow["WIN"][b]["sell"] = bars[-1]["WIN"][b]["sell"]
    
    print(f"[INFO] Flow history seeded: {len(bars)} barras de {bars[0]['time']} a {bars[-1]['time']}")


def _seed_realtime_flow():
    global _realtime_flow_cache
    if len(_realtime_flow_cache) > 0:
        return
        
    now_dt = datetime.now()
    start_dt = now_dt.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # If it is before 09:00 AM, don't seed
    if now_dt < start_dt:
        return
        
    start_time = start_dt.timestamp()
    end_time = now_dt.timestamp()
    
    curr_time = start_time
    score = 0.0
    
    # Seed up to the current time, leaving at least the last few minutes for live data
    while curr_time < end_time:
        score = score * 0.96 + random.uniform(-12.0, 12.0)
        score = max(-100.0, min(100.0, score))
        
        if score >= 40.0:
            color = "#00e87a"
        elif score <= -40.0:
            color = "#ff3860"
        else:
            color = "#f5a623"
            
        _realtime_flow_cache.append({
            "time": int(curr_time),
            "value": round(score, 2),
            "color": color
        })
        curr_time += 5.0

async def flow_snapshot_loop():
    print("[INFO] Real WIN Broker Flow Snapshot Loop iniciado.")
    # Inicializa todas as corretoras com saldo zero (sem simulação)
    for b in _broker_list:
        _broker_flow["WIN"][b]["net"] = 0
        _broker_flow["WIN"][b]["buy"] = 0
        _broker_flow["WIN"][b]["sell"] = 0
        _broker_flow["WIN"][b]["vol"] = 0
        _broker_flow["WIN"][b]["avg"] = 0.0

    last_date = datetime.now().date()

    while True:
        try:
            current_time = time.time()
            now_dt = datetime.now()
            today = now_dt.date()
            
            # Reset diário se a data mudou
            if today != last_date:
                print(f"[INFO] Mudança de dia detectada ({last_date} -> {today}). Reiniciando fluxo do dashboard...")
                for b in _broker_list:
                    _broker_flow["WIN"][b]["net"] = 0
                    _broker_flow["WIN"][b]["buy"] = 0
                    _broker_flow["WIN"][b]["sell"] = 0
                    _broker_flow["WIN"][b]["vol"] = 0
                    _broker_flow["WIN"][b]["avg"] = 0.0
                _flow_history_bars.clear()
                _raw_flow_snapshots.clear()
                _realtime_flow_cache.clear()
                last_date = today

            time_str = now_dt.strftime("%H:%M")
            
            # Cria o snapshot a partir do estado atual real
            current_flow = _get_current_flow_data()
            snapshot = {
                "time": time_str,
                "timestamp": int(current_time),
                "WIN": current_flow["WIN"]
            }
            if not _flow_history_bars or _flow_history_bars[-1]["time"] != time_str:
                _flow_history_bars.append(snapshot)
            else:
                _flow_history_bars[-1] = snapshot
                
            if len(_flow_history_bars) > 600:
                _flow_history_bars.pop(0)

            # Record raw snapshot for high-frequency calculations
            raw_snap = {
                "timestamp": int(current_time),
                "price": _last_win_price,
                "flow": {b: {"net": current_flow["WIN"][b]["net"], "buy": current_flow["WIN"][b]["buy"], "sell": current_flow["WIN"][b]["sell"]} for b in _broker_list}
            }
            _raw_flow_snapshots.append(raw_snap)

            # Compute current synthetic flow score
            score = _calculate_combined_flow_score(_raw_flow_snapshots)
            
            # Classify score color
            if score >= 40.0:
                color = "#00e87a"  # Green
            elif score <= -40.0:
                color = "#ff3860"  # Red
            else:
                color = "#f5a623"  # Yellow
                
            _realtime_flow_cache.append({
                "time": int(current_time),
                "value": round(score, 2),
                "color": color
            })
                
        except Exception as e:
            print(f"[AVISO] Erro no loop de snapshot de fluxo: {e}")
        await asyncio.sleep(5.0)

# ─── App setup ───────────────────────────────────────────────────────────────
import contextlib

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if firebase_initialized:
        asyncio.create_task(firebase_push_loop())
    
    _seed_realtime_flow()  # Pre-populate real-time flow indicator cache for today
    # _seed_flow_history()  # Pre-populate flow chart with full-day simulated data
    asyncio.create_task(flow_snapshot_loop())
    
    # Run backfill async
    import threading
    threading.Thread(target=do_backfill_if_empty, daemon=True).start()
    
    yield
    # Shutdown

app = FastAPI(title="WIN×WDO Regime Monitor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

async def firebase_push_loop():
    print("[INFO] Firebase Sync Loop iniciado.")
    last_hist_update = 0
    last_dash_update = 0
    while True:
        try:
            if firebase_initialized:
                # Chama as funções nativamente (cuidado com MT5: executado na main thread de evento)
                r_v2 = regime_v2()
                r_di = di_regime()
                perf = get_performance()
                
                current_time = time.time()
                
                # Check for immediate push condition
                action_v2 = r_v2.get("trade_engine", {}).get("action", "WAIT")
                push_immediate = action_v2 not in ("WAIT", "HOLDING", "ANOMALY")
                
                # Push para RTDB (dashboard live) a cada 15 segundos ou imediatamente se houver trade
                if push_immediate or current_time - last_dash_update >= 15:
                    ref = fdb.reference('dashboard')
                    ref.set({
                        'regime': r_v2,
                        'di_regime': r_di,
                        'performance': perf,
                    })
                    last_dash_update = current_time

                # Push history_30d a cada 5 minutos (300 segundos) para economizar banda
                if current_time - last_hist_update > 300:
                    hist = history_endpoint(days=30)
                    ref_hist = fdb.reference('history_30d')
                    ref_hist.set(hist.get("history", []))
                    last_hist_update = current_time

        except Exception as e:
            print(f"[AVISO] Erro no sync do Firebase: {e}")
        await asyncio.sleep(2.5)  # Envia live a cada 2.5s

_trade_engine = TradeEngine(db_path="trades.db")
_cache: dict = {}
_cache_ts: float = 0.0

# DI pair trading state
_di_cache: dict = {}
_di_cache_ts: float = 0.0
_di_beta_state = {
    "current_beta": DI_BETA_INITIAL,
    "previous_beta": DI_BETA_INITIAL,
    "last_calc_date": None,
    "last_calc_hour": None,
    "unstable": False,
}
_di_coint_cache = {"date": None, "is_coint": False, "pvalue": 1.0}

# DI Kalman filter (persistent across requests)
_di_kalman = KalmanBetaFilter(
    initial_beta=DI_BETA_INITIAL,
    trans_cov=DI_KALMAN_Q,
    obs_cov=DI_KALMAN_R,
)
_di_kalman_spreads = []
_di_kalman_initialized = False

# Johansen gate state (periodic recheck)
_joh_wdo_state = {
    "gate_open": False, "trace_ratio": 0.0, "joh_beta": None,
    "last_check_i": -999, "conviction": "N/A",
}
_joh_di_state = {
    "gate_open": False, "trace_ratio": 0.0, "joh_beta": None,
    "last_check_i": -999, "conviction": "N/A",
}


def _compute_johansen_gate(closes_a, closes_b, state, bar_count):
    """Recompute Johansen cointegration gate if enough bars elapsed.
    Modifies state in-place. Returns (gate_open, trace_ratio, conviction, joh_beta).
    """
    if bar_count - state["last_check_i"] >= JOH_RECHECK_BARS and len(closes_a) >= JOH_WINDOW:
        try:
            y = np.column_stack([
                closes_a[-JOH_WINDOW:],
                closes_b[-JOH_WINDOW:],
            ])
            result = coint_johansen(y, det_order=0, k_ar_diff=1)
            trace_stat = float(result.lr1[0])       # r=0 trace statistic
            crit_95 = float(result.cvt[0, 1])       # 95% critical value
            state["gate_open"] = bool(trace_stat > crit_95)
            state["trace_ratio"] = round(trace_stat / crit_95, 3) if crit_95 > 0 else 0.0
            vec = result.evec[:, 0]
            vec = vec / vec[0]
            state["joh_beta"] = float(vec[1])
            # Conviction label
            r = state["trace_ratio"]
            if r >= 1.5:
                state["conviction"] = "FORTE"
            elif r >= 1.0:
                state["conviction"] = "MODERADA"
            else:
                state["conviction"] = "FRACA"
            state["last_check_i"] = bar_count
        except Exception:
            pass
    return (
        state["gate_open"],
        state["trace_ratio"],
        state["conviction"],
        state["joh_beta"],
    )


# ─── DB init ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_in DATETIME,
            status TEXT,
            z_in REAL,
            rho_in REAL,
            beta_in REAL,
            qty_wdo INTEGER,
            qty_win INTEGER,
            price_wdo_in REAL,
            price_win_in REAL,
            timestamp_out DATETIME,
            exit_reason TEXT,
            price_wdo_out REAL,
            price_win_out REAL,
            pnl_brl REAL,
            max_pts_favor REAL DEFAULT 0.0,
            be_active INTEGER DEFAULT 0
        )
    ''')
    try:
        c.execute("ALTER TABLE operations ADD COLUMN max_pts_favor REAL DEFAULT 0.0")
        c.execute("ALTER TABLE operations ADD COLUMN be_active INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

init_db()


# ─── Helpers ─────────────────────────────────────────────────────────────────
SESSION_START = 8 * 60 + 50     # 08:50
SESSION_END   = 18 * 60 + 20    # 18:20

TF_NAMES = {
    mt5.TIMEFRAME_M1: "M1", mt5.TIMEFRAME_M5: "M5",
    mt5.TIMEFRAME_M15: "M15", mt5.TIMEFRAME_M30: "M30",
    mt5.TIMEFRAME_H1: "H1", mt5.TIMEFRAME_H4: "H4",
}


def save_bar_history(timestamp, date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up, flow_json=None):
    try:
        conn = sqlite3.connect("trades.db", timeout=10.0)
        c = conn.cursor()
        c.execute('''
            INSERT OR IGNORE INTO bar_history 
            (timestamp, date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up, flow_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (int(timestamp), date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, int(nwe_is_up), flow_json))
        # Always update flow_json if provided (handles bars inserted before flow was available)
        if flow_json:
            c.execute('''
                UPDATE bar_history SET flow_json = ? WHERE timestamp = ?
            ''', (flow_json, int(timestamp)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERRO DB] falha ao salvar bar_history: {e}")

def load_bar_history(days=30):
    try:
        conn = sqlite3.connect("trades.db", timeout=10.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        ts_limit = int(time.time()) - days * 86400
        c.execute("SELECT * FROM bar_history WHERE timestamp >= ? ORDER BY timestamp ASC", (ts_limit,))
        rows = c.fetchall()
        conn.close()
        
        import json
        from datetime import datetime
        history = []
        for i, r in enumerate(rows):
            dt_time = datetime.strptime(r["bar_time"], "%H:%M")
            z_wdo = r["z_wdo"]
            z_di = r["z_di"] or 0.0
            win_price = r["win_price"]
            
            nv = r["nwe_center"]
            nu = r["nwe_upper"]
            nl = r["nwe_lower"]
            n_up = bool(r["nwe_is_up"]) if "nwe_is_up" in r.keys() else None
            
            npu = npl = None
            if nv is not None and nu is not None and nl is not None:
                envW = nu - nv
                PROX_PCT = 0.10
                npu = nu - (2 * envW) * PROX_PCT
                npl = nl + (2 * envW) * PROX_PCT
                
            cons_wdo_sig = -1 if z_wdo <= -1.4 else (1 if z_wdo >= 1.4 else 0)
            cons_di_sig = -1 if z_di <= -1.4 else (1 if z_di >= 1.4 else 0)
            
            sig_wdo = cons_wdo_sig
            sig_di = cons_di_sig
            
            if win_price is not None and n_up is not None and npu is not None:
                isBuyBlocked = n_up or (win_price > npl)
                isSellBlocked = not n_up or (win_price < npu)
                
                if isBuyBlocked:
                    if z_wdo < 0: sig_wdo, z_wdo = 0, 0
                    if z_di < 0: sig_di, z_di = 0, 0
                if isSellBlocked:
                    if z_wdo > 0: sig_wdo, z_wdo = 0, 0
                    if z_di > 0: sig_di, z_di = 0, 0
            
            flow_data = None
            if "flow_json" in r.keys() and r["flow_json"]:
                try:
                    flow_data = json.loads(r["flow_json"])
                except Exception:
                    pass
            
            history.append({
                "i": i,
                "z": r["z_wdo"],
                "z_di": r["z_di"],
                "spread": r["spread_wdo"],
                "bar_time": r["bar_time"],
                "date": r["date_str"],
                "t_min": dt_time.hour * 60 + dt_time.minute,
                "win_price": win_price,
                
                "nwe": nv,
                "nweUpper": nu,
                "nweLower": nl,
                "nweProxUpper": npu,
                "nweProxLower": npl,
                "isUp": n_up,
                "is_up": n_up,
                
                "z_raw_wdo": z_wdo,
                "z_raw_di": z_di,
                "z_unfiltered_wdo": r["z_wdo"],
                "z_unfiltered_di": r["z_di"],
                "sig_wdo": sig_wdo,
                "sig_di": sig_di,
                "cons_wdo_sig": cons_wdo_sig,
                "cons_di_sig": cons_di_sig,
                "flow": flow_data
            })
        return history
    except Exception as e:
        print(f"[ERRO DB] falha ao carregar bar_history: {e}")
        return []

def do_backfill_if_empty():
    try:
        conn = sqlite3.connect("trades.db", timeout=10.0)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bar_history")
        count = c.fetchone()[0]
        conn.close()
        if count > 0:
            print(f"[OK] bar_history possui {count} registros.")
            return
            
        print("[INFO] bar_history vazio. Iniciando backfill de 30 dias...")
        import urllib.request
        urllib.request.urlopen("http://localhost:8080/api/history?days=30")
        print("[OK] Backfill concluido via chamada ao endpoint local.")
    except Exception as e:
        print(f"[ERRO] Falha no backfill: {e}")

def _build_history(bar_times, z_arr, spread_arr, z_v1_arr=None, win_prices=None, nwe_data=None, di_map=None):
    """Build filtered session history from bar data, including NWE and DI."""
    n = len(z_arr)
    v1_len = len(z_v1_arr) if z_v1_arr is not None else 0
    win_len = len(win_prices) if win_prices is not None else 0
    
    nwe_line, nwe_upper, nwe_lower, nwe_is_up = nwe_data if nwe_data else (None, None, None, None)
    nwe_len = len(nwe_line) if nwe_line is not None else 0
    bar_info = []
    for i in range(n):
        local_ts = int(bar_times[i]) + TIME_OFFSET
        dt = datetime.fromtimestamp(local_ts)
        t_min = dt.hour * 60 + dt.minute
        entry = {
            "z": round(float(z_arr[i]), 3),
            "spread": round(float(spread_arr[i]), 2),
            "bar_time": dt.strftime("%H:%M"),
            "date": dt.strftime("%Y-%m-%d"),
            "t_min": t_min,
        }
        if z_v1_arr is not None:
            v1_idx = i - (n - v1_len)
            entry["z_v1"] = round(float(z_v1_arr[v1_idx]), 3) if 0 <= v1_idx < v1_len else 0.0
            
        win_val = None
        if win_prices is not None:
            win_idx = i - (n - win_len)
            win_val = float(win_prices[win_idx]) if 0 <= win_idx < win_len else 0.0
            entry["win_price"] = win_val
            
        z_di_val = di_map.get(local_ts, 0.0) if di_map else 0.0
        entry["z_di"] = z_di_val
        
        z_wdo = round(float(z_arr[i]), 3)
        orig_z_wdo = z_wdo
        orig_z_di_val = z_di_val
        
        cons_wdo_sig = -1 if orig_z_wdo <= -1.4 else (1 if orig_z_wdo >= 1.4 else 0)
        cons_di_sig = -1 if orig_z_di_val <= -1.4 else (1 if orig_z_di_val >= 1.4 else 0)
        
        sig_wdo = cons_wdo_sig
        sig_di = cons_di_sig
        
        if nwe_line is not None:
            nwe_idx = i - (n - nwe_len)
            if 0 <= nwe_idx < nwe_len:
                nv = float(nwe_line[nwe_idx])
                nu = float(nwe_upper[nwe_idx])
                nl = float(nwe_lower[nwe_idx])
                n_is_up = bool(nwe_is_up[nwe_idx])
                
                envW = nu - nv
                PROX_PCT = 0.10
                npu = nu - (2 * envW) * PROX_PCT
                npl = nl + (2 * envW) * PROX_PCT
                
                entry["nwe"] = round(nv, 2)
                entry["nweUpper"] = round(nu, 2)
                entry["nweLower"] = round(nl, 2)
                entry["nweProxUpper"] = round(npu, 2)
                entry["nweProxLower"] = round(npl, 2)
                entry["isUp"] = n_is_up
                entry["is_up"] = n_is_up
                
                if win_val is not None:
                    isBuyBlocked = n_is_up or (win_val > npl)
                    isSellBlocked = not n_is_up or (win_val < npu)
                    
                    if isBuyBlocked:
                        if z_wdo < 0: sig_wdo, z_wdo = 0, 0
                        if z_di_val < 0: sig_di, z_di_val = 0, 0
                    if isSellBlocked:
                        if z_wdo > 0: sig_wdo, z_wdo = 0, 0
                        if z_di_val > 0: sig_di, z_di_val = 0, 0
                        
        entry["z_raw_wdo"] = z_wdo
        entry["z_raw_di"] = z_di_val
        entry["z_unfiltered_wdo"] = orig_z_wdo
        entry["z_unfiltered_di"] = orig_z_di_val
        entry["sig_wdo"] = sig_wdo
        entry["sig_di"] = sig_di
        entry["cons_wdo_sig"] = cons_wdo_sig
        entry["cons_di_sig"] = cons_di_sig

        bar_info.append(entry)

    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")

    history = []
    for b in bar_info:
        if b["date"] == today_str and SESSION_START <= b["t_min"] <= SESSION_END:
            entry = {k: v for k, v in b.items()}
            entry["i"] = len(history)
            history.append(entry)

    return history


def _update_beta_state(closes_a, closes_b):
    """Hourly beta state machine update. Returns (beta_ols, beta_ref_20d, delta_pct, change_pct, unstable)."""
    today = datetime.now().date()
    now_hour = datetime.now().hour
    now_min = datetime.now().minute

    ref_window = min(BETA_REF_BARS, len(closes_a))
    beta_ref_20d = calc_beta_ols(closes_a[-ref_window:], closes_b[-ref_window:], window=ref_window)

    beta_ols = beta_state["current_beta"]

    is_calc_time = False
    if beta_state["last_calc_date"] != today or beta_state["last_calc_hour"] != now_hour:
        if now_min >= 30 and now_hour in [9, 10, 11, 12, 13, 14, 15, 16, 17]:
            if not (now_hour == 17 and now_min >= 55):
                is_calc_time = True

    if is_calc_time:
        new_b = calc_beta_ols(closes_a, closes_b, window=WINDOW)

        if beta_state["last_calc_hour"] is not None and beta_state["last_calc_date"] == today:
            delta_b = abs(new_b - beta_ols) / abs(beta_ols) * 100 if beta_ols != 0 else 0
            beta_state["unstable"] = bool(delta_b > 15.0)
        else:
            beta_state["unstable"] = False

        beta_state["previous_beta"] = beta_ols
        beta_state["current_beta"] = new_b
        beta_state["last_calc_date"] = today
        beta_state["last_calc_hour"] = now_hour
        beta_ols = new_b

        if now_hour == 17:
            save_beta_ultimo(beta_ols)

    beta_delta_pct = (abs(beta_ols - beta_ref_20d) / abs(beta_ref_20d)) * 100 if beta_ref_20d != 0 else 0.0
    beta_change_pct = ((beta_ols - beta_state["previous_beta"]) / abs(beta_state["previous_beta"])) * 100 if beta_state["previous_beta"] != 0 else 0.0

    # Run daily cointegration test (once per calc time)
    if is_calc_time and len(closes_a) >= BETA_REF_BARS:
        try:
            _, pval, _ = coint(closes_a[-BETA_REF_BARS:], closes_b[-BETA_REF_BARS:])
            _coint_cache["date"] = today
            _coint_cache["is_coint"] = bool(pval < 0.05)
            _coint_cache["pvalue"] = pval
        except Exception:
            pass

    return beta_ols, beta_ref_20d, beta_delta_pct, beta_change_pct, beta_state["unstable"]


def _build_response(current_z, current_rho, half_life, strength,
                     beta_ols, beta_ref_20d, beta_delta_pct, beta_change_pct, beta_unstable,
                     rho_status, beta_status, safe_to_trade,
                     trade_result, history, version="v1"):
    """Build the common response dict for both V1 and V2 endpoints."""
    now = datetime.now()
    return {
        "current_z":       round(current_z, 3),
        "current_rho":     round(current_rho, 3),
        "half_life":       round(half_life, 2) if half_life != float("inf") else 0.0,
        "signal":          get_signal(current_z, hmm_state=hmm.current_hmm_regime),
        "strength":        round(strength, 1),
        "beta_ols":        round(beta_ols, 4),
        "beta_ref_5d":     round(beta_ols, 4),
        "beta_drift_5d":   0.0,
        "beta_ref_20d":    round(beta_ref_20d, 4),
        "beta_delta_pct":  round(beta_delta_pct, 2),
        "beta_prev":       round(beta_state["previous_beta"], 4),
        "beta_change_pct": round(beta_change_pct, 2),
        "beta_unstable":   beta_unstable,
        "coint_eg": {
            "is_coint": _coint_cache["is_coint"],
            "pvalue":   round(_coint_cache["pvalue"], 4)
        },
        "regime_health": {
            "rho": {
                "value":  round(current_rho, 3),
                "status": rho_status["label"],
                "action": rho_status["action"],
                "color":  rho_status["color"],
                "level":  rho_status["level"],
            },
            "beta": {
                "current":    round(beta_ols, 4),
                "ref_20d":    round(beta_ref_20d, 4),
                "delta_pct":  round(beta_delta_pct, 2),
                "status":     beta_status["label"],
                "action":     beta_status["action"],
                "color":      beta_status["color"],
                "level":      beta_status["level"],
            },
            "safe_to_trade": safe_to_trade,
        },
        "history": history,
        "last_update":     now.strftime("%H:%M:%S"),
        "last_update_iso": now.isoformat(timespec="seconds"),
        "meta": {
            "version":    version,
            "symbol_a":   SYMBOL_A,
            "symbol_b":   SYMBOL_B,
            "beta":       round(beta_ols, 4),
            "window":     WINDOW if version == "v1" else "KALMAN",
            "timeframe":  TF_NAMES.get(TIMEFRAME, str(TIMEFRAME)),
            "hmm_regime": hmm.current_hmm_regime,
        },
        "trade_engine": {
            "action": trade_result["action"],
            "exit_reason": trade_result.get("exit_reason"),
            "pnl": trade_result.get("pnl"),
            "holding": trade_result.get("holding", False),
            "strategies": trade_result.get("strategies", {}),
        },
        "error": None,
    }


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/api/regime")
def regime():
    """V1 endpoint — OLS-based regime monitoring."""
    global _cache, _cache_ts

    if time.time() - _cache_ts < CACHE_TTL and _cache:
        return _cache

    if not connect_mt5():
        return {"error": "MT5 não disponível.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": []}

    needed = max(BARS, BETA_REF_BARS) + WINDOW + 10
    closes_a, times_a = fetch_bars(SYMBOL_A, needed)
    closes_b, times_b = fetch_bars(SYMBOL_B, needed)

    global _last_win_price
    if closes_a is not None and len(closes_a) > 0:
        _last_win_price = float(closes_a[-1])

    if closes_a is None or closes_b is None:
        return {"error": f"Sem dados para '{SYMBOL_A}'/'{SYMBOL_B}'.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": []}

    min_len = min(len(closes_a), len(closes_b))
    closes_a, closes_b, times_a = closes_a[-min_len:], closes_b[-min_len:], times_a[-min_len:]

    # Beta state machine
    beta_ols, beta_ref_20d, beta_delta_pct, beta_change_pct, beta_unstable = _update_beta_state(closes_a, closes_b)

    # Z-score + regime health
    spread_arr, z_arr, rho_arr = calc_zscore(closes_a, closes_b, beta=beta_ols)
    half_life = calc_half_life(spread_arr)
    current_spread_sd = np.std(spread_arr[-WINDOW:]) if len(spread_arr) >= WINDOW else 1.0
    current_z = float(z_arr[-1])
    current_rho = float(rho_arr[-1])
    strength = min(100.0, abs(current_z) / 4.0 * 100.0)

    rho_status = get_rho_status(current_rho)
    beta_status_d = get_beta_status(beta_delta_pct)
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2 and _coint_cache["pvalue"] < 0.10 and not beta_unstable)

    # V2 Kalman z for BUY routing
    kf_temp = KalmanBetaFilter(initial_beta=BETA_INITIAL)
    for y, x in zip(closes_a, closes_b):
        kf_temp.update(float(y), float(x))
    z_kalman = float(KalmanBetaFilter.rolling_zscore([s for _, s, _ in [kf_temp.update(float(y), float(x)) for y, x in zip(closes_a, closes_b)]], window=WINDOW)[-1]) if False else 0.0

    # Recalculate properly
    kf_temp2 = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
    kf_spreads = []
    for y, x in zip(closes_a, closes_b):
        _, spread_t, _ = kf_temp2.update(float(y), float(x))
        kf_spreads.append(spread_t)
    z_kalman = float(KalmanBetaFilter.rolling_zscore(kf_spreads, window=WDO_KALMAN_W)[-1])

    # Trade engine
    now_dt = datetime.now()
    trade_result = _trade_engine.evaluate(
        z_wdo=current_z, z_di=0.0,
        win_price=float(closes_a[-1]), wdo_price=float(closes_b[-1]),
        rho=current_rho, beta_safe=safe_to_trade, hmm_state=hmm.current_hmm_regime,
        hour=now_dt.hour, minute=now_dt.minute, beta_value=beta_ols,
    )

    history = _build_history(times_a[-BARS:], z_arr, spread_arr, win_prices=closes_a[-BARS:])

    _cache = _build_response(
        current_z, current_rho, half_life, strength,
        beta_ols, beta_ref_20d, beta_delta_pct, beta_change_pct, beta_unstable,
        rho_status, beta_status_d, safe_to_trade,
        trade_result, history, version="v1_ols",
    )
    _cache_ts = time.time()
    return _cache


@app.get("/api/v2/regime")
def regime_v2():
    """V2 endpoint — Kalman-based regime monitoring + Johansen gate."""
    if not connect_mt5():
        return {"error": "MT5 não disponível.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": []}

    closes_a, times_a = fetch_bars(SYMBOL_A, max(KALMAN_BURN_IN, JOH_WINDOW + 10))
    closes_b, times_b = fetch_bars(SYMBOL_B, max(KALMAN_BURN_IN, JOH_WINDOW + 10))

    global _last_win_price
    if closes_a is not None and len(closes_a) > 0:
        _last_win_price = float(closes_a[-1])

    if closes_a is None or closes_b is None:
        return {"error": "Sem dados.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": []}

    min_len = min(len(closes_a), len(closes_b))
    ac, bc, tc = closes_a[-min_len:], closes_b[-min_len:], times_a[-min_len:]

    # Kalman filter
    kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
    spreads, kf_betas = [], []
    beta_current = BETA_INITIAL
    for y, x in zip(ac, bc):
        beta, spread, var = kf.update(y, x)
        spreads.append(spread)
        kf_betas.append(beta)
        beta_current = beta

    z_scores_full = KalmanBetaFilter.rolling_zscore(spreads, window=WDO_KALMAN_W)
    
    # ── NWE computation BEFORE slicing ───────────────────────────────────
    # Compute on the last 200 bars to prevent cone effect
    nwe_lookback_bars = min(len(ac), BARS + 200)
    ac_nwe = ac[-nwe_lookback_bars:]
    nwe_line_full, nwe_upper_full, nwe_lower_full, nwe_is_up_full = calc_nwe_with_bands(
        ac_nwe, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
    )

    # ── Slice after burn-in to keep payload and NWE/OLS fast ────────────
    if len(ac) > BARS:
        ac, bc, tc = ac[-BARS:], bc[-BARS:], tc[-BARS:]
        spreads = spreads[-BARS:]
        kf_betas = kf_betas[-BARS:]
        z_scores = z_scores_full[-BARS:]
        nwe_line = nwe_line_full[-BARS:]
        nwe_upper = nwe_upper_full[-BARS:]
        nwe_lower = nwe_lower_full[-BARS:]
        nwe_is_up_arr = nwe_is_up_full[-BARS:]
    else:
        z_scores = z_scores_full
        nwe_line = nwe_line_full
        nwe_upper = nwe_upper_full
        nwe_lower = nwe_lower_full
        nwe_is_up_arr = nwe_is_up_full

    current_z = float(z_scores[-1])
    current_spread_sd = np.std(spreads[-40:]) if len(spreads) >= 40 else 1.0

    # V1 OLS z-scores + rho (keep for trade engine, not for display)
    beta_ols_real = beta_state["current_beta"]
    spread_v1, z_v1_arr, rho_arr = calc_zscore(ac, bc, beta=beta_ols_real)
    current_rho = float(rho_arr[-1])
    rho_status = get_rho_status(current_rho)

    # Johansen gate
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        ac, bc, _joh_wdo_state, len(ac)
    )

    # Beta health
    beta_ref_20d = float(np.mean(kf_betas[-80:-40]) if len(kf_betas) > 80 else kf_betas[0])
    beta_delta_pct = ((beta_current - beta_ref_20d) / abs(beta_ref_20d) * 100) if beta_ref_20d != 0 else 0
    beta_status_d = get_beta_status(beta_delta_pct)
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2)
    nwe_is_up_now = bool(nwe_is_up_arr[-1])
    nwe_upper_now = float(nwe_upper[-1])
    nwe_lower_now = float(nwe_lower[-1])

    # Trade engine (Consenso WDO + DI + NWE filters)
    now_dt = datetime.now()
    z_di = _di_cache.get("current_z", 0.0) if _di_cache else 0.0
    
    # ── Bar-close gate: entries only on confirmed bar close ──────────
    # Detect if the last bar timestamp changed since last poll
    last_bar_ts = int(tc[-1])
    bar_close_confirmed = False
    if not hasattr(regime_v2, "_last_bar_ts") or regime_v2._last_bar_ts != last_bar_ts:
        bar_close_confirmed = True
        regime_v2._last_bar_ts = last_bar_ts
        # Force DI cache update on bar close to prevent race conditions in consensus logic
        di_regime()
        
        # SAVE CLOSED BAR STATE TO DATABASE FOR PERSISTENCE
        try:
            if len(ac) > 1:
                z_wdo_closed = z_scores[-2]
                spread_wdo_closed = spreads[-2]
                win_price_closed = ac[-2]
                wdo_price_closed = bc[-2]
                nwe_center_closed = nwe_line[-2]
                nwe_upper_closed = nwe_upper[-2]
                nwe_lower_closed = nwe_lower[-2]
                nwe_is_up_closed = nwe_is_up_arr[-2]
                closed_ts = int(tc[-2])
                
                z_di_closed = 0.0
                if _di_cache and "history" in _di_cache and len(_di_cache["history"]) > 0:
                    z_di_closed = _di_cache["history"][-1]["z"]
                
                dt_c = datetime.fromtimestamp(closed_ts + TIME_OFFSET)
                bar_time_c = dt_c.strftime("%H:%M")
                date_str_c = dt_c.strftime("%Y-%m-%d")
                
                import json
                current_flow = _get_current_flow_data()
                flow_json_str = json.dumps(current_flow)
                
                save_bar_history(
                    timestamp=closed_ts, date_str=date_str_c, bar_time=bar_time_c,
                    win_price=win_price_closed, wdo_price=wdo_price_closed, di_price=0.0,
                    spread_wdo=spread_wdo_closed, spread_di=0.0,
                    z_wdo=z_wdo_closed, z_di=z_di_closed,
                    nwe_center=nwe_center_closed, nwe_upper=nwe_upper_closed, nwe_lower=nwe_lower_closed,
                    nwe_is_up=nwe_is_up_closed,
                    flow_json=flow_json_str
                )
        except Exception as e:
            print(f"[ERRO DB SAVE] {e}")

    # Re-fetch DI cache after forced update
    z_di = _di_cache.get("current_z", 0.0) if _di_cache else 0.0

    trade_result = _trade_engine.evaluate(
        z_wdo=current_z, z_di=float(z_di),
        win_price=float(ac[-1]), wdo_price=float(bc[-1]),
        rho=current_rho, beta_safe=safe_to_trade, hmm_state=hmm.current_hmm_regime,
        hour=now_dt.hour, minute=now_dt.minute, beta_value=beta_current,
        nwe_is_up=nwe_is_up_now, nwe_upper=nwe_upper_now, nwe_lower=nwe_lower_now,
        bar_close_confirmed=bar_close_confirmed,
    )

    # History — Statefully loaded from DB to prevent repainting
    db_hist = load_bar_history(days=2) # Load last 2 days is enough for dashboard
    today_str = datetime.now().strftime("%Y-%m-%d")
    db_hist = [h for h in db_hist if h.get("date") == today_str]  # Only today for live view
    
    di_map = {}
    if _di_cache and "history" in _di_cache:
        for dh in _di_cache["history"]:
            dt_str = dh.get("date", "") + " " + dh.get("bar_time", "")
            try:
                local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                di_map[int(local_dt.timestamp())] = dh.get("z", 0.0)
            except Exception:
                pass

    live_history = _build_history(
        tc, z_scores, spreads, win_prices=ac,
        nwe_data=(nwe_line, nwe_upper, nwe_lower, nwe_is_up_arr),
        di_map=di_map
    )
    
    merged_map = {}
    for lh in live_history:
        ts_str = lh["date"] + " " + lh["bar_time"]
        merged_map[ts_str] = lh
        
    for db_h in db_hist:
        ts_str = db_h["date"] + " " + db_h["bar_time"]
        merged_map[ts_str] = db_h
        
    history = [merged_map[k] for k in sorted(merged_map.keys())]
    
    # Attach current flow data to live/open bars that lack it
    current_flow = _get_current_flow_data()
    for h in history:
        if "flow" not in h or h["flow"] is None:
            h["flow"] = current_flow

    

    sig_data = get_signal(current_z, current_spread_sd, beta_current, hmm_state=hmm.current_hmm_regime)

    res = _build_response(
        current_z, current_rho, 0, min(100.0, abs(current_z) / 4.0 * 100.0),
        beta_current, beta_ref_20d, beta_delta_pct, 0.0, beta_status_d["level"] >= 2,
        rho_status, beta_status_d, safe_to_trade,
        trade_result, history, version="v2_kalman",
    )
    res["beta_kalman"] = round(float(beta_current), 4)
    res["beta_ols_real"] = round(float(beta_ols_real), 4)
    res["johansen_gate"] = {
        "open": joh_open,
        "trace_ratio": joh_ratio,
        "conviction": joh_conv,
        "joh_beta": round(joh_beta, 4) if joh_beta is not None else None,
    }
    # NWE state for dashboard
    res["nwe"] = {
        "is_up": nwe_is_up_now,
        "upper": round(nwe_upper_now, 2),
        "lower": round(nwe_lower_now, 2),
        "center": round(float(nwe_line[-1]), 2),
    }
    return res


# ─── DI Pair Trading Endpoint ────────────────────────────────────────────────

def _get_di_signal(z, z_entry=DI_Z_ENTRY, z_anomaly=DI_Z_ANOMALY):
    """Signal logic for WIN×DI pair (inverse relationship).
    
    DI sobe → WIN cai (juros altos = bolsa cai)
    z > 0 means WIN is high relative to DI → expect WIN to fall
    z < 0 means WIN is low relative to DI → expect WIN to rise
    """
    az = abs(z)
    if az >= z_anomaly:
        return {"id": "anomalia", "label": "ANOMALIA", "sub": "Nao operar — relacao WIN×DI fora do padrao",
                "win": None, "di": None, "color": "#ff3860"}
    if z >= z_entry:
        return {"id": "vendeWin", "label": "VENDE WIN · COMPRA DI",
                "sub": "WIN sobrevalorizado vs DI — spread revertendo",
                "win": "VENDER", "di": "COMPRAR", "color": "#ff6b6b"}
    if z <= -z_entry:
        return {"id": "compraWin", "label": "COMPRA WIN · VENDE DI",
                "sub": "WIN subvalorizado vs DI — spread revertendo",
                "win": "COMPRAR", "di": "VENDER", "color": "#51cf66"}
    if az >= DI_Z_ATTENTION:
        return {"id": "atencao", "label": "ZONA DE DIVERGENCIA",
                "sub": f"Aguardar Z atingir +/-{z_entry} para entrar",
                "win": None, "di": None, "color": "#f5a623"}
    return {"id": "neutro", "label": "AGUARDAR",
            "sub": "Spread WIN×DI em equilibrio",
            "win": None, "di": None, "color": "#445560"}


@app.get("/api/di-regime")
def di_regime():
    """WIN×DI pair trading — Johansen z-score + gate."""
    global _di_cache, _di_cache_ts, _di_beta_state, _di_coint_cache

    if time.time() - _di_cache_ts < CACHE_TTL and _di_cache:
        return _di_cache

    if not connect_mt5():
        return {"error": "MT5 nao disponivel.", "current_z": 0, "signal": _get_di_signal(0), "history": []}

    # Fetch data — need enough for Kalman + Johansen gate
    needed = max(KALMAN_BURN_IN, DI_BETA_REF_BARS, JOH_WINDOW) + DI_KALMAN_W + 10
    closes_win, times_win = fetch_bars(SYMBOL_A, needed)
    closes_di, times_di = fetch_bars(DI_SYMBOL, needed)

    if closes_win is None or closes_di is None:
        return {"error": f"Sem dados para '{SYMBOL_A}'/'{DI_SYMBOL}'.",
                "current_z": 0, "signal": _get_di_signal(0), "history": []}

    min_len = min(len(closes_win), len(closes_di))
    closes_win = closes_win[-min_len:]
    closes_di = closes_di[-min_len:]
    times_win = times_win[-min_len:]

    today = datetime.now().date()

    # ── Johansen gate + beta ──────────────────────────────────────────
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        closes_win, closes_di, _joh_di_state, len(closes_win)
    )

    # ── DI Kalman z-score (Restored to Kalman Pure) ──
    # Para evitar que o Kalman inverta a correlação (beta positivo) devido à diferença de escala absurda,
    # inicializamos o intercepto (alpha) e o beta baseados no OLS inicial.
    if len(closes_win) > 100:
        b, a = np.polyfit(closes_di[:100], closes_win[:100], 1)
        init_beta, init_alpha = b, a
    else:
        init_beta, init_alpha = DI_BETA_INITIAL, 260000.0

    kf_di = KalmanBetaFilter(initial_beta=init_beta, initial_alpha=init_alpha, trans_cov=DI_KALMAN_Q, obs_cov=DI_KALMAN_R)
    spreads = []
    kf_betas = []
    for y, x in zip(closes_win, closes_di):
        beta, spread, _ = kf_di.update(float(y), float(x))
        spreads.append(spread)
        kf_betas.append(beta)
        
    beta_current = kf_betas[-1]
    
    spread_arr = np.array(spreads)
    z_arr = KalmanBetaFilter.rolling_zscore(spreads, window=DI_KALMAN_W)
    current_z = float(z_arr[-1]) if len(z_arr) > 0 else 0.0

    # NaN protection
    if math.isnan(beta_current) or math.isnan(current_z):
        return {"error": "OLS NaN", "current_z": 0, "signal": _get_di_signal(0), "history": []}

    method_label = "kalman"

    # Rho (correlation) — use Kalman beta
    _, _, rho_arr = calc_zscore(closes_win, closes_di, beta=beta_current)
    current_rho = float(rho_arr[-1]) if len(rho_arr) > 0 and not math.isnan(float(rho_arr[-1])) else 0.0

    spread_arr = np.array(spreads)
    half_life = calc_half_life(spread_arr)
    strength = min(100.0, abs(current_z) / 4.0 * 100.0)

    # ── Beta tracking ─────────────────────────────────────────────────
    ref_window = min(DI_BETA_REF_BARS, len(closes_win))
    beta_ref_20d = calc_beta_ols(closes_win[-ref_window:], closes_di[-ref_window:], window=ref_window)

    prev_beta = _di_beta_state["current_beta"]
    if prev_beta == DI_BETA_INITIAL:
        prev_beta = beta_current
    _di_beta_state["previous_beta"] = prev_beta
    _di_beta_state["current_beta"] = beta_current
    _di_beta_state["last_calc_date"] = today

    beta_delta_pct = (abs(beta_current - beta_ref_20d) / abs(beta_ref_20d)) * 100 if beta_ref_20d != 0 else 0.0
    beta_change_pct = ((beta_current - prev_beta) / abs(prev_beta)) * 100 if prev_beta != 0 else 0.0
    _di_beta_state["unstable"] = bool(abs(beta_change_pct) > 15.0)

    # ── Cointegration test Engle-Granger (legacy, once per day) ───────
    if _di_coint_cache["date"] != today and len(closes_win) >= DI_BETA_REF_BARS:
        try:
            _, pval, _ = coint(closes_win[-DI_BETA_REF_BARS:], closes_di[-DI_BETA_REF_BARS:])
            _di_coint_cache["date"] = today
            _di_coint_cache["is_coint"] = bool(pval < 0.05)
            _di_coint_cache["pvalue"] = pval
        except Exception:
            pass

    rho_status = get_rho_status(current_rho)
    beta_status_d = get_beta_status(beta_delta_pct)
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2)

    # ── History ───────────────────────────────────────────────────────
    n_z = len(z_arr)
    history = _build_history(times_win[-n_z:], z_arr, spread_arr[-n_z:])

    # Force signal from Kalman Z
    signal = _get_di_signal(current_z)

    now = datetime.now()
    _di_cache = {
        "current_z": round(current_z, 3),
        "current_rho": round(current_rho, 3),
        "half_life": round(half_life, 2) if half_life != float("inf") else 0.0,
        "signal": signal,
        "strength": round(strength, 1),
        "beta_ols": round(float(beta_current), 4),
        "beta_ref_20d": round(float(beta_ref_20d), 4),
        "beta_delta_pct": round(beta_delta_pct, 2),
        "beta_prev": round(float(_di_beta_state["previous_beta"]), 4),
        "beta_change_pct": round(beta_change_pct, 2),
        "beta_unstable": _di_beta_state["unstable"],
        "coint_eg": {
            "is_coint": _di_coint_cache["is_coint"],
            "pvalue": round(_di_coint_cache["pvalue"], 4),
        },
        "johansen_gate": {
            "open": joh_open,
            "trace_ratio": joh_ratio,
            "conviction": joh_conv,
            "joh_beta": round(float(joh_beta), 4) if joh_beta is not None else None,
        },
        "regime_health": {
            "rho": {
                "value": round(current_rho, 3),
                "status": rho_status["label"],
                "action": rho_status["action"],
                "color": rho_status["color"],
                "level": rho_status["level"],
            },
            "beta": {
                "current": round(float(beta_current), 4),
                "ref_20d": round(float(beta_ref_20d), 4),
                "delta_pct": round(beta_delta_pct, 2),
                "status": beta_status_d["label"],
                "action": beta_status_d["action"],
                "color": beta_status_d["color"],
                "level": beta_status_d["level"],
            },
            "safe_to_trade": safe_to_trade,
        },
        "history": history,
        "last_update": now.strftime("%H:%M:%S"),
        "last_update_iso": now.isoformat(timespec="seconds"),
        "meta": {
            "version": f"di_{method_label}",
            "symbol_a": SYMBOL_A,
            "symbol_b": DI_SYMBOL,
            "beta": round(float(beta_current), 4),
            "kalman_q": DI_KALMAN_Q,
            "kalman_r": DI_KALMAN_R,
            "kalman_w": DI_KALMAN_W,
            "timeframe": TF_NAMES.get(TIMEFRAME, str(TIMEFRAME)),
        },
        "error": None,
    }
    _di_cache_ts = time.time()
    return _di_cache


@app.get("/health")
def health():
    connected = connect_mt5()
    info = mt5.terminal_info() if connected else None
    return {
        "mt5_connected": connected,
        "terminal_name": info.name if info else None,
        "terminal_path": info.path if info else None,
        "configured_path": MT5_PATH or "(automatico)",
        "symbol_a": SYMBOL_A,
        "symbol_b": SYMBOL_B,
        "di_symbol": DI_SYMBOL,
    }


@app.get("/api/performance")
def get_performance():
    try:
        return _trade_engine.get_performance(limit=50)
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/gex-walls")
def get_gex_walls():
    import json
    try:
        cache_path = os.path.join("gex", "data", "win_walls_cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("walls", [])
    except Exception as e:
        print(f"Erro ao ler walls localmente: {e}")
    return []



# ─── Multi-day History Endpoint ──────────────────────────────────────────────

_hist_cache: dict = {}
_hist_cache_ts: float = 0.0
_hist_cache_days: int = 0

@app.get("/api/history")
def history_endpoint(days: int = 30):
    """Multi-day z-score history (Kalman + OLS + DI).
    
    Returns session-filtered bars for the last N trading days.
    Each bar has: date, bar_time, z (Kalman), z_v1 (OLS), z_di (DI).
    """
    global _hist_cache, _hist_cache_ts, _hist_cache_days

    # Cache for 30s (heavier computation)
    if time.time() - _hist_cache_ts < 30 and _hist_cache and _hist_cache_days == days:
        return _hist_cache

    if not connect_mt5():
        return {"error": "MT5 não disponível.", "history": [], "days": days}

    try:
        # M5 bars: ~108 bars/session day (9:20-18:20), fetch extra for window warmup
        bars_per_day = 108
        bars_needed = max(days * bars_per_day + WINDOW + 50, KALMAN_BURN_IN)

        # Fetch WIN, WDO, DI
        closes_a, times_a = fetch_bars(SYMBOL_A, bars_needed)
        closes_b, times_b = fetch_bars(SYMBOL_B, bars_needed)
        closes_di, times_di = fetch_bars(DI_SYMBOL, bars_needed)

        if closes_a is None or closes_b is None:
            return {"error": "Sem dados WIN/WDO.", "history": [], "days": days}

        min_len = min(len(closes_a), len(closes_b))
        ac = closes_a[-min_len:]
        bc = closes_b[-min_len:]
        tc = times_a[-min_len:]

        # --- Kalman z-scores ---
        kf = KalmanBetaFilter(initial_beta=BETA_INITIAL, trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
        kf_spreads = []
        for y, x in zip(ac, bc):
            _, spread_t, _ = kf.update(float(y), float(x))
            kf_spreads.append(spread_t)
        z_kalman = KalmanBetaFilter.rolling_zscore(kf_spreads, window=WDO_KALMAN_W)

        # --- OLS z-scores ---
        beta_ols_val = beta_state["current_beta"]
        _, z_ols, _ = calc_zscore(ac, bc, beta=beta_ols_val, max_bars=min_len)

        # --- DI z-scores (Kalman) ---
        z_di_map = {}
        if closes_di is not None:
            min_di = min(len(ac), len(closes_di))
            di_c = closes_di[-min_di:]
            di_t = times_di[-min_di:]
            win_for_di = ac[-min_di:]

            # DI Kalman filter
            kf_di = KalmanBetaFilter(
                initial_beta=DI_BETA_INITIAL,
                trans_cov=DI_KALMAN_Q,
                obs_cov=DI_KALMAN_R,
            )
            di_spreads = []
            for y, x in zip(win_for_di, di_c):
                _, spread_t, _ = kf_di.update(float(y), float(x))
                di_spreads.append(spread_t)
            z_di_arr = KalmanBetaFilter.rolling_zscore(di_spreads, window=DI_KALMAN_W)

            for i, t in enumerate(di_t):
                local_ts = int(t) + TIME_OFFSET
                z_di_map[local_ts] = round(float(z_di_arr[i]), 3) if i < len(z_di_arr) else 0.0

        # --- NWE for history ---
        nwe_line, nwe_u, nwe_l, nwe_is_up = calc_nwe_with_bands(
            ac, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
        )

        # --- Build history with session filter ---
        n = len(z_kalman)
        ols_offset = len(z_ols) - n  # align arrays
        nwe_offset = len(nwe_line) - n

        entries = []
        for i in range(n):
            local_ts = int(tc[i + (len(tc) - n)]) + TIME_OFFSET
            dt = datetime.fromtimestamp(local_ts)
            t_min = dt.hour * 60 + dt.minute

            if not (SESSION_START <= t_min <= SESSION_END):
                continue

            ols_idx = i + ols_offset
            z_ols_val = round(float(z_ols[ols_idx]), 3) if 0 <= ols_idx < len(z_ols) else 0.0
            z_di_val = z_di_map.get(local_ts, None)

            win_idx = i + (len(tc) - n)
            win_val = float(ac[win_idx]) if 0 <= win_idx < len(ac) else 0.0

            entry = {
                "date": dt.strftime("%Y-%m-%d"),
                "bar_time": dt.strftime("%H:%M"),
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "z": round(float(z_kalman[i]), 3),
                "z_v1": z_ols_val,
                "z_di": z_di_val,
                "win_price": win_val,
            }
            
            nwe_idx = i + nwe_offset
            if 0 <= nwe_idx < len(nwe_line):
                nv = float(nwe_line[nwe_idx])
                nu = float(nwe_u[nwe_idx])
                nl = float(nwe_l[nwe_idx])
                n_up = bool(nwe_is_up[nwe_idx])
                
                envW = nu - nv
                PROX_PCT = 0.10
                npu = nu - (2 * envW) * PROX_PCT
                npl = nl + (2 * envW) * PROX_PCT
                
                entry["nwe"] = round(nv, 2)
                entry["nweUpper"] = round(nu, 2)
                entry["nweLower"] = round(nl, 2)
                entry["nweProxUpper"] = round(npu, 2)
                entry["nweProxLower"] = round(npl, 2)
                entry["isUp"] = n_up
                entry["is_up"] = n_up

            entries.append(entry)

        # Get unique trading days
        trading_days = sorted(set(e["date"] for e in entries))

        result = {
            "history": entries,
            "days_requested": days,
            "days_available": len(trading_days),
            "trading_days": trading_days,
            "total_bars": len(entries),
        }

        _hist_cache = result
        _hist_cache_ts = time.time()
        _hist_cache_days = days

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "history": [], "days": days}


# ─── B3 Order Flow / RTD Endpoints ───────────────────────────────────────────
from fastapi import Query

def calculate_directional_efficiency():
    """Calculate the Daily Directional Efficiency (Player Price Influence) for WIN.
    
    Formula: (sum(dPrice * dNet) / sum(|dPrice * dNet|)) * 100
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect("trades.db", timeout=5.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT win_price, flow_json 
            FROM bar_history 
            WHERE date_str = ? 
            ORDER BY timestamp ASC
        """, (today_str,))
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        print(f"[ERROR calculate_directional_efficiency] {e}")
        return {"WIN": {}}

    if len(rows) < 2:
        return {"WIN": {}}

    # Initialize calculations
    efficiency = {"WIN": {}}
    
    # We will compute changes: dPrice = Price_t - Price_{t-1} and dNet = Net_t - Net_{t-1}
    prev_prices = {"WIN": None}
    prev_nets = {
        "WIN": {b: None for b in _broker_list}
    }
    
    # Cumulative numerator and denominator per broker per symbol
    stats = {
        "WIN": {b: {"num": 0.0, "den": 0.0} for b in _broker_list}
    }

    import json
    for r in rows:
        win_price = r["win_price"]
        flow_json = r["flow_json"]
        
        if not flow_json or win_price is None:
            continue
            
        try:
            flow_data = json.loads(flow_json)
        except Exception:
            continue
            
        sym = "WIN"
        price = win_price
        
        # Check if we have previous price
        if prev_prices[sym] is not None:
            dPrice = price - prev_prices[sym]
        else:
            dPrice = 0.0
            
        # Process brokers
        sym_flow = flow_data.get(sym, {})
        for b in _broker_list:
            b_metrics = sym_flow.get(b, {})
            if isinstance(b_metrics, dict):
                net = b_metrics.get("net", None)
            elif isinstance(b_metrics, (int, float)):
                net = b_metrics
            else:
                net = None
                
            if net is None:
                continue
                
            prev_net = prev_nets[sym][b]
            if prev_net is not None:
                dNet = net - prev_net
            else:
                dNet = 0.0
                
            # If both changes are valid, accumulate
            if prev_prices[sym] is not None and prev_net is not None:
                product = dPrice * dNet
                stats[sym][b]["num"] += product
                stats[sym][b]["den"] += abs(product)
                
            # Update prev net
            prev_nets[sym][b] = net
            
        # Update prev price
        prev_prices[sym] = price

    # Compute final scores
    for b in _broker_list:
        den = stats["WIN"][b]["den"]
        num = stats["WIN"][b]["num"]
        if den > 0:
            eff = (num / den) * 100.0
            efficiency["WIN"][b] = round(eff, 1)
        else:
            efficiency["WIN"][b] = 0.0
                
    return efficiency

def calculate_flow_acceleration(efficiency=None):
    """Calculate the Flow Acceleration Index (IAF) based on Kyle's Lambda (Lots per 100 points) for WIN.
    
    Returns a dictionary: {"WIN": float} containing scores from -100 to 100.
    """
    if efficiency is None:
        efficiency = calculate_directional_efficiency()
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect("trades.db", timeout=5.0)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT win_price, flow_json 
            FROM bar_history 
            WHERE date_str = ? 
            ORDER BY timestamp ASC
        """, (today_str,))
        rows = c.fetchall()
        conn.close()
    except Exception as e:
        print(f"[ERROR calculate_flow_acceleration] {e}")
        return {"WIN": 0.0}

    # Convert to a list of dicts to make it mutable and allow appending the current open bar
    bars_list = []
    for r in rows:
        bars_list.append({
            "win_price": r["win_price"],
            "flow_json": r["flow_json"]
        })

    # Append the current active open bar to the end of the bars list for real-time responsiveness
    if connect_mt5():
        closes_now, _ = fetch_bars(SYMBOL_A, 1)
        if closes_now is not None and len(closes_now) > 0:
            price_now = float(closes_now[-1])
            import json
            current_flow = _get_current_flow_data()
            flow_json_now = json.dumps(current_flow)
            bars_list.append({
                "win_price": price_now,
                "flow_json": flow_json_now
            })

    # We need at least 2 bars to calculate any price movement/flow change
    if len(bars_list) < 2:
        return {"WIN": 0.0}

    accelerator = {"WIN": 0.0}
    
    # 1. Identify dominant players per symbol (DDE >= 40%)
    dominant_players = {"WIN": []}
    sym_eff = efficiency.get("WIN", {})
    for b, eff in sym_eff.items():
        if eff >= 40.0:
            dominant_players["WIN"].append((b, eff / 100.0))  # (broker, weight)
                
    # 2. Iterate and compute short-term variables
    M = min(5, len(bars_list) - 1)
    
    import json
    sym = "WIN"
    doms = dominant_players[sym]
    if doms:
        # Price change over the last M bars
        price_curr = bars_list[-1]["win_price"]
        price_prev = bars_list[-1 - M]["win_price"]
        
        if price_curr is not None and price_prev is not None:
            dPrice = abs(price_curr - price_prev)
            tick_unit = 100.0
            
            # Total absolute net change of ALL active brokers over the last M bars
            total_vol = 0.0
            prev_nets_all = {}
            for idx in range(len(bars_list) - M - 1, len(bars_list)):
                r = bars_list[idx]
                flow_json = r["flow_json"]
                if not flow_json:
                    continue
                try:
                    flow_data = json.loads(flow_json).get(sym, {})
                except Exception:
                    continue
                    
                for b in _broker_list:
                    val_b = flow_data.get(b, {})
                    net = val_b.get("net", None) if isinstance(val_b, dict) else val_b
                    if net is not None:
                        if b in prev_nets_all:
                            total_vol += abs(net - prev_nets_all[b])
                        prev_nets_all[b] = net
                        
            # If total_vol is 0, LotsPer100Pts cannot be calculated
            if total_vol > 0:
                # Lots required to move the price by 1 tick_unit
                if dPrice == 0:
                    lots_per_unit = float("inf")
                else:
                    lots_per_unit = total_vol / (dPrice / tick_unit)
                    
                # 3. Calculate Instantaneous Pressure of Dominant Players (last bar)
                flow_curr = json.loads(bars_list[-1]["flow_json"]).get(sym, {}) if bars_list[-1]["flow_json"] else {}
                flow_prev = json.loads(bars_list[-2]["flow_json"]).get(sym, {}) if bars_list[-2]["flow_json"] else {}
                
                dom_pressure = 0.0
                for b, weight in doms:
                    c_val = flow_curr.get(b, {})
                    p_val = flow_prev.get(b, {})
                    net_curr = c_val.get("net", 0) if isinstance(c_val, dict) else c_val
                    net_prev = p_val.get("net", 0) if isinstance(p_val, dict) else p_val
                    dom_pressure += (net_curr - net_prev) * weight
                    
                # 4. Compute IAF
                if lots_per_unit != float("inf"):
                    scale_factor = 5.0  # multiplier to make the gauge responsive
                    iaf = (dom_pressure / lots_per_unit) * 100.0 * scale_factor
                    iaf = max(-100.0, min(100.0, iaf))
                    
                    accelerator["WIN"] = round(iaf, 1)
                    
    return accelerator

@app.get("/api/restart")
@app.post("/api/restart")
def restart_server():
    import os
    import threading
    print("[INFO] Comando de reinicialização recebido pelo endpoint API. Encerrando processo...")
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"ok": True, "message": "Reiniciando servidor via PM2..."}

@app.get("/api/flow/realtime")
def get_realtime_flow():
    return list(_realtime_flow_cache)

@app.get("/api/flow")
def get_flow():
    eff_data = calculate_directional_efficiency()
    return {
        "brokers": _broker_list,
        "flow": _broker_flow,
        "history": _flow_history_bars,
        "efficiency": eff_data,
        "accelerator": calculate_flow_acceleration(efficiency=eff_data),
        "last_update": {
            "WIN": datetime.fromtimestamp(_last_flow_update["WIN"]).strftime("%H:%M:%S") if _last_flow_update["WIN"] > 0 else "SIMULADO"
        }
    }

@app.post("/api/flow/inject-history")
async def inject_flow_history(request: Request):
    """Debug: inject simulated flow history for chart testing."""
    global _flow_history_bars
    data = await request.json()
    if isinstance(data, list):
        _flow_history_bars = data
        if data:
            last = data[-1]
            sym = "WIN"
            if sym in last:
                for b in _broker_list:
                    if b in last[sym]:
                        val = last[sym][b]
                        if isinstance(val, dict):
                            _broker_flow[sym][b]["net"] = val.get("net", 0)
                            _broker_flow[sym][b]["buy"] = val.get("buy", 0)
                            _broker_flow[sym][b]["sell"] = val.get("sell", 0)
                        else:
                            _broker_flow[sym][b]["net"] = val
                            _broker_flow[sym][b]["buy"] = 0
                            _broker_flow[sym][b]["sell"] = 0
        return {"ok": True, "bars": len(_flow_history_bars)}
    return {"ok": False, "error": "expected list"}

@app.get("/api/flow/update")
@app.post("/api/flow/update")
def update_flow(
    symbol: str = Query(..., description="WIN"),
    broker: str = Query(..., description="Nome da corretora"),
    net: int = Query(..., description="Saldo líquido do corretor"),
    avg: float = Query(0.0, description="Preço médio (opcional)"),
    buy: int = Query(0, description="Volume de compra (opcional)"),
    sell: int = Query(0, description="Volume de venda (opcional)"),
):
    sym = symbol.upper()
    brk = broker.upper()
    
    if sym != "WIN":
        return {"error": "Símbolo inválido. Apenas WIN é suportado."}
        
    if net < -1000000:
        return {"status": "ignored", "reason": "Excel error code filtered."}
    
    if brk not in _broker_flow[sym]:
        _broker_flow[sym][brk] = {"id": str(len(_broker_flow[sym])), "net": 0, "avg": 0.0, "vol": 0, "buy": 0, "sell": 0}
        if brk not in _broker_list:
            _broker_list.append(brk)
            
    _broker_flow[sym][brk]["net"] = net
    if avg > 0:
        _broker_flow[sym][brk]["avg"] = avg
    if buy > 0:
        _broker_flow[sym][brk]["buy"] = buy
    if sell > 0:
        _broker_flow[sym][brk]["sell"] = sell
        
    _broker_flow[sym][brk]["vol"] = _broker_flow[sym][brk]["buy"] + _broker_flow[sym][brk]["sell"]
    _last_flow_update[sym] = time.time()
    
    return {"status": "success", "broker": brk, "symbol": sym, "net": net}

# ─── Startup ─────────────────────────────────────────────────────────────────
# NOTE: HMM background thread DISABLED — no longer used in this project.
# It was calling mt5.initialize() from a background thread, which is NOT
# thread-safe and caused Python segfaults (crashing all Python on the machine).
# hmm.start()

if __name__ == "__main__":
    import uvicorn
    print("=" * 55)
    print("  WIN×WDO+DI Regime Monitor — Servidor local")
    print("  WDO:    http://localhost:8080/api/regime")
    print("  DI:     http://localhost:8080/api/di-regime")
    print("  Fluxo:  http://localhost:8080/api/flow")
    print("  Saude:  http://localhost:8080/health")
    print("  Docs:   http://localhost:8080/docs")
    print("=" * 55)
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)
