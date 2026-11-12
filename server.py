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
    connect_mt5, fetch_bars, align_series_by_time, beta_state, save_beta_ultimo, load_beta_ultimo,
)
from core.profit_statarb_engine import (
    fetch_profit_m5_series,
    align_profit_series_with_ffill,
    get_profit_day_flow_bundle,
    format_flow_score_for_frontend,
    format_iaf_for_frontend,
)
from core.signals import (
    calc_beta_ols, calc_half_life, calc_zscore,
    get_signal, get_rho_status, get_beta_status,
    calc_nwe_with_bands,
    _coint_cache,
)
from core.kalman_filter import KalmanBetaFilter
from core.trade_engine import TradeEngine, calc_wall_tp_sl
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
_realtime_factors_cache = deque(maxlen=10000)
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
            buy_sum += (snap_end["flow"].get(b, {}).get("buy", 0) - snap_start["flow"].get(b, {}).get("buy", 0))
            sell_sum += (snap_end["flow"].get(b, {}).get("sell", 0) - snap_start["flow"].get(b, {}).get("sell", 0))
        fl = buy_sum - sell_sum
        sum_fl += fl
        sum_abs_fl += abs(fl)
        
    if sum_abs_fl > 0:
        return sum_fl / sum_abs_fl
    return 0.0

def _calculate_window_factors(snapshots, window_seconds):
    P = window_seconds // 5
    if len(snapshots) < P + 1:
        return 0.0, 0.0, 0.0, 0.0
        
    latest = snapshots[-1]
    start = snapshots[-1 - P]
    
    # 1. FLN (Fluxo Normalizado)
    buy_sum = 0
    sell_sum = 0
    for b in _broker_list:
        buy_sum += (latest["flow"].get(b, {}).get("buy", 0) - start["flow"].get(b, {}).get("buy", 0))
        sell_sum += (latest["flow"].get(b, {}).get("sell", 0) - start["flow"].get(b, {}).get("sell", 0))
    
    fl = buy_sum - sell_sum
    va = buy_sum + sell_sum
    fln = fl / va if va > 0 else 0.0
    
    # 2. PERS (Persistência)
    pers = calculate_persistence(snapshots, P)
    
    # 3. CONC_DIR (Concentração Direcionada)
    broker_nets = []
    for b in _broker_list:
        b_buy = latest["flow"].get(b, {}).get("buy", 0) - start["flow"].get(b, {}).get("buy", 0)
        b_sell = latest["flow"].get(b, {}).get("sell", 0) - start["flow"].get(b, {}).get("sell", 0)
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
            j_buy += (snap_j["flow"].get(b, {}).get("buy", 0) - snap_prev["flow"].get(b, {}).get("buy", 0))
            j_sell += (snap_j["flow"].get(b, {}).get("sell", 0) - snap_prev["flow"].get(b, {}).get("sell", 0))
            
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
        
    return fln, pers, conc_dir, abs_dir

def _calculate_window_score(snapshots, window_seconds):
    fln, pers, conc_dir, abs_dir = _calculate_window_factors(snapshots, window_seconds)
    # ScoreFluxo_t = 100 * (0.20 * FLN_t + 0.40 * PERS_t + 0.30 * CONC_DIR_t + 0.10 * ABS_DIR_t)
    return 100.0 * (0.20 * fln + 0.40 * pers + 0.30 * conc_dir + 0.10 * abs_dir)

def _calculate_combined_factors(snapshots):
    if len(snapshots) < 2:
        return 0.0, 0.0, 0.0, 0.0
    
    fln_5s, pers_5s, conc_5s, abs_5s = _calculate_window_factors(snapshots, 5)
    fln_15s, pers_15s, conc_15s, abs_15s = _calculate_window_factors(snapshots, 15)
    fln_60s, pers_60s, conc_60s, abs_60s = _calculate_window_factors(snapshots, 60)
    
    fln = 0.50 * fln_5s + 0.30 * fln_15s + 0.20 * fln_60s
    pers = 0.50 * pers_5s + 0.30 * pers_15s + 0.20 * pers_60s
    conc_dir = 0.50 * conc_5s + 0.30 * conc_15s + 0.20 * conc_60s
    abs_dir = 0.50 * abs_5s + 0.30 * abs_15s + 0.20 * abs_60s
    
    return fln, pers, conc_dir, abs_dir

def _calculate_combined_flow_score(snapshots):
    fln, pers, conc_dir, abs_dir = _calculate_combined_factors(snapshots)
    return 100.0 * (0.20 * fln + 0.40 * pers + 0.30 * conc_dir + 0.10 * abs_dir)

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
    global _realtime_flow_cache, _realtime_factors_cache
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
        
        val_norm = score / 100.0
        _realtime_factors_cache.append({
            "time": int(curr_time),
            "fln": val_norm,
            "pers": val_norm,
            "conc_dir": val_norm,
            "abs_dir": val_norm
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
                _realtime_factors_cache.clear()
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
            fln, pers, conc_dir, abs_dir = _calculate_combined_factors(_raw_flow_snapshots)
            score = 100.0 * (0.20 * fln + 0.40 * pers + 0.30 * conc_dir + 0.10 * abs_dir)
            
            _realtime_factors_cache.append({
                "time": int(current_time),
                "fln": fln,
                "pers": pers,
                "conc_dir": conc_dir,
                "abs_dir": abs_dir
            })
            
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
import concurrent.futures

_single_mt5_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="mt5_single")
_firebase_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="firebase_io")

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Force all sync endpoints & asyncio.to_thread calls onto a single OS thread so MetaTrader5 C++ DLL never segfaults
    try:
        asyncio.get_running_loop().set_default_executor(_single_mt5_executor)
    except Exception:
        pass
    try:
        import anyio.to_thread
        anyio.to_thread.current_default_thread_limiter().total_tokens = 1
    except Exception:
        pass

    # Startup
    if firebase_initialized:
        asyncio.create_task(firebase_push_loop())
    
    _seed_realtime_flow()  # Pre-populate real-time flow indicator cache for today
    # _seed_flow_history()  # Pre-populate flow chart with full-day simulated data
    asyncio.create_task(flow_snapshot_loop())
    
    # Run backfill on the single MT5 worker thread
    asyncio.create_task(asyncio.to_thread(do_backfill_if_empty))
    
    yield
    # Shutdown

app = FastAPI(title="WIN×WDO Regime Monitor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

def _sync_firebase_dash(r_v2, r_di, perf, compass_snap=None):
    ref = fdb.reference('dashboard')
    payload = {
        'regime': r_v2,
        'di_regime': r_di,
        'performance': perf,
    }
    if compass_snap is not None:
        payload['compass'] = compass_snap
    ref.set(payload)

def _sync_firebase_hist(hist_list):
    ref_hist = fdb.reference('history_30d')
    ref_hist.set(hist_list)

async def firebase_push_loop():
    print("[INFO] Firebase Sync Loop iniciado.")
    last_hist_update = 0
    last_dash_update = 0
    while True:
        try:
            if firebase_initialized:
                r_v2 = await asyncio.to_thread(regime_v2)
                r_di = await asyncio.to_thread(di_regime)
                perf = await asyncio.to_thread(get_performance)
                
                current_time = time.time()
                
                # Check for immediate push condition
                action_v2 = r_v2.get("trade_engine", {}).get("action", "WAIT")
                push_immediate = action_v2 not in ("WAIT", "HOLDING", "ANOMALY")
                
                # Push para RTDB (dashboard live) a cada 15 segundos ou imediatamente se houver trade
                if push_immediate or current_time - last_dash_update >= 15:
                    compass_snap = await asyncio.to_thread(get_compass_etapa1, None, True)
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(_firebase_executor, _sync_firebase_dash, r_v2, r_di, perf, compass_snap)
                    last_dash_update = current_time

                # Push history_30d a cada 5 minutos (300 segundos) para economizar banda
                if current_time - last_hist_update > 300:
                    hist = await asyncio.to_thread(history_endpoint, 30)
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(_firebase_executor, _sync_firebase_hist, hist.get("history", []))
                    last_hist_update = current_time

        except Exception as e:
            print(f"[AVISO] Erro no sync do Firebase: {e}")
        await asyncio.sleep(2.5)  # Envia live a cada 2.5s

import threading
_trade_engine = TradeEngine(db_path="trades.db")
_cache: dict = {}
_cache_ts: float = 0.0
_v2_cache: dict = {}
_v2_cache_ts: float = 0.0
from core.mt5_client import mt5_lock as _mt5_lock
_v2_lock = _mt5_lock
_di_lock = _mt5_lock
_hist_lock = _mt5_lock
_flow_api_cache: dict = {}
_flow_api_cache_ts: float = 0.0

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
    "last_check_i": -999, "last_check_ts": 0, "conviction": "N/A",
}
_joh_di_state = {
    "gate_open": False, "trace_ratio": 0.0, "joh_beta": None,
    "last_check_i": -999, "last_check_ts": 0, "conviction": "N/A",
}


def _compute_johansen_gate(closes_a, closes_b, state, bar_count, last_bar_ts=None):
    """Recompute Johansen cointegration gate if enough bars/time elapsed.
    Modifies state in-place. Returns (gate_open, trace_ratio, conviction, joh_beta).
    """
    should_recheck = False
    if last_bar_ts is not None and last_bar_ts > 0:
        if last_bar_ts - state.get("last_check_ts", 0) >= JOH_RECHECK_BARS * 300:
            should_recheck = True
    elif bar_count - state["last_check_i"] >= JOH_RECHECK_BARS:
        should_recheck = True

    if should_recheck and len(closes_a) >= JOH_WINDOW:
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
            if last_bar_ts is not None:
                state["last_check_ts"] = int(last_bar_ts)
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
    conn = sqlite3.connect("trades.db", timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS bar_history (
            timestamp INTEGER PRIMARY KEY,
            date_str TEXT,
            bar_time TEXT,
            win_price REAL,
            wdo_price REAL,
            di_price REAL,
            spread_wdo REAL,
            spread_di REAL,
            z_wdo REAL,
            z_di REAL,
            nwe_center REAL,
            nwe_upper REAL,
            nwe_lower REAL,
            nwe_is_up INTEGER,
            flow_json TEXT
        )
    ''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_bar_history_date ON bar_history(date_str, timestamp)")
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

ANCHOR_2026_TS = int(datetime(2026, 1, 2, 0, 0).timestamp()) - TIME_OFFSET


def _evaluate_bar_setups(
    orig_z_wdo: float,
    orig_z_di: float,
    win_val: float | None,
    nv: float | None,
    nu: float | None,
    nl: float | None,
    n_is_up: bool | None,
    t_min: int,
    active_walls: list | None = None,
    is_closed_bar: bool = True,
) -> dict:
    """
    Canonical evaluation of the 3 Stat-Arb setups (WDO_NWE, DI_NWE, CONSENSO WDO+DI)
    on a single M5 bar. Marks signals ONLY when the full setup triggers an entry
    on a closed bar (Z-score + NWE contra-trend & band proximity + GEX Wall RR/SL).
    """
    npu = npl = npu_10 = npl_10 = None
    bw = 0.0
    if nv is not None and nu is not None and nl is not None and nu > nl:
        bw = float(nu - nl)
        npu = float(nu - bw * 0.15)
        npl = float(nl + bw * 0.15)
        npu_10 = float(nu - bw * 0.10)
        npl_10 = float(nl + bw * 0.10)

    sig_wdo = 0
    sig_di = 0
    sig_cons = 0
    wall_tp = None
    wall_sl = None
    wall_tp_pts = None
    wall_sl_pts = None

    in_entry_window = (545 <= t_min <= 1005)  # 09:05 .. 16:45
    no_anomaly = (abs(orig_z_wdo) < 4.0 and abs(orig_z_di) < 4.0)

    if is_closed_bar and in_entry_window and no_anomaly and win_val is not None and n_is_up is not None and bw > 0:
        buy_nwe_15 = (not n_is_up) and (win_val <= npl)
        sell_nwe_15 = bool(n_is_up) and (win_val >= npu)
        buy_nwe_10 = (not n_is_up) and (win_val <= npl_10)
        sell_nwe_10 = bool(n_is_up) and (win_val >= npu_10)

        if orig_z_wdo <= -1.4 and buy_nwe_15:
            sig_wdo = -1
        elif orig_z_wdo >= 1.4 and sell_nwe_15:
            sig_wdo = 1

        if orig_z_di <= -2.2 and buy_nwe_10:
            sig_di = -1
        elif orig_z_di >= 2.2 and sell_nwe_10:
            sig_di = 1

        cons_buy = ((orig_z_wdo <= -1.8 and orig_z_di <= -1.2) or (orig_z_di <= -2.2 and orig_z_wdo <= -1.2)) and buy_nwe_15
        cons_sell = ((orig_z_wdo >= 1.8 and orig_z_di >= 1.2) or (orig_z_di >= 2.2 and orig_z_wdo >= 1.2)) and sell_nwe_15
        if cons_buy:
            sig_cons = -1
        elif cons_sell:
            sig_cons = 1

        if (sig_wdo != 0 or sig_di != 0 or sig_cons != 0) and active_walls is not None:
            sig_val = sig_cons if sig_cons != 0 else (sig_wdo if sig_wdo != 0 else sig_di)
            dir_str = "BUY" if sig_val < 0 else "SELL"
            tp_w, sl_w, tp_d, sl_d = calc_wall_tp_sl(dir_str, float(win_val), active_walls)
            if sl_d <= 300.0 and (tp_d / max(sl_d, 1.0)) >= 1.4:
                wall_tp = tp_w
                wall_sl = sl_w
                wall_tp_pts = tp_d
                wall_sl_pts = sl_d
            else:
                sig_wdo = 0
                sig_di = 0
                sig_cons = 0

    return {
        "nweProxUpper": round(npu, 2) if npu is not None else None,
        "nweProxLower": round(npl, 2) if npl is not None else None,
        "z_raw_wdo": orig_z_wdo if sig_wdo != 0 else 0.0,
        "z_raw_di": orig_z_di if sig_di != 0 else 0.0,
        "sig_wdo": sig_wdo,
        "sig_di": sig_di,
        "sig_cons": sig_cons,
        "cons_wdo_sig": sig_cons,
        "cons_di_sig": sig_cons,
        "wall_tp": wall_tp,
        "wall_sl": wall_sl,
        "wall_tp_pts": wall_tp_pts,
        "wall_sl_pts": wall_sl_pts,
    }


def simulate_day_statarb_trades(day_bars: list, active_walls: list | None = None) -> list:
    """
    Simulate the 3 Stat-Arb strategies (CONS, WDO_NWE, DI_NWE) on a single session's M5 bars
    using the exact audited 2026 rules. Returns both closed trades and currently open live trades.
    """
    if not day_bars:
        return []
    if active_walls is None:
        active_walls = get_gex_walls()

    now_epoch = int(time.time())
    strat_configs = [
        {"id": "CONS", "sig_key": "sig_cons", "be_act": 150.0, "wait_bars": 4},
        {"id": "WDO_NWE", "sig_key": "sig_wdo", "be_act": 150.0, "wait_bars": 4},
        {"id": "DI_NWE", "sig_key": "sig_di", "be_act": 200.0, "wait_bars": 4},
    ]

    all_trades = []
    for cfg in strat_configs:
        strat_id = cfg["id"]
        sig_key = cfg["sig_key"]
        be_act = cfg["be_act"]
        wait_bars = cfg["wait_bars"]
        pos = None
        cooldown_until = -1

        for i, b in enumerate(day_bars):
            bt = b.get("bar_time", "")
            d_str = b.get("date", "")
            tm = int(b.get("t_min", 0))
            px = float(b.get("win_price") or 0.0)
            hi = float(b.get("win_high") or px)
            lo = float(b.get("win_low") or px)
            zw = float(b.get("z") or 0.0)
            zd = float(b.get("z_di") or 0.0)
            raw_ts = int(b.get("timestamp") or 0)
            local_ts = raw_ts + TIME_OFFSET
            is_closed = (i < len(day_bars) - 1) or (raw_ts == 0) or (now_epoch >= (local_ts + 300))

            if pos is not None:
                d = pos["dir"]
                closed = False
                pnl_pts = 0.0
                exit_px = px
                exit_reason = ""
                if d == 1:
                    if lo <= pos["sl_px"]:
                        pnl_pts = pos["sl_px"] - pos["entry_px"]
                        exit_px = pos["sl_px"]
                        exit_reason = "STOP BE (+15p)" if pos["be_triggered"] else "STOP WALL"
                        closed = True
                    elif hi >= pos["tp_px"]:
                        pnl_pts = pos["tp_px"] - pos["entry_px"]
                        exit_px = pos["tp_px"]
                        exit_reason = "ALVO WALL"
                        closed = True
                    elif is_closed and ((strat_id == "WDO_NWE" and zw >= 0.2) or (strat_id == "DI_NWE" and zd >= 0.2) or (strat_id == "CONS" and zw >= 0.0 and zd >= 0.0)) and (px - pos["entry_px"]) >= 200.0:
                        pnl_pts = px - pos["entry_px"]
                        exit_px = px
                        exit_reason = "ALVO Z-REV"
                        closed = True
                    elif be_act > 0 and (hi - pos["entry_px"]) >= be_act and pos["sl_px"] < pos["entry_px"]:
                        pos["sl_px"] = pos["entry_px"] + 15.0
                        pos["be_triggered"] = True
                        pos["be_time"] = bt
                        pos["be_stop_px"] = pos["sl_px"]
                        pos["be_trig_px"] = pos["entry_px"] + be_act
                else:
                    if hi >= pos["sl_px"]:
                        pnl_pts = pos["entry_px"] - pos["sl_px"]
                        exit_px = pos["sl_px"]
                        exit_reason = "STOP BE (+15p)" if pos["be_triggered"] else "STOP WALL"
                        closed = True
                    elif lo <= pos["tp_px"]:
                        pnl_pts = pos["entry_px"] - pos["tp_px"]
                        exit_px = pos["tp_px"]
                        exit_reason = "ALVO WALL"
                        closed = True
                    elif is_closed and ((strat_id == "WDO_NWE" and zw <= -0.2) or (strat_id == "DI_NWE" and zd <= -0.2) or (strat_id == "CONS" and zw <= 0.0 and zd <= 0.0)) and (pos["entry_px"] - px) >= 200.0:
                        pnl_pts = pos["entry_px"] - px
                        exit_px = px
                        exit_reason = "ALVO Z-REV"
                        closed = True
                    elif be_act > 0 and (pos["entry_px"] - lo) >= be_act and pos["sl_px"] > pos["entry_px"]:
                        pos["sl_px"] = pos["entry_px"] - 15.0
                        pos["be_triggered"] = True
                        pos["be_time"] = bt
                        pos["be_stop_px"] = pos["sl_px"]
                        pos["be_trig_px"] = pos["entry_px"] - be_act

                if not closed and is_closed and tm >= 17 * 60 + 40:
                    pnl_pts = (px - pos["entry_px"]) * d
                    exit_px = px
                    exit_reason = "FECHAMENTO 17:40"
                    closed = True

                if closed:
                    all_trades.append({
                        "id": f"{d_str}_{pos['entry_time']}_{strat_id}",
                        "date": d_str,
                        "strat": strat_id,
                        "strategy_id": strat_id,
                        "dir": "BUY" if d == 1 else "SELL",
                        "direction": "COMPRA" if d == 1 else "VENDA",
                        "dir_num": d,
                        "entry_time": pos["entry_time"],
                        "exit_time": bt,
                        "entry_price": round(pos["entry_px"]),
                        "exit_price": round(exit_px),
                        "tp_price": round(pos["tp_px"]),
                        "sl_price": round(pos["sl_px"]),
                        "initial_sl_price": round(pos["init_sl_px"]),
                        "stop_price": round(pos["init_sl_px"]),
                        "tp_dist": round(abs(pos["tp_px"] - pos["entry_px"])),
                        "sl_dist": round(abs(pos["entry_px"] - pos["init_sl_px"])),
                        "be_triggered": pos["be_triggered"],
                        "be_time": pos["be_time"],
                        "be_stop_price": round(pos["be_stop_px"]) if pos["be_triggered"] else None,
                        "be_trigger_price": round(pos["be_trig_px"]) if pos["be_triggered"] else None,
                        "pnl_pts": round(pnl_pts),
                        "pts": round(pnl_pts),
                        "pnl_brl": round(pnl_pts * 0.4),
                        "brl_2c": round(pnl_pts * 0.4),
                        "reason": exit_reason,
                        "exit_reason": exit_reason,
                        "status": "FECHADA",
                    })
                    pos = None
                    cooldown_until = i + wait_bars
                continue

            if not is_closed or i <= cooldown_until or not (545 <= tm <= 930):
                continue

            sig_val = int(b.get(sig_key) or 0)
            if sig_val != 0 and px > 0:
                dir_num = 1 if sig_val < 0 else -1
                dir_str = "BUY" if dir_num == 1 else "SELL"
                tp_w, sl_w, tp_d, sl_d = calc_wall_tp_sl(dir_str, px, active_walls)
                if sl_d <= 300.0 and (tp_d / max(sl_d, 1.0)) >= 1.4:
                    pos = {
                        "dir": dir_num,
                        "entry_px": px,
                        "tp_px": tp_w,
                        "sl_px": sl_w,
                        "init_sl_px": sl_w,
                        "entry_time": bt,
                        "be_triggered": False,
                        "be_time": None,
                        "be_stop_px": None,
                        "be_trig_px": None,
                    }

        if pos is not None and day_bars:
            last_b = day_bars[-1]
            last_px = float(last_b.get("win_price") or pos["entry_px"])
            d = pos["dir"]
            live_pts = (last_px - pos["entry_px"]) * d
            all_trades.append({
                "id": f"{last_b.get('date', '')}_{pos['entry_time']}_{strat_id}",
                "date": last_b.get("date", ""),
                "strat": strat_id,
                "strategy_id": strat_id,
                "dir": "BUY" if d == 1 else "SELL",
                "direction": "COMPRA" if d == 1 else "VENDA",
                "dir_num": d,
                "entry_time": pos["entry_time"],
                "exit_time": last_b.get("bar_time", pos["entry_time"]),
                "entry_price": round(pos["entry_px"]),
                "exit_price": round(last_px),
                "tp_price": round(pos["tp_px"]),
                "sl_price": round(pos["sl_px"]),
                "initial_sl_price": round(pos["init_sl_px"]),
                "stop_price": round(pos["init_sl_px"]),
                "tp_dist": round(abs(pos["tp_px"] - pos["entry_px"])),
                "sl_dist": round(abs(pos["entry_px"] - pos["init_sl_px"])),
                "be_triggered": pos["be_triggered"],
                "be_time": pos["be_time"],
                "be_stop_price": round(pos["be_stop_px"]) if pos["be_triggered"] else None,
                "be_trigger_price": round(pos["be_trig_px"]) if pos["be_triggered"] else None,
                "pnl_pts": round(live_pts),
                "pts": round(live_pts),
                "pnl_brl": round(live_pts * 0.4),
                "brl_2c": round(live_pts * 0.4),
                "reason": "⏳ EM ABERTO (AO VIVO)",
                "exit_reason": "⏳ EM ABERTO (AO VIVO)",
                "status": "ABERTA",
            })

    return sorted(all_trades, key=lambda x: (x["entry_time"], x["strat"]))


def load_bar_history(days=30, active_walls=None):
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
        if active_walls is None:
            active_walls = get_gex_walls()
        history = []
        for i, r in enumerate(rows):
            dt_time = datetime.strptime(r["bar_time"], "%H:%M")
            t_min = dt_time.hour * 60 + dt_time.minute
            orig_z_wdo = round(float(r["z_wdo"] or 0.0), 3)
            orig_z_di = round(float(r["z_di"] or 0.0), 3)
            win_price = r["win_price"]
            
            nv = r["nwe_center"]
            nu = r["nwe_upper"]
            nl = r["nwe_lower"]
            n_up = bool(r["nwe_is_up"]) if "nwe_is_up" in r.keys() else None
            
            setup_eval = _evaluate_bar_setups(
                orig_z_wdo, orig_z_di, win_price, nv, nu, nl, n_up, t_min,
                active_walls=active_walls, is_closed_bar=True
            )
            
            flow_data = None
            if "flow_json" in r.keys() and r["flow_json"]:
                try:
                    flow_data = json.loads(r["flow_json"])
                except Exception:
                    pass
            
            item = {
                "i": i,
                "timestamp": int(r["timestamp"]),
                "z": orig_z_wdo,
                "z_di": orig_z_di,
                "spread": r["spread_wdo"],
                "bar_time": r["bar_time"],
                "date": r["date_str"],
                "t_min": t_min,
                "win_price": win_price,
                
                "nwe": round(float(nv), 2) if nv is not None else None,
                "nweUpper": round(float(nu), 2) if nu is not None else None,
                "nweLower": round(float(nl), 2) if nl is not None else None,
                "isUp": n_up,
                "is_up": n_up,
                
                "z_unfiltered_wdo": orig_z_wdo,
                "z_unfiltered_di": orig_z_di,
                "flow": flow_data,
            }
            item.update(setup_eval)
            history.append(item)
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
        time.sleep(2.0)
        history_endpoint(days=30)
        print("[OK] Backfill concluido diretamente via history_endpoint.")
    except Exception as e:
        print(f"[ERRO] Falha no backfill: {e}")

def _build_history(bar_times, z_arr, spread_arr, z_v1_arr=None, win_prices=None, nwe_data=None, di_map=None, active_walls=None):
    """Build filtered session history from bar data, including NWE and DI."""
    n = len(z_arr)
    v1_len = len(z_v1_arr) if z_v1_arr is not None else 0
    win_len = len(win_prices) if win_prices is not None else 0
    
    nwe_line, nwe_upper, nwe_lower, nwe_is_up = nwe_data if nwe_data else (None, None, None, None)
    nwe_len = len(nwe_line) if nwe_line is not None else 0
    bar_info = []
    now_epoch = int(time.time())
    for i in range(n):
        raw_ts = int(bar_times[i])
        local_ts = raw_ts + TIME_OFFSET
        dt = datetime.fromtimestamp(local_ts)
        t_min = dt.hour * 60 + dt.minute
        entry = {
            "timestamp": raw_ts,
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
            
        dt_key = entry["date"] + " " + entry["bar_time"]
        z_di_val = None
        if di_map:
            z_di_val = di_map.get(dt_key)
            if z_di_val is None:
                z_di_val = di_map.get(raw_ts)
            if z_di_val is None:
                z_di_val = di_map.get(local_ts)
        if z_di_val is None:
            z_di_val = bar_info[-1]["z_unfiltered_di"] if bar_info else 0.0
        entry["z_di"] = round(float(z_di_val), 3)
        
        orig_z_wdo = round(float(z_arr[i]), 3)
        orig_z_di_val = round(float(z_di_val), 3)
        
        nv = nu = nl = n_is_up = None
        if nwe_line is not None:
            nwe_idx = i - (n - nwe_len)
            if 0 <= nwe_idx < nwe_len:
                nv = float(nwe_line[nwe_idx])
                nu = float(nwe_upper[nwe_idx])
                nl = float(nwe_lower[nwe_idx])
                n_is_up = bool(nwe_is_up[nwe_idx])
                entry["nwe"] = round(nv, 2)
                entry["nweUpper"] = round(nu, 2)
                entry["nweLower"] = round(nl, 2)
                entry["isUp"] = n_is_up
                entry["is_up"] = n_is_up

        # A bar is closed if it is not the last bar OR its 5-minute window has already elapsed
        is_closed = (i < n - 1) or (now_epoch >= (local_ts + 300))
        setup_eval = _evaluate_bar_setups(
            orig_z_wdo, orig_z_di_val, win_val, nv, nu, nl, n_is_up, t_min,
            active_walls=active_walls, is_closed_bar=is_closed
        )
        entry["z_unfiltered_wdo"] = orig_z_wdo
        entry["z_unfiltered_di"] = orig_z_di_val
        entry.update(setup_eval)

        bar_info.append(entry)

    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")

    session_bars = [b for b in bar_info if SESSION_START <= b["t_min"] <= SESSION_END]
    target_date = today_str
    if not any(b["date"] == today_str for b in session_bars) and session_bars:
        target_date = session_bars[-1]["date"]

    history = []
    for b in session_bars:
        if b["date"] == target_date:
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
            "symbol_a":   "WINFUT",
            "symbol_b":   "WDOFUT",
            "di_symbol":  "DIFUT",
            "source":     "PROFIT",
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
    """V1 endpoint — OLS-based regime monitoring (WINFUT x WDOFUT via Profit)."""
    with _mt5_lock:
        return _regime_v1_impl()

def _regime_v1_impl():
    global _cache, _cache_ts

    if time.time() - _cache_ts < CACHE_TTL and _cache:
        return _cache

    needed = max(BARS, BETA_REF_BARS) + WINDOW + 10
    closes_a, times_a, _ = fetch_profit_m5_series("WINFUT", needed)
    closes_b, times_b, _ = fetch_profit_m5_series("WDOFUT", needed)

    global _last_win_price
    if closes_a is not None and len(closes_a) > 0:
        _last_win_price = float(closes_a[-1])

    if closes_a is None or closes_b is None:
        return {"error": "Sem dados para 'WINFUT'/'WDOFUT' no Profit.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": []}

    closes_a, closes_b, times_a = align_profit_series_with_ffill(closes_a, times_a, closes_b, times_b)

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

    # Legacy V1 endpoint is read-only: do NOT trigger _trade_engine.evaluate() with unfiltered V1 OLS z-score
    open_trades = _trade_engine._get_open_trades()
    any_holding = any(t is not None for t in open_trades.values())
    trade_result = {
        "action": "HOLDING" if any_holding else "WAIT",
        "holding": any_holding,
        "exit_reason": None,
        "pnl": None,
        "strategies": {},
    }

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
    """V2 endpoint — Kalman-based regime monitoring + Johansen gate (WINFUT x WDOFUT x DIFUT via Profit)."""
    with _v2_lock:
        return _regime_v2_impl()

def _regime_v2_impl():
    global _v2_cache, _v2_cache_ts, _last_win_price

    if time.time() - _v2_cache_ts < CACHE_TTL and _v2_cache:
        return _v2_cache

    closes_a, times_a, win_meta = fetch_profit_m5_series("WINFUT", 50000)
    closes_b, times_b, _ = fetch_profit_m5_series("WDOFUT", 50000)
    win_bars_by_ts = win_meta.get("bars_ByTs", {}) if isinstance(win_meta, dict) else {}

    if closes_a is not None and len(closes_a) > 0:
        _last_win_price = float(closes_a[-1])

    if closes_a is None or closes_b is None:
        return {"error": "Sem dados do Profit.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": []}

    ac_full, bc_full, tc_full = align_profit_series_with_ffill(closes_a, times_a, closes_b, times_b)
    idx_anchor = int(np.searchsorted(tc_full, ANCHOR_2026_TS))
    if 0 < idx_anchor < len(tc_full) - 600:
        ac_full = ac_full[idx_anchor:]
        bc_full = bc_full[idx_anchor:]
        tc_full = tc_full[idx_anchor:]

    # Always keep _di_cache synchronized to the current poll cycle
    try:
        di_regime()
    except Exception:
        pass

    # Kalman filter anchored to 2026-01-02 (first 500 bars of 2026) — zero sliding-window drift (with prefix cache)
    import copy as _copy
    prefix_key = (len(tc_full) - 1, int(tc_full[-2]) if len(tc_full) >= 2 else 0, float(ac_full[-2]) if len(ac_full) >= 2 else 0.0)
    if getattr(_regime_v2_impl, "_kf_prefix_key", None) == prefix_key and len(ac_full) >= 2:
        kf = _copy.deepcopy(_regime_v2_impl._kf_prefix_obj)
        spreads = list(_regime_v2_impl._kf_prefix_spreads)
        kf_betas = list(_regime_v2_impl._kf_prefix_betas)
        beta_current, spread_last, _ = kf.update(float(ac_full[-1]), float(bc_full[-1]))
        spreads.append(spread_last)
        kf_betas.append(beta_current)
    else:
        init_win_len = min(500, len(ac_full))
        if init_win_len > 50 and np.std(bc_full[:init_win_len]) > 1e-6:
            init_b_wdo, init_a_wdo = np.polyfit(bc_full[:init_win_len], ac_full[:init_win_len], 1)
            if init_b_wdo >= 0:
                init_b_wdo = BETA_INITIAL
                init_a_wdo = float(ac_full[0] - init_b_wdo * bc_full[0])
        else:
            init_b_wdo = BETA_INITIAL
            init_a_wdo = float(ac_full[0] - init_b_wdo * bc_full[0]) if len(ac_full) > 0 else 0.0

        kf = KalmanBetaFilter(initial_beta=float(init_b_wdo), initial_alpha=float(init_a_wdo), trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
        spreads, kf_betas = [], []
        beta_current = float(init_b_wdo)
        for idx_k, (y, x) in enumerate(zip(ac_full, bc_full)):
            if idx_k == len(ac_full) - 1 and len(ac_full) >= 2:
                _regime_v2_impl._kf_prefix_key = prefix_key
                _regime_v2_impl._kf_prefix_obj = _copy.deepcopy(kf)
                _regime_v2_impl._kf_prefix_spreads = list(spreads)
                _regime_v2_impl._kf_prefix_betas = list(kf_betas)
            beta, spread, var = kf.update(float(y), float(x))
            spreads.append(spread)
            kf_betas.append(beta)
            beta_current = beta

    tail_len = max(BARS + WDO_KALMAN_W + 10, 400)
    z_tail = KalmanBetaFilter.rolling_zscore(spreads[-tail_len:], window=WDO_KALMAN_W)
    z_scores_full = ([0.0] * max(0, len(spreads) - len(z_tail))) + list(z_tail)
    ref_20d_win = min(BETA_REF_BARS, len(kf_betas))
    beta_ref_20d = float(np.mean(kf_betas[-ref_20d_win:]) if ref_20d_win > 0 else beta_current)

    # Johansen gate evaluated on full aligned series with bar timestamp tracking
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        ac_full, bc_full, _joh_wdo_state, len(ac_full), last_bar_ts=int(tc_full[-1])
    )
    
    # ── NWE computation BEFORE slicing ───────────────────────────────────
    nwe_lookback_bars = min(len(ac_full), BARS + 200)
    ac_nwe = ac_full[-nwe_lookback_bars:]
    nwe_line_full, nwe_upper_full, nwe_lower_full, nwe_is_up_full = calc_nwe_with_bands(
        ac_nwe, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
    )

    # ── Slice after burn-in to keep payload and NWE/OLS fast ────────────
    if len(ac_full) > BARS:
        ac, bc, tc = ac_full[-BARS:], bc_full[-BARS:], tc_full[-BARS:]
        spreads = spreads[-BARS:]
        kf_betas = kf_betas[-BARS:]
        z_scores = z_scores_full[-BARS:]
        nwe_line = nwe_line_full[-BARS:]
        nwe_upper = nwe_upper_full[-BARS:]
        nwe_lower = nwe_lower_full[-BARS:]
        nwe_is_up_arr = nwe_is_up_full[-BARS:]
    else:
        ac, bc, tc = ac_full, bc_full, tc_full
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

    # Beta health
    beta_delta_pct = (abs(beta_current - beta_ref_20d) / abs(beta_ref_20d) * 100) if beta_ref_20d != 0 else 0
    beta_status_d = get_beta_status(beta_delta_pct)
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2)
    nwe_is_up_now = bool(nwe_is_up_arr[-1])
    nwe_upper_now = float(nwe_upper[-1])
    nwe_lower_now = float(nwe_lower[-1])

    # Trade engine (Consenso WDO + DI + NWE filters)
    now_dt = datetime.now()
    z_di = _di_cache.get("current_z", 0.0) if _di_cache else 0.0
    
    # ── Bar-close gate: entries only on confirmed bar close ──────────
    last_bar_ts = int(tc[-1])
    bar_close_confirmed = False
    if not hasattr(_regime_v2_impl, "_last_bar_ts"):
        _regime_v2_impl._last_bar_ts = last_bar_ts
    elif _regime_v2_impl._last_bar_ts != last_bar_ts:
        bar_close_confirmed = True
        _regime_v2_impl._last_bar_ts = last_bar_ts
        di_regime()

    # Re-fetch DI cache after forced update
    z_di = _di_cache.get("current_z", 0.0) if _di_cache else 0.0

    # On confirmed bar close, evaluate entry criteria using the just-closed bar [-2] to avoid newborn tick noise
    eval_z_wdo = float(z_scores[-2]) if (bar_close_confirmed and len(z_scores) > 1) else current_z
    eval_z_di = float(_di_cache["history"][-2]["z"]) if (bar_close_confirmed and _di_cache and len(_di_cache.get("history", [])) > 1) else float(z_di)
    eval_win_px = float(ac[-2]) if (bar_close_confirmed and len(ac) > 1) else float(ac[-1])
    eval_wdo_px = float(bc[-2]) if (bar_close_confirmed and len(bc) > 1) else float(bc[-1])
    eval_nwe_up = bool(nwe_is_up_arr[-2]) if (bar_close_confirmed and len(nwe_is_up_arr) > 1) else nwe_is_up_now
    eval_nwe_upper = float(nwe_upper[-2]) if (bar_close_confirmed and len(nwe_upper) > 1) else nwe_upper_now
    eval_nwe_lower = float(nwe_lower[-2]) if (bar_close_confirmed and len(nwe_lower) > 1) else nwe_lower_now

    active_walls = get_gex_walls()
    trade_result = _trade_engine.evaluate(
        z_wdo=eval_z_wdo, z_di=eval_z_di,
        win_price=eval_win_px, wdo_price=eval_wdo_px,
        rho=current_rho, beta_safe=safe_to_trade, hmm_state=hmm.current_hmm_regime,
        hour=now_dt.hour, minute=now_dt.minute, beta_value=beta_current,
        nwe_is_up=eval_nwe_up, nwe_upper=eval_nwe_upper, nwe_lower=eval_nwe_lower,
        bar_close_confirmed=bar_close_confirmed,
        walls=active_walls,
    )

    di_map = {}
    if _di_cache and "history" in _di_cache:
        for dh in _di_cache["history"]:
            dt_str = dh.get("date", "") + " " + dh.get("bar_time", "")
            di_map[dt_str] = dh.get("z", 0.0)
            if dh.get("timestamp") is not None:
                di_map[int(dh["timestamp"])] = dh.get("z", 0.0)
            try:
                local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                di_map[int(local_dt.timestamp())] = dh.get("z", 0.0)
            except Exception:
                pass

    live_history = _build_history(
        tc, z_scores, spreads, win_prices=ac,
        nwe_data=(nwe_line, nwe_upper, nwe_lower, nwe_is_up_arr),
        di_map=di_map,
        active_walls=active_walls,
    )
    active_date_str = live_history[-1]["date"] if live_history else datetime.now().strftime("%Y-%m-%d")

    # Persist all closed bars of active_date_str into bar_history so closed bars are permanently frozen
    if getattr(_regime_v2_impl, "_db_hist_date", None) != active_date_str or not hasattr(_regime_v2_impl, "_db_hist_cache"):
        db_hist_all = load_bar_history(days=5, active_walls=active_walls)
        _regime_v2_impl._db_hist_cache = [h for h in db_hist_all if h.get("date") == active_date_str]
        _regime_v2_impl._db_hist_date = active_date_str
    db_hist = _regime_v2_impl._db_hist_cache
    db_keys = {h["date"] + " " + h["bar_time"] for h in db_hist}

    wdo_by_ts = {int(t): float(b_px) for t, b_px in zip(tc, bc)}
    now_epoch = int(time.time())
    newly_saved = False
    for idx_lh, lh in enumerate(live_history):
        ts_key = lh["date"] + " " + lh["bar_time"]
        raw_ts = int(lh.get("timestamp", 0))
        local_ts = raw_ts + TIME_OFFSET
        is_closed = (idx_lh < len(live_history) - 1) or (now_epoch >= (local_ts + 300))
        if is_closed and ts_key not in db_keys and raw_ts > 0:
            save_bar_history(
                timestamp=raw_ts,
                date_str=lh["date"],
                bar_time=lh["bar_time"],
                win_price=float(lh.get("win_price") or 0.0),
                wdo_price=float(wdo_by_ts.get(raw_ts, 0.0)),
                di_price=0.0,
                spread_wdo=float(lh.get("spread") or 0.0),
                spread_di=0.0,
                z_wdo=float(lh.get("z") or 0.0),
                z_di=float(lh.get("z_di") or 0.0),
                nwe_center=lh.get("nwe"),
                nwe_upper=lh.get("nweUpper"),
                nwe_lower=lh.get("nweLower"),
                nwe_is_up=bool(lh.get("isUp")),
                flow_json=None,
            )
            newly_saved = True

    if newly_saved:
        db_hist_all = load_bar_history(days=5, active_walls=active_walls)
        db_hist = [h for h in db_hist_all if h.get("date") == active_date_str]
        _regime_v2_impl._db_hist_cache = db_hist
        _regime_v2_impl._db_hist_date = active_date_str

    merged_map = {}
    for lh in live_history:
        ts_str = lh["date"] + " " + lh["bar_time"]
        merged_map[ts_str] = lh

    live_last_key = (live_history[-1]["date"] + " " + live_history[-1]["bar_time"]) if live_history else None
    live_last_closed = False
    if live_history:
        live_last_closed = now_epoch >= (int(live_history[-1].get("timestamp", 0)) + TIME_OFFSET + 300)

    for db_h in db_hist:
        ts_str = db_h["date"] + " " + db_h["bar_time"]
        # Freeze all closed bars from DB; keep the currently forming open bar live
        if ts_str != live_last_key or live_last_closed:
            merged_map[ts_str] = db_h

    history = []
    for k in sorted(merged_map.keys()):
        item = dict(merged_map[k])
        item["i"] = len(history)
        history.append(item)

    # Attach real Profit broker flow data and M5 OHLC to bars
    profit_flow_bundle = get_profit_day_flow_bundle(active_date_str)
    snap_by_bt = {s["time"]: {"WIN": s["WIN"], "WDO": s["WDO"]} for s in profit_flow_bundle.get("history", [])}
    current_flow = profit_flow_bundle.get("current", _get_current_flow_data())
    for h in history:
        bt = h.get("bar_time", "")
        h["flow"] = snap_by_bt.get(bt, current_flow)
        raw_ts_h = int(h.get("timestamp") or 0)
        b_ohlc = win_bars_by_ts.get(raw_ts_h, {})
        px_h = float(h.get("win_price") or 0.0)
        h["win_open"] = float(b_ohlc.get("open", px_h))
        h["win_high"] = float(b_ohlc.get("high", px_h))
        h["win_low"] = float(b_ohlc.get("low", px_h))

    day_trades = simulate_day_statarb_trades(history, active_walls)

    sig_data = get_signal(current_z, current_spread_sd, beta_current, hmm_state=hmm.current_hmm_regime)

    res = _build_response(
        current_z, current_rho, 0, min(100.0, abs(current_z) / 4.0 * 100.0),
        beta_current, beta_ref_20d, beta_delta_pct, 0.0, beta_status_d["level"] >= 2,
        rho_status, beta_status_d, safe_to_trade,
        trade_result, history, version="v2_kalman",
    )
    res["day_trades"] = day_trades
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
    _v2_cache = res
    _v2_cache_ts = time.time()
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
    """WIN×DI pair trading — Johansen z-score + gate (WINFUT x DIFUT via Profit)."""
    with _di_lock:
        return _di_regime_impl()

def _di_regime_impl():
    global _di_cache, _di_cache_ts, _di_beta_state, _di_coint_cache

    if time.time() - _di_cache_ts < CACHE_TTL and _di_cache:
        return _di_cache

    closes_win, times_win, _ = fetch_profit_m5_series("WINFUT", 50000)
    closes_di, times_di, di_meta = fetch_profit_m5_series("DIFUT", 50000)

    if closes_win is None or closes_di is None:
        return {"error": "Sem dados para 'WINFUT'/'DIFUT' no Profit.",
                "current_z": 0, "signal": _get_di_signal(0), "history": []}

    closes_win, closes_di, times_win = align_profit_series_with_ffill(closes_win, times_win, closes_di, times_di)
    idx_anchor = int(np.searchsorted(times_win, ANCHOR_2026_TS))
    if 0 < idx_anchor < len(times_win) - 600:
        closes_win = closes_win[idx_anchor:]
        closes_di = closes_di[idx_anchor:]
        times_win = times_win[idx_anchor:]

    today = datetime.now().date()

    # ── Johansen gate + beta ──────────────────────────────────────────
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        closes_win, closes_di, _joh_di_state, len(closes_win), last_bar_ts=int(times_win[-1])
    )

    # ── DI Kalman z-score anchored to 2026-01-02 (first 500 bars of 2026, with prefix cache) ──
    import copy as _copy
    di_prefix_key = (len(times_win) - 1, int(times_win[-2]) if len(times_win) >= 2 else 0, float(closes_win[-2]) if len(closes_win) >= 2 else 0.0)
    if getattr(_di_regime_impl, "_kf_prefix_key", None) == di_prefix_key and len(closes_win) >= 2:
        kf_di = _copy.deepcopy(_di_regime_impl._kf_prefix_obj)
        spreads = list(_di_regime_impl._kf_prefix_spreads)
        kf_betas = list(_di_regime_impl._kf_prefix_betas)
        beta_last, spread_last, _ = kf_di.update(float(closes_win[-1]), float(closes_di[-1]))
        spreads.append(spread_last)
        kf_betas.append(beta_last)
    else:
        init_win_len = min(500, len(closes_win))
        if init_win_len > 50 and np.std(closes_di[:init_win_len]) > 1e-6:
            b, a = np.polyfit(closes_di[:init_win_len], closes_win[:init_win_len], 1)
            if b >= 0:
                init_beta = DI_BETA_INITIAL
                init_alpha = float(closes_win[0] - init_beta * closes_di[0])
            else:
                init_beta, init_alpha = b, a
        else:
            init_beta = DI_BETA_INITIAL
            init_alpha = float(closes_win[0] - init_beta * closes_di[0]) if len(closes_win) > 0 else 260000.0

        kf_di = KalmanBetaFilter(initial_beta=init_beta, initial_alpha=init_alpha, trans_cov=DI_KALMAN_Q, obs_cov=DI_KALMAN_R)
        spreads = []
        kf_betas = []
        for idx_k, (y, x) in enumerate(zip(closes_win, closes_di)):
            if idx_k == len(closes_win) - 1 and len(closes_win) >= 2:
                _di_regime_impl._kf_prefix_key = di_prefix_key
                _di_regime_impl._kf_prefix_obj = _copy.deepcopy(kf_di)
                _di_regime_impl._kf_prefix_spreads = list(spreads)
                _di_regime_impl._kf_prefix_betas = list(kf_betas)
            beta, spread, _ = kf_di.update(float(y), float(x))
            spreads.append(spread)
            kf_betas.append(beta)
        
    beta_current = kf_betas[-1]
    
    tail_di_len = max(DI_BARS + DI_KALMAN_W + 10, 400)
    spread_arr = np.array(spreads[-tail_di_len:])
    z_tail = KalmanBetaFilter.rolling_zscore(spreads[-tail_di_len:], window=DI_KALMAN_W)
    z_arr = np.array(z_tail)
    di_bars_by_ts = di_meta.get("bars_ByTs", {})
    for idx_t, ts_val in enumerate(times_win[-len(z_arr):]):
        exact_z = di_bars_by_ts.get(int(ts_val), {}).get("z_di_exact")
        if exact_z is not None and idx_t < len(z_arr):
            z_arr[idx_t] = float(exact_z)
    current_z = float(z_arr[-1]) if len(z_arr) > 0 else 0.0

    # NaN protection
    if math.isnan(beta_current) or math.isnan(current_z):
        return {"error": "OLS NaN", "current_z": 0, "signal": _get_di_signal(0), "history": []}

    method_label = "kalman"

    # Rho (correlation) — use Kalman beta on tail
    _, _, rho_arr = calc_zscore(closes_win[-tail_di_len:], closes_di[-tail_di_len:], beta=beta_current)
    current_rho = float(rho_arr[-1]) if len(rho_arr) > 0 and not math.isnan(float(rho_arr[-1])) else 0.0

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
            "symbol_a": "WINFUT",
            "symbol_b": "DIFUT",
            "source": "PROFIT",
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
    with _mt5_lock:
        connected = connect_mt5()
        info = mt5.terminal_info() if connected else None
    return {
        "mt5_connected": connected,
        "profit_connected": True,
        "terminal_name": info.name if info else "Profit Native DB + RTD",
        "terminal_path": info.path if info else "Nelogica/Scalper & Profit",
        "configured_path": MT5_PATH or "(automatico)",
        "symbol_a": "WINFUT",
        "symbol_b": "WDOFUT",
        "di_symbol": "DIFUT",
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
        for cand in [
            os.path.join("gex", "data", "win_walls_cache.json"),
            os.path.join("gex", "data", "jumba_gex_win_daily.json"),
            os.path.join("gex", "data", "jumba_gex_win_history.json"),
        ]:
            if os.path.exists(cand):
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "walls" in data:
                        return data["walls"]
                    elif isinstance(data, dict) and data:
                        latest_key = sorted(data.keys())[-1]
                        entry = data[latest_key]
                        if isinstance(entry, dict) and "walls" in entry:
                            return entry["walls"]
    except Exception as e:
        print(f"Erro ao ler walls localmente: {e}")
    return []


@app.get("/api/live-calendar")
def get_live_calendar(account: str = ""):
    """Calendário do Live Trading: trades fechados das EAs Jumba no MT5 milhao (via CSV do Live Monitor)."""
    try:
        from core.live_calendar import load_live_calendar, LIVE_ACCOUNT
        return load_live_calendar(account or LIVE_ACCOUNT)
    except Exception as e:
        return {"ok": False, "error": str(e), "trades": [], "open_positions": []}


# ─── Multi-day History Endpoint ──────────────────────────────────────────────

_hist_cache: dict = {}
_hist_cache_ts: float = 0.0
_hist_cache_days: int = 0

@app.get("/api/history")
def history_endpoint(days: int = 30):
    with _mt5_lock:
        return _history_endpoint_impl(days)

def _history_endpoint_impl(days: int = 30):
    """Multi-day z-score history (Kalman + OLS + DI).
    
    Returns session-filtered bars for the last N trading days.
    Each bar has: date, bar_time, z (Kalman), z_v1 (OLS), z_di (DI).
    """
    global _hist_cache, _hist_cache_ts, _hist_cache_days

    # Cache for 30s (heavier computation)
    if time.time() - _hist_cache_ts < 30 and _hist_cache and _hist_cache_days == days:
        return _hist_cache

    try:
        # M5 bars: ~108 bars/session day (9:20-18:20), fetch extra for window warmup
        bars_per_day = 108
        bars_needed = max(days * bars_per_day + WINDOW + 50, KALMAN_BURN_IN)
        tail_bars = max(days * 135 + 120, 800)

        # Fetch WINFUT, WDOFUT, DIFUT via Profit
        closes_a, times_a, win_meta = fetch_profit_m5_series("WINFUT", 50000)
        closes_b, times_b, _ = fetch_profit_m5_series("WDOFUT", 50000)
        closes_di, times_di, di_meta = fetch_profit_m5_series("DIFUT", 50000)
        win_bars_by_ts = win_meta.get("bars_ByTs", {}) if isinstance(win_meta, dict) else {}

        if closes_a is None or closes_b is None:
            return {"error": "Sem dados WINFUT/WDOFUT no Profit.", "history": [], "days": days}

        ac, bc, tc = align_profit_series_with_ffill(closes_a, times_a, closes_b, times_b)
        idx_anchor = int(np.searchsorted(tc, ANCHOR_2026_TS))
        if 0 < idx_anchor < len(tc) - 600:
            ac = ac[idx_anchor:]
            bc = bc[idx_anchor:]
            tc = tc[idx_anchor:]

        min_len = len(ac)
        slice_len = min(min_len, tail_bars)

        # --- Kalman z-scores anchored to 2026-01-02 ---
        init_win_len = min(500, len(ac))
        if init_win_len > 50 and np.std(bc[:init_win_len]) > 1e-6:
            init_b_wdo, init_a_wdo = np.polyfit(bc[:init_win_len], ac[:init_win_len], 1)
            if init_b_wdo >= 0:
                init_b_wdo = BETA_INITIAL
                init_a_wdo = float(ac[0] - init_b_wdo * bc[0])
        else:
            init_b_wdo = BETA_INITIAL
            init_a_wdo = float(ac[0] - init_b_wdo * bc[0]) if len(ac) > 0 else 0.0
        kf = KalmanBetaFilter(initial_beta=float(init_b_wdo), initial_alpha=float(init_a_wdo), trans_cov=WDO_KALMAN_Q, obs_cov=WDO_KALMAN_R)
        kf_spreads = []
        for y, x in zip(ac, bc):
            _, spread_t, _ = kf.update(float(y), float(x))
            kf_spreads.append(spread_t)
        z_kalman = KalmanBetaFilter.rolling_zscore(kf_spreads, window=WDO_KALMAN_W)[-slice_len:]

        # --- OLS z-scores ---
        beta_ols_val = beta_state["current_beta"]
        _, z_ols, _ = calc_zscore(ac, bc, beta=beta_ols_val, max_bars=slice_len)

        # --- DI z-scores (Kalman anchored to 2026-01-02 + Profit/DB exact) ---
        z_di_map = {}
        if closes_di is not None:
            win_for_di, di_c, di_t = align_profit_series_with_ffill(closes_a, times_a, closes_di, times_di)
            idx_di_anchor = int(np.searchsorted(di_t, ANCHOR_2026_TS))
            if 0 < idx_di_anchor < len(di_t) - 600:
                win_for_di = win_for_di[idx_di_anchor:]
                di_c = di_c[idx_di_anchor:]
                di_t = di_t[idx_di_anchor:]

            init_di_len = min(500, len(win_for_di))
            if init_di_len > 50 and np.std(di_c[:init_di_len]) > 1e-6:
                init_b_di, init_a_di = np.polyfit(di_c[:init_di_len], win_for_di[:init_di_len], 1)
                if init_b_di >= 0:
                    init_b_di = DI_BETA_INITIAL
                    init_a_di = float(win_for_di[0] - init_b_di * di_c[0])
            else:
                init_b_di = DI_BETA_INITIAL
                init_a_di = float(win_for_di[0] - init_b_di * di_c[0]) if len(win_for_di) > 0 else 260000.0

            # DI Kalman filter
            kf_di = KalmanBetaFilter(
                initial_beta=float(init_b_di),
                initial_alpha=float(init_a_di),
                trans_cov=DI_KALMAN_Q,
                obs_cov=DI_KALMAN_R,
            )
            di_spreads = []
            for y, x in zip(win_for_di, di_c):
                _, spread_t, _ = kf_di.update(float(y), float(x))
                di_spreads.append(spread_t)
            z_di_arr = KalmanBetaFilter.rolling_zscore(di_spreads, window=DI_KALMAN_W)
            di_bars_by_ts = di_meta.get("bars_ByTs", {})

            start_di_idx = max(0, len(di_t) - slice_len)
            for i in range(start_di_idx, len(di_t)):
                t = di_t[i]
                exact_z = di_bars_by_ts.get(int(t), {}).get("z_di_exact")
                val = round(float(exact_z if exact_z is not None else (z_di_arr[i] if i < len(z_di_arr) else 0.0)), 3)
                local_ts = int(t) + TIME_OFFSET
                dt_key = datetime.fromtimestamp(local_ts).strftime("%Y-%m-%d %H:%M")
                z_di_map[local_ts] = val
                z_di_map[dt_key] = val

        # Slice ac and tc to slice_len (with 100-bar warmup for NWE)
        nwe_slice = min(len(ac), slice_len + 100)
        ac_nwe = ac[-nwe_slice:]
        ac = ac[-slice_len:]
        tc = tc[-slice_len:]

        # --- NWE for history ---
        nwe_line, nwe_u, nwe_l, nwe_is_up = calc_nwe_with_bands(
            ac_nwe, bandwidth=NWE_BANDWIDTH, lookback=NWE_LOOKBACK, mult_mae=NWE_MULT_MAE
        )
        nwe_line = nwe_line[-slice_len:]
        nwe_u = nwe_u[-slice_len:]
        nwe_l = nwe_l[-slice_len:]
        nwe_is_up = nwe_is_up[-slice_len:]

        # --- Build history with session filter ---
        n = len(z_kalman)
        ols_offset = len(z_ols) - n  # align arrays
        nwe_offset = len(nwe_line) - n
        active_walls = get_gex_walls()
        now_epoch = int(time.time())

        entries = []
        last_valid_z_di = 0.0
        for i in range(n):
            raw_ts = int(tc[i + (len(tc) - n)])
            local_ts = raw_ts + TIME_OFFSET
            dt = datetime.fromtimestamp(local_ts)
            t_min = dt.hour * 60 + dt.minute

            if not (SESSION_START <= t_min <= SESSION_END):
                continue

            ols_idx = i + ols_offset
            z_ols_val = round(float(z_ols[ols_idx]), 3) if 0 <= ols_idx < len(z_ols) else 0.0
            dt_key = dt.strftime("%Y-%m-%d %H:%M")
            z_di_val = z_di_map.get(dt_key) if z_di_map else None
            if z_di_val is None and z_di_map:
                z_di_val = z_di_map.get(local_ts, None)
            if z_di_val is None:
                z_di_val = last_valid_z_di
            else:
                last_valid_z_di = float(z_di_val)

            win_idx = i + (len(tc) - n)
            win_val = float(ac[win_idx]) if 0 <= win_idx < len(ac) else 0.0
            orig_z_wdo = round(float(z_kalman[i]), 3)
            orig_z_di = round(float(z_di_val), 3)

            b_ohlc = win_bars_by_ts.get(raw_ts, {})
            entry = {
                "timestamp": raw_ts,
                "date": dt.strftime("%Y-%m-%d"),
                "bar_time": dt.strftime("%H:%M"),
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "z": orig_z_wdo,
                "z_v1": z_ols_val,
                "z_di": orig_z_di,
                "win_price": win_val,
                "win_open": float(b_ohlc.get("open", win_val)),
                "win_high": float(b_ohlc.get("high", win_val)),
                "win_low": float(b_ohlc.get("low", win_val)),
            }
            
            nv = nu = nl = n_up = None
            nwe_idx = i + nwe_offset
            if 0 <= nwe_idx < len(nwe_line):
                nv = float(nwe_line[nwe_idx])
                nu = float(nwe_u[nwe_idx])
                nl = float(nwe_l[nwe_idx])
                n_up = bool(nwe_is_up[nwe_idx])
                entry["nwe"] = round(nv, 2)
                entry["nweUpper"] = round(nu, 2)
                entry["nweLower"] = round(nl, 2)
                entry["isUp"] = n_up
                entry["is_up"] = n_up

            is_closed = (i < n - 1) or (now_epoch >= (local_ts + 300))
            setup_eval = _evaluate_bar_setups(
                orig_z_wdo, orig_z_di, win_val, nv, nu, nl, n_up, t_min,
                active_walls=active_walls, is_closed_bar=is_closed
            )
            entry["z_unfiltered_wdo"] = orig_z_wdo
            entry["z_unfiltered_di"] = orig_z_di
            entry.update(setup_eval)

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

def calculate_directional_efficiency(lookback_bars: int = None, bars_list=None):
    """Calculate the Daily Directional Efficiency (Player Price Influence) for WIN.
    
    Formula: (sum(dPrice * dNet) / sum(|dPrice * dNet|)) * 100
    """
    if bars_list is None:
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
    else:
        rows = bars_list

    if lookback_bars is not None:
        rows = rows[-lookback_bars:]

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

def calculate_flow_acceleration(efficiency=None, bars_list=None):
    """Calculate the Flow Acceleration Index (IAF) based on Kyle's Lambda (Lots per 100 points) for WIN.
    
    Returns a dictionary: {"WIN": float} containing scores from -100 to 100.
    """
    if bars_list is None:
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
    
    # 1. Identify dominant players per symbol (DDE >= 40%) using short-term rolling efficiency (5 bars / 25 minutes)
    short_term_eff = calculate_directional_efficiency(lookback_bars=5, bars_list=bars_list)
    dominant_players = {"WIN": []}
    sym_eff = short_term_eff.get("WIN", {})
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

@app.post("/api/restart")
def restart_server(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        return {"ok": False, "error": "Acesso permitido apenas via localhost."}
    print("[INFO] Comando de reinicialização recebido pelo endpoint API. Limpando caches e recarregando motores em tempo real...")
    global _cache, _cache_ts, _v2_cache, _v2_cache_ts, _di_cache, _di_cache_ts
    _cache = {}
    _cache_ts = 0.0
    _v2_cache = {}
    _v2_cache_ts = 0.0
    _di_cache = {}
    _di_cache_ts = 0.0
    try:
        import importlib
        import core.gex_live_dealer_engine
        import core.profit_mt5_flow_engine
        with _mt5_lock:
            importlib.reload(core.gex_live_dealer_engine)
            importlib.reload(core.profit_mt5_flow_engine)
            from core.profit_mt5_flow_engine import flow_engine_singleton
            flow_engine_singleton._last_update_ts = 0.0
            if hasattr(flow_engine_singleton, "_historical_cache"):
                flow_engine_singleton._historical_cache.clear()
            flow_engine_singleton.update(force=True)
    except Exception:
        pass
    return {"ok": True, "message": "Caches e motores reiniciados com sucesso!"}

@app.get("/api/flow/realtime")
def get_realtime_flow(
    w_fln: float = 0.20,
    w_pers: float = 0.40,
    w_conc: float = 0.30,
    w_abs: float = 0.10,
    date_str: str = None,
):
    with _mt5_lock:
        bundle = get_profit_day_flow_bundle(date_str)
    return format_flow_score_for_frontend(
        bundle,
        w_fln=w_fln,
        w_pers=w_pers,
        w_conc=w_conc,
        w_abs=w_abs,
    )


@app.get("/api/flow/iaf-history")
def get_iaf_history(date_str: str = None):
    with _mt5_lock:
        bundle = get_profit_day_flow_bundle(date_str)
    return format_iaf_for_frontend(bundle)


@app.get("/api/flow")
def get_flow(date_str: str = None):
    with _mt5_lock:
        bundle = get_profit_day_flow_bundle(date_str)
    current_flow = bundle.get("current", _broker_flow)
    # Garantir que cada corretora tenha id, net, avg, vol, buy, sell
    formatted_flow = {"WIN": {}, "WDO": {}}
    for sym in ("WIN", "WDO"):
        sym_data = current_flow.get(sym, {})
        for idx, b in enumerate(_broker_list):
            b_obj = sym_data.get(b, {})
            formatted_flow[sym][b] = {
                "id": str(idx),
                "net": int(b_obj.get("net", 0)),
                "avg": float(b_obj.get("avg", 0.0)),
                "vol": int(b_obj.get("vol", 0)),
                "buy": int(b_obj.get("buy", 0)),
                "sell": int(b_obj.get("sell", 0)),
            }

    return {
        "date": bundle.get("date"),
        "source": bundle.get("source", "PROFIT_NATIVE"),
        "brokers": _broker_list,
        "flow": formatted_flow,
        "history": bundle.get("history", []),
        "efficiency": bundle.get("efficiency", {"WIN": {}}),
        "accelerator": bundle.get("accelerator", {"WIN": 0.0}),
        "last_update": {
            "WIN": f"PROFIT ({bundle.get('date', 'LIVE')})"
        },
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
        if len(_broker_list) >= 50:
            return {"error": "Limite máximo de corretoras atingido."}
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

# ─── Etapa 1, 2 & 3: Motor de Microestrutura + Caminho A (Dealers GEX) + Caminho B (Opções) ────
@app.get("/api/compass/etapa1")
@app.get("/api/compass/all")
@app.get("/api/flow/microstructure")
def get_compass_etapa1(date_str: str = None, lite: bool = False):
    """Retorna o snapshot completo unificado das Etapas 1, 2 (Caminho A) e 3 (Caminho B) e sincroniza _broker_flow."""
    try:
        from core.profit_mt5_flow_engine import flow_engine_singleton
        with _mt5_lock:
            snap = flow_engine_singleton.update(date_str=date_str)
        win_b = snap.get("WIN", {}).get("brokers", {})
        if win_b:
            any_vol = False
            for brk, bdata in win_b.items():
                if bdata.get("vol", 0) > 0 or bdata.get("net", 0) != 0:
                    any_vol = True
                if brk not in _broker_flow["WIN"]:
                    _broker_flow["WIN"][brk] = {"id": str(len(_broker_flow["WIN"])), "net": 0, "avg": 0.0, "vol": 0, "buy": 0, "sell": 0}
                    if brk not in _broker_list:
                        _broker_list.append(brk)
                _broker_flow["WIN"][brk]["net"] = bdata.get("net", 0)
                _broker_flow["WIN"][brk]["buy"] = bdata.get("aggr_buy", bdata.get("buy", 0))
                _broker_flow["WIN"][brk]["sell"] = bdata.get("aggr_sell", bdata.get("sell", 0))
                _broker_flow["WIN"][brk]["vol"] = bdata.get("vol", 0)
            if any_vol:
                _last_flow_update["WIN"] = time.time()
        if lite and isinstance(snap, dict) and isinstance(snap.get("portfolio_4_sistematicas"), dict):
            p4_full = snap["portfolio_4_sistematicas"]
            live_days = p4_full.get("live_days", [])
            lite_snap = dict(snap)
            lite_p4 = dict(p4_full)
            lite_p4["is_lite"] = True
            lite_p4["days"] = live_days
            lite_p4["all_11_comparison"] = []
            lite_snap["portfolio_4_sistematicas"] = lite_p4
            return lite_snap
        return snap
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/api/compass/m1_series")
def get_compass_m1_series(date_str: str = None):
    """Retorna a série intradiária enriquecida de 1 Minuto (M1) para WIN e WDO (com NWE causal + Fluxo Smart Money)."""
    try:
        from core.gex_live_dealer_engine import gex_dealer_engine_singleton
        return gex_dealer_engine_singleton.get_m1_chart_payload(sess_date=date_str)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/api/compass/etapa2")
@app.get("/api/compass/dealer-gex")
def get_compass_etapa2(date_str: str = None):
    """Retorna a análise da Etapa 2 (Caminho A — Pressão de Hedge Dinâmico dos Dealers GEX cruzada com o Fluxo Profit/MT5)."""
    try:
        from core.profit_mt5_flow_engine import flow_engine_singleton
        with _mt5_lock:
            snap = flow_engine_singleton.update(date_str=date_str)
        return {
            "ok": snap.get("ok", True),
            "timestamp": snap.get("timestamp"),
            "updated_at": snap.get("updated_at"),
            "WIN": snap.get("WIN", {}).get("caminho_a", {}),
            "WDO": snap.get("WDO", {}).get("caminho_a", {}),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/api/compass/etapa3")
@app.get("/api/compass/options-radar")
def get_compass_etapa3():
    """Retorna a análise da Etapa 3 (Caminho B — Radar Ao Vivo da Cadeia de Opções BOVA11/IBOV, Fluxo Call vs Put e Skew IV)."""
    try:
        from core.options_live_radar_engine import options_radar_singleton
        with _mt5_lock:
            return options_radar_singleton.update()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

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
