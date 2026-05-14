# server.py — WIN×WDO Regime Monitor (Thin Controller)
"""
FastAPI server for WIN×WDO pair trading regime monitoring.
All computation logic lives in core/ modules.
"""
import copy
import json
import logging
import time
import sqlite3
import threading
import numpy as np
import MetaTrader5 as mt5
from dataclasses import asdict
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import math
from contextvars import ContextVar
from functools import wraps
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen

import os
import asyncio

# Configure root logger at module import so gate_block INFO lines reach the
# console/PM2 log in all launch modes (python server.py, uvicorn server:app,
# pm2). If a caller has already configured logging this call is a no-op.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)
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
    SYMBOL_A, SYMBOL_B, TIMEFRAME, BARS, KALMAN_BURN_IN,
    BETA_INITIAL, MT5_PATH,
    TIME_OFFSET, CACHE_TTL,
    DI_SYMBOL, DI_KALMAN_Q, DI_KALMAN_R, DI_KALMAN_W,
    DI_BARS, DI_BETA_INITIAL,
    DI_BETA_REF_BARS, DI_Z_ENTRY, DI_Z_ANOMALY, DI_Z_ATTENTION,
    JOH_WINDOW, JOH_RECHECK_BARS,
    NWE_BANDWIDTH, NWE_LOOKBACK, NWE_MULT_MAE,
    WDO_KALMAN_Q, WDO_KALMAN_R, WDO_KALMAN_W,
    LIVE_ORDERS, LIVE_SYMBOL_WIN,
)
from core.mt5_client import (
    connect_mt5, fetch_bars, fetch_rates, resolve_live_symbol_win,
)
from core.signals import (
    calc_beta_ols, calc_half_life, calc_zscore,
    get_signal, get_rho_status, get_beta_status,
    calc_nwe_with_bands,
)
from core.kalman_filter import KalmanBetaFilter
from core.execution_timeline import (
    bulk_record_events,
    current_bottleneck,
    current_live_issue,
    init_timeline_table,
    load_timeline,
    record_event,
)
from core.risk_gate import (
    compute_engle_granger_pvalue,
    risk_gate,
)
from core.timeline_emit import (
    emit_closed_bar_timeline,
    reason_message,
    timeline_minute_key,
    timeline_ts,
)
from core.trade_engine import STRATEGIES, TradeEngine
from core import runtime_config
from core import bar_history_db as bhdb
import core.hmm_background as hmm


# ─── App setup ───────────────────────────────────────────────────────────────
import contextlib

POLL_INTERVAL_SEC = 2.5

_eval_lock = threading.Lock()
_eval_state_lock = threading.Lock()
_eval_source = ContextVar("eval_source", default="http")
_latest_regime_snapshot: dict | None = None
_eval_state = {
    "loop_running": False,
    "in_progress": False,
    "last_source": None,
    "last_started_at": None,
    "last_completed_at": None,
    "last_completed_epoch": None,
    "last_duration_ms": None,
    "last_error": None,
    "last_error_at": None,
    "last_result_error": None,
}


def _set_eval_state(**fields) -> None:
    with _eval_state_lock:
        _eval_state.update(fields)


def _get_eval_state() -> dict:
    with _eval_state_lock:
        return dict(_eval_state)


def _serialized_regime_call(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        global _latest_regime_snapshot
        source = _eval_source.get()
        with _eval_lock:
            started = time.time()
            _set_eval_state(
                in_progress=True,
                last_source=source,
                last_started_at=datetime.now().isoformat(timespec="seconds"),
            )
            try:
                result = fn(*args, **kwargs)
                completed = time.time()
                _latest_regime_snapshot = result if isinstance(result, dict) else None
                _set_eval_state(
                    in_progress=False,
                    last_completed_at=datetime.now().isoformat(timespec="seconds"),
                    last_completed_epoch=completed,
                    last_duration_ms=round((completed - started) * 1000, 1),
                    last_error=None,
                    last_result_error=(
                        result.get("error") if isinstance(result, dict) else None
                    ),
                )
                return result
            except Exception as exc:
                completed = time.time()
                _set_eval_state(
                    in_progress=False,
                    last_duration_ms=round((completed - started) * 1000, 1),
                    last_error=f"{type(exc).__name__}: {exc}",
                    last_error_at=datetime.now().isoformat(timespec="seconds"),
                )
                raise

    return wrapper


def _run_regime_v2_from_loop():
    token = _eval_source.set("loop")
    try:
        return regime_v2()
    finally:
        _eval_source.reset(token)


def _push_dashboard_to_firebase(regime, di_regime_payload, performance) -> None:
    ref = fdb.reference('dashboard')
    ref.set({
        'regime': regime,
        'di_regime': di_regime_payload,
        'performance': performance,
    })


def _push_history_to_firebase(history_payload) -> None:
    ref_hist = fdb.reference('history_30d')
    ref_hist.set(history_payload.get("history", []))


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("trade_eval_loop stopped unexpectedly")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    eval_task = asyncio.create_task(trade_eval_loop())
    eval_task.add_done_callback(_log_background_task_result)

    # Run backfill async
    threading.Thread(target=do_backfill_if_empty, daemon=True).start()

    try:
        yield
    finally:
        eval_task.cancel()
        await asyncio.gather(eval_task, return_exceptions=True)

app = FastAPI(title="WIN×WDO Regime Monitor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

async def trade_eval_loop():
    _set_eval_state(loop_running=True)
    try:
        logger.info(
            "trade_eval_loop started interval=%.1fs firebase_enabled=%s",
            POLL_INTERVAL_SEC,
            firebase_initialized,
        )
        last_hist_update = 0
        last_dash_update = 0

        while True:
            try:
                r_v2 = await asyncio.to_thread(_run_regime_v2_from_loop)

                if firebase_initialized:
                    r_di = await asyncio.to_thread(di_regime)
                    perf = await asyncio.to_thread(get_performance)

                    # Check for immediate push condition
                    action_v2 = r_v2.get("trade_engine", {}).get("action", "WAIT")
                    push_immediate = action_v2 not in ("WAIT", "HOLDING", "ANOMALY")

                    # Push para RTDB (dashboard live) a cada 15 segundos ou
                    # imediatamente se houver trade.
                    current_time = time.time()
                    if push_immediate or current_time - last_dash_update >= 15:
                        await asyncio.to_thread(
                            _push_dashboard_to_firebase, r_v2, r_di, perf
                        )
                        last_dash_update = current_time

                    # Push history_30d a cada 5 minutos (300 segundos) para
                    # economizar banda.
                    if current_time - last_hist_update > 300:
                        hist = await asyncio.to_thread(history_endpoint, days=30)
                        await asyncio.to_thread(_push_history_to_firebase, hist)
                        last_hist_update = current_time

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("trade_eval_loop error")
                _set_eval_state(
                    last_error=f"{type(e).__name__}: {e}",
                    last_error_at=datetime.now().isoformat(timespec="seconds"),
                )

            await asyncio.sleep(POLL_INTERVAL_SEC)
    finally:
        _set_eval_state(loop_running=False)

DB_PATH = bhdb.sqlite_path()
REPLAY_DIR = os.environ.get("REPLAY_DIR", "replays")

# Counters for postgres write/init failures under BAR_HISTORY_BACKEND=postgres.
# Exposed in /health so the operator can tell when bars are being silently lost
# (postgres mode no longer falls back to SQLite — see migration doc §15).
_pg_write_failures: int = 0
_last_pg_write_failure: dict | None = None


def _record_pg_failure(ctx: str, exc: Exception) -> None:
    global _pg_write_failures, _last_pg_write_failure
    _pg_write_failures += 1
    _last_pg_write_failure = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "context": ctx,
        "error": f"{type(exc).__name__}: {exc}",
    }
    logger.error("bar_history PG write failed (%s): %s", ctx, exc)


_trade_engine = TradeEngine(db_path=DB_PATH)
init_timeline_table(DB_PATH)

# In-flight replay generation tracking. Per-date set protected by a single
# lock — different dates can run in parallel (separate output DBs); same-date
# concurrent requests get 409.
_replay_in_progress: set[str] = set()
_replay_progress_lock = threading.Lock()

templates = Jinja2Templates(directory="templates")

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

# WIN×WDO beta state machine — mirrors `_di_beta_state` but for the primary
# pair feeding `risk_gate`. Updated only on confirmed bar close so the
# bar-over-bar change percentage is real (multiple polls inside the same M5
# bar would otherwise compare a value against itself). `unstable=True` is a
# hard block in risk_gate (BETA_UNSTABLE reason), mirroring Miqueias upstream
# `safe_to_trade and not beta_unstable`.
_win_beta_state = {
    "current_beta": None,
    "previous_beta": None,
    "last_closed_bar_ts": None,
    "unstable": False,
}
WIN_BETA_UNSTABLE_PCT = 15.0  # |Δβ bar-over-bar| > this → unstable

# Live EG pvalue cache for eg_recalc="daily". Keyed by (date_str, eg_bars)
# so the value computed at the first qualifying bar of the day is reused for
# the rest of the session (mirrors Miqueias's gestor reference). Including
# eg_bars in the key means a hot-reload that changes the window invalidates
# the stale pvalue on the very next poll — without the operator having to
# wait for the next session. The "bar" mode bypasses this cache.
_live_eg_daily_cache: dict[tuple[str, int], float] = {}
_live_eg_daily_lock = threading.Lock()


def _compute_live_eg_pvalue(
    *,
    live_profile: dict,
    win_closes,
    wdo_closes,
    bar_ts,
    date_str: str,
) -> float | None:
    """Resolve EG pvalue honoring eg_bars (window) + eg_recalc (cadence).

    "bar"   → recompute on every bar (compute_engle_granger_pvalue still
              dedupes within the same bar via its bar_ts cache).
    "daily" → reuse the first computed value for the rest of (date_str,
              eg_bars). Only finite values are cached; None results retry on
              the next bar so a transient short-history miss self-heals.
    """
    eg_bars = int(live_profile.get("eg_bars", 0)) or 0
    if eg_bars > 0 and win_closes is not None and len(win_closes) > eg_bars:
        win_closes = win_closes[-eg_bars:]
        wdo_closes = wdo_closes[-eg_bars:]

    eg_recalc = live_profile.get("eg_recalc", "bar")
    if eg_recalc == "daily":
        cache_key = (date_str, eg_bars)
        with _live_eg_daily_lock:
            cached = _live_eg_daily_cache.get(cache_key)
        if cached is not None:
            return cached
        pvalue = compute_engle_granger_pvalue(win_closes, wdo_closes, bar_ts)
        if pvalue is not None:
            with _live_eg_daily_lock:
                _live_eg_daily_cache[cache_key] = pvalue
        return pvalue

    return compute_engle_granger_pvalue(win_closes, wdo_closes, bar_ts)


def reset_live_eg_daily_cache() -> None:
    """Test helper — drop the daily cache so the next call recomputes."""
    with _live_eg_daily_lock:
        _live_eg_daily_cache.clear()


def _compute_ols_profile_tail(win_closes, wdo_closes, *, window: int, max_bars: int):
    """Compute OLS beta/z/rho on full warmup history and return the visible tail."""
    tail = min(int(max_bars), len(win_closes), len(wdo_closes))
    beta_ols = calc_beta_ols(win_closes, wdo_closes, window=window)
    spread, z_arr, rho_arr = calc_zscore(
        win_closes, wdo_closes, beta=beta_ols, window=window, max_bars=tail
    )
    return beta_ols, spread, z_arr, rho_arr


def _entry_gate_clock_from_closed_bar(
    closed_bar_ts: int | None,
    fallback_dt: datetime,
) -> tuple[int, int]:
    """Return local bar-clock HH:MM for entry gating, falling back to poll time."""
    if closed_bar_ts is None:
        return fallback_dt.hour, fallback_dt.minute
    local_bar_dt = datetime.fromtimestamp(int(closed_bar_ts) + TIME_OFFSET)
    return local_bar_dt.hour, local_bar_dt.minute

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

def _record_timeline_data_failure(
    event: str,
    *,
    message: str | None = None,
    payload: dict | None = None,
    now_dt: datetime | None = None,
    db_path: str = DB_PATH,
) -> int | None:
    """Persist DATA failures with minute-level dedupe to avoid poll spam."""
    rowid = record_event(
        db_path,
        timestamp=timeline_ts(now_dt),
        dedupe_key=f"crit:DATA:{event}:{timeline_minute_key(now_dt)}",
        phase="DATA",
        event=event,
        status="FAILED",
        severity="error",
        message=message,
        payload_json=payload,
    )
    regime_v2._timeline_data_failed = True
    return rowid


def _record_timeline_data_recovery(
    *,
    now_dt: datetime | None = None,
    db_path: str = DB_PATH,
) -> int | None:
    """Clear a process-local DATA failure with one recovery event."""
    if not getattr(regime_v2, "_timeline_data_failed", False):
        return None
    rowid = record_event(
        db_path,
        timestamp=timeline_ts(now_dt),
        dedupe_key=f"crit:DATA:DATA_RECOVERED:{timeline_minute_key(now_dt)}",
        phase="DATA",
        event="DATA_RECOVERED",
        status="OK",
        severity="info",
        message="MT5 data path recovered",
    )
    regime_v2._timeline_data_failed = False
    return rowid


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
def init_bar_history(db_path: str = DB_PATH) -> None:
    """Idempotent migration for the bar_history table.

    Schema mirrors the columns written by save_bar_history. timestamp is the
    PRIMARY KEY dedups when MT5 reissues an old M5 bar.
    """
    backend = bhdb.get_backend()
    if backend == "postgres":
        # Fail-fast: if schema init fails in postgres mode, every subsequent
        # save_bar_history will lose data silently (no SQLite fallback in this
        # mode). Surface the failure at startup instead.
        bhdb.init_schema(backend="postgres")
        logger.info("bar_history backend=postgres — Postgres schema initialised")
        return

    conn = sqlite3.connect(db_path, timeout=10.0)
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS bar_history (
                timestamp   INTEGER PRIMARY KEY,
                date_str    TEXT NOT NULL,
                bar_time    TEXT NOT NULL,
                win_price   REAL,
                wdo_price   REAL,
                di_price    REAL,
                spread_wdo  REAL,
                spread_di   REAL,
                z_wdo       REAL,
                z_di        REAL,
                nwe_center  REAL,
                nwe_upper   REAL,
                nwe_lower   REAL,
                nwe_is_up   INTEGER
            )
        ''')
        # Replay indicators + OHLC required for parity. Idempotent ALTERs ignore
        # only the expected duplicate-column case.
        for ddl in (
            "ALTER TABLE bar_history ADD COLUMN eg_pvalue REAL",
            "ALTER TABLE bar_history ADD COLUMN rho REAL",
            "ALTER TABLE bar_history ADD COLUMN rho_level INTEGER",
            "ALTER TABLE bar_history ADD COLUMN beta_value REAL",
            "ALTER TABLE bar_history ADD COLUMN beta_delta_pct REAL",
            "ALTER TABLE bar_history ADD COLUMN win_open REAL",
            "ALTER TABLE bar_history ADD COLUMN win_high REAL",
            "ALTER TABLE bar_history ADD COLUMN win_low REAL",
            "ALTER TABLE bar_history ADD COLUMN wdo_open REAL",
            "ALTER TABLE bar_history ADD COLUMN wdo_high REAL",
            "ALTER TABLE bar_history ADD COLUMN wdo_low REAL",
            "ALTER TABLE bar_history ADD COLUMN di_open REAL",
            "ALTER TABLE bar_history ADD COLUMN di_high REAL",
            "ALTER TABLE bar_history ADD COLUMN di_low REAL",
        ):
            try:
                c.execute(ddl)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        conn.commit()
    finally:
        conn.close()

    if backend == "dual":
        try:
            bhdb.init_schema(backend="postgres")
            logger.info("bar_history backend=%s — Postgres mirror initialised", backend)
        except Exception as exc:
            # Dual mode: keep SQLite as source of truth even if PG mirror is
            # offline. Just record the failure so /health surfaces it.
            _record_pg_failure("init_schema(postgres)", exc)


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
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
    init_bar_history(db_path)

init_db()


# ─── Helpers ─────────────────────────────────────────────────────────────────
SESSION_START = 8 * 60 + 50     # 08:50
SESSION_END   = 18 * 60 + 20    # 18:20


def _fetch_ohlc(symbol: str, count: int):
    """Return (closes, opens, highs, lows, times) numpy arrays for `count` M5 bars.

    Thin wrapper around fetch_rates() that flattens the MT5 structured array
    into the per-field arrays callers want. Failure semantics mirror
    fetch_bars: returns a 5-tuple of Nones on missing data.
    """
    rates = fetch_rates(symbol, count)
    if rates is None:
        return None, None, None, None, None
    closes = np.array([r["close"] for r in rates], dtype=float)
    opens = np.array([r["open"] for r in rates], dtype=float)
    highs = np.array([r["high"] for r in rates], dtype=float)
    lows = np.array([r["low"] for r in rates], dtype=float)
    times = np.array([r["time"] for r in rates], dtype=np.int64)
    return closes, opens, highs, lows, times

TF_NAMES = {
    mt5.TIMEFRAME_M1: "M1", mt5.TIMEFRAME_M5: "M5",
    mt5.TIMEFRAME_M15: "M15", mt5.TIMEFRAME_M30: "M30",
    mt5.TIMEFRAME_H1: "H1", mt5.TIMEFRAME_H4: "H4",
}


def save_bar_history(timestamp, date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up, eg_pvalue=None, rho=None, rho_level=None, beta_value=None, beta_delta_pct=None, win_open=None, win_high=None, win_low=None, wdo_open=None, wdo_high=None, wdo_low=None, di_open=None, di_high=None, di_low=None, db_path: str = DB_PATH):
    nwe_is_up_val = int(bool(nwe_is_up)) if nwe_is_up is not None else None
    rho_level_val = int(rho_level) if rho_level is not None else None

    row = {
        "timestamp": int(timestamp),
        "date_str": date_str,
        "bar_time": bar_time,
        "win_price": win_price,
        "win_open": win_open,
        "win_high": win_high,
        "win_low": win_low,
        "wdo_price": wdo_price,
        "wdo_open": wdo_open,
        "wdo_high": wdo_high,
        "wdo_low": wdo_low,
        "di_price": di_price,
        "di_open": di_open,
        "di_high": di_high,
        "di_low": di_low,
        "spread_wdo": spread_wdo,
        "spread_di": spread_di,
        "z_wdo": z_wdo,
        "z_di": z_di,
        "nwe_center": nwe_center,
        "nwe_upper": nwe_upper,
        "nwe_lower": nwe_lower,
        "nwe_is_up": nwe_is_up_val,
        "eg_pvalue": eg_pvalue,
        "rho": rho,
        "rho_level": rho_level_val,
        "beta_value": beta_value,
        "beta_delta_pct": beta_delta_pct,
    }
    backend = bhdb.get_backend()

    # In postgres mode, PG is the only writer. The wrapper's merge mode
    # reproduces the COALESCE semantics this function used inline.
    if backend == "postgres":
        try:
            bhdb.upsert_bar(row, backend="postgres", mode="merge")
        except Exception as exc:
            _record_pg_failure(f"save_bar_history ts={int(timestamp)}", exc)
        return

    sqlite_ok = False
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        c = conn.cursor()
        # COALESCE on indicator/OHLC columns so they get filled in by the poll
        # where the bar is the closed-bar (history[-2]); subsequent re-saves of
        # the same bar arrive with NULL indicators and must not erase them.
        c.execute('''
            INSERT INTO bar_history
            (timestamp, date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up, eg_pvalue, rho, rho_level, beta_value, beta_delta_pct, win_open, win_high, win_low, wdo_open, wdo_high, wdo_low, di_open, di_high, di_low)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(timestamp) DO UPDATE SET
                wdo_price = COALESCE(bar_history.wdo_price, excluded.wdo_price),
                di_price = COALESCE(bar_history.di_price, excluded.di_price),
                z_di = COALESCE(excluded.z_di, bar_history.z_di),
                eg_pvalue = COALESCE(bar_history.eg_pvalue, excluded.eg_pvalue),
                rho = COALESCE(bar_history.rho, excluded.rho),
                rho_level = COALESCE(bar_history.rho_level, excluded.rho_level),
                beta_value = COALESCE(bar_history.beta_value, excluded.beta_value),
                beta_delta_pct = COALESCE(bar_history.beta_delta_pct, excluded.beta_delta_pct),
                win_open = COALESCE(bar_history.win_open, excluded.win_open),
                win_high = COALESCE(bar_history.win_high, excluded.win_high),
                win_low  = COALESCE(bar_history.win_low,  excluded.win_low),
                wdo_open = COALESCE(bar_history.wdo_open, excluded.wdo_open),
                wdo_high = COALESCE(bar_history.wdo_high, excluded.wdo_high),
                wdo_low  = COALESCE(bar_history.wdo_low,  excluded.wdo_low),
                di_open  = COALESCE(bar_history.di_open,  excluded.di_open),
                di_high  = COALESCE(bar_history.di_high,  excluded.di_high),
                di_low   = COALESCE(bar_history.di_low,   excluded.di_low)
        ''', (int(timestamp), date_str, bar_time, win_price, wdo_price, di_price, spread_wdo, spread_di, z_wdo, z_di, nwe_center, nwe_upper, nwe_lower, nwe_is_up_val, eg_pvalue, rho, rho_level_val, beta_value, beta_delta_pct, win_open, win_high, win_low, wdo_open, wdo_high, wdo_low, di_open, di_high, di_low))
        conn.commit()
        conn.close()
        sqlite_ok = True
    except Exception as e:
        print(f"[ERRO DB] falha ao salvar bar_history: {e}")

    # `dual`: mirror to PG only after the authoritative SQLite write
    # committed. The sqlite_ok guard preserves rollback-by-env: if SQLite
    # rejects a bar, PG must not hold it either.
    if sqlite_ok and backend == "dual":
        try:
            bhdb.upsert_bar(row, backend="postgres", mode="merge")
        except Exception as exc:
            _record_pg_failure(f"dual-write ts={int(timestamp)}", exc)


def _persist_closed_bars(history, db_path: str = DB_PATH) -> int:
    """Persist closed bars from a live history payload to bar_history.

    Skips the last entry (it is the still-forming bar; saving it would freeze
    a not-yet-final value into the non-repainting source-of-truth). Returns the
    number of save attempts (independent of insert/upsert outcome).

    The function reads the unfiltered z values (z_unfiltered_*) so that
    load_bar_history's NWE re-application is consistent across writes/reads.
    """
    if not history or len(history) < 2:
        return 0
    saved = 0
    for entry in history[:-1]:
        try:
            local_ts = int(datetime.strptime(
                f"{entry['date']} {entry['bar_time']}", "%Y-%m-%d %H:%M"
            ).timestamp())
            save_bar_history(
                timestamp=local_ts,
                date_str=entry["date"],
                bar_time=entry["bar_time"],
                win_price=entry.get("win_price"),
                wdo_price=entry.get("wdo_price"),
                di_price=entry.get("di_price"),
                spread_wdo=entry.get("spread"),
                spread_di=None,
                z_wdo=entry.get("z_unfiltered_wdo", entry.get("z")),
                z_di=entry.get("z_unfiltered_di", entry.get("z_di", 0.0)),
                nwe_center=entry.get("nwe"),
                nwe_upper=entry.get("nweUpper"),
                nwe_lower=entry.get("nweLower"),
                nwe_is_up=entry.get("isUp"),
                eg_pvalue=entry.get("eg_pvalue"),
                rho=entry.get("rho"),
                rho_level=entry.get("rho_level"),
                beta_value=entry.get("beta_value"),
                beta_delta_pct=entry.get("beta_delta_pct"),
                win_open=entry.get("win_open"),
                win_high=entry.get("win_high"),
                win_low=entry.get("win_low"),
                wdo_open=entry.get("wdo_open"),
                wdo_high=entry.get("wdo_high"),
                wdo_low=entry.get("wdo_low"),
                di_open=entry.get("di_open"),
                di_high=entry.get("di_high"),
                di_low=entry.get("di_low"),
                db_path=db_path,
            )
            saved += 1
        except Exception as exc:
            print(f"[ERRO DB] persist bar_history skip: {exc}")
    return saved

def load_bar_history(days=30, db_path: str = DB_PATH):
    try:
        # `dual`/`sqlite` keep the in-process SQLite path so the db_path arg
        # (used by tests) still applies. PG rows are dicts with the same
        # column names, so the row-loop below is backend-agnostic.
        if bhdb.get_backend() == "postgres":
            rows = bhdb.select_window(days=days, backend="postgres")
        else:
            conn = sqlite3.connect(db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            ts_limit = int(time.time()) - days * 86400
            c.execute("SELECT * FROM bar_history WHERE timestamp >= ? ORDER BY timestamp ASC", (ts_limit,))
            rows = c.fetchall()
            conn.close()

        from datetime import datetime
        history = []
        for i, r in enumerate(rows):
            dt_time = datetime.strptime(r["bar_time"], "%H:%M")
            z_wdo = r["z_wdo"]
            z_di = r["z_di"] or 0.0
            win_price = r["win_price"]
            wdo_price = r["wdo_price"]
            di_price = r["di_price"]
            
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
            
            history.append({
                "i": i,
                "z": r["z_wdo"],
                "z_di": r["z_di"],
                "spread": r["spread_wdo"],
                "bar_time": r["bar_time"],
                "date": r["date_str"],
                "t_min": dt_time.hour * 60 + dt_time.minute,
                "win_price": win_price,
                "wdo_price": wdo_price,
                "di_price": di_price,
                
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
                # TASK-8 Slice A: replay-required indicators. May be NULL on
                # bars persisted before the migration ran or before the live
                # poll attached them; replay treats NULLs as MISSING_*.
                "eg_pvalue": r["eg_pvalue"] if "eg_pvalue" in r.keys() else None,
                "rho": r["rho"] if "rho" in r.keys() else None,
                "rho_level": r["rho_level"] if "rho_level" in r.keys() else None,
                "beta_value": r["beta_value"] if "beta_value" in r.keys() else None,
                "beta_delta_pct": r["beta_delta_pct"] if "beta_delta_pct" in r.keys() else None,
            })
        return history
    except Exception as e:
        print(f"[ERRO DB] falha ao carregar bar_history: {e}")
        return []

def do_backfill_if_empty():
    try:
        # Count via wrapper so postgres mode looks at the right DB. `dual`
        # reads SQLite per the wrapper contract.
        if bhdb.get_backend() == "postgres":
            count = bhdb.count_rows(backend="postgres")
        else:
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
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

def _build_history(
    bar_times,
    z_arr,
    spread_arr,
    z_v1_arr=None,
    win_prices=None,
    nwe_data=None,
    di_map=None,
    wdo_prices=None,
    di_prices=None,
    di_price_map=None,
    win_opens=None,
    win_highs=None,
    win_lows=None,
    wdo_opens=None,
    wdo_highs=None,
    wdo_lows=None,
    di_opens=None,
    di_highs=None,
    di_lows=None,
    di_ohlc_map=None,
):
    """Build filtered session history from bar data, including NWE and DI."""
    n = len(z_arr)
    v1_len = len(z_v1_arr) if z_v1_arr is not None else 0
    win_len = len(win_prices) if win_prices is not None else 0
    wdo_len = len(wdo_prices) if wdo_prices is not None else 0
    di_len = len(di_prices) if di_prices is not None else 0

    # Per-array OHLC indexing aligns with the corresponding close array (same
    # length as win_prices / wdo_prices / di_prices). Missing arrays => no OHLC
    # attached for that leg (graceful degradation; load_bar_history reads NULLs).
    def _pick(arr, idx):
        if arr is None:
            return None
        if 0 <= idx < len(arr):
            return float(arr[idx])
        return None

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
            win_open = _pick(win_opens, win_idx)
            win_high = _pick(win_highs, win_idx)
            win_low = _pick(win_lows, win_idx)
            if win_open is not None: entry["win_open"] = win_open
            if win_high is not None: entry["win_high"] = win_high
            if win_low is not None: entry["win_low"] = win_low

        if wdo_prices is not None:
            wdo_idx = i - (n - wdo_len)
            if 0 <= wdo_idx < wdo_len:
                entry["wdo_price"] = float(wdo_prices[wdo_idx])
            wdo_open = _pick(wdo_opens, wdo_idx)
            wdo_high = _pick(wdo_highs, wdo_idx)
            wdo_low = _pick(wdo_lows, wdo_idx)
            if wdo_open is not None: entry["wdo_open"] = wdo_open
            if wdo_high is not None: entry["wdo_high"] = wdo_high
            if wdo_low is not None: entry["wdo_low"] = wdo_low

        di_price_val = None
        di_open_val = di_high_val = di_low_val = None
        if di_prices is not None:
            di_idx = i - (n - di_len)
            if 0 <= di_idx < di_len:
                di_price_val = float(di_prices[di_idx])
            di_open_val = _pick(di_opens, di_idx)
            di_high_val = _pick(di_highs, di_idx)
            di_low_val = _pick(di_lows, di_idx)
        elif di_price_map:
            di_price_val = di_price_map.get(local_ts)
        if di_ohlc_map and (di_open_val is None or di_high_val is None or di_low_val is None):
            # Fallback: when caller doesn't pass DI arrays directly, look up
            # per-timestamp from the cache map populated by /api/di-regime.
            cached = di_ohlc_map.get(local_ts)
            if cached:
                co, ch, cl = cached
                if di_open_val is None and co is not None: di_open_val = float(co)
                if di_high_val is None and ch is not None: di_high_val = float(ch)
                if di_low_val is None and cl is not None: di_low_val = float(cl)
        if di_price_val is not None:
            entry["di_price"] = float(di_price_val)
        if di_open_val is not None: entry["di_open"] = di_open_val
        if di_high_val is not None: entry["di_high"] = di_high_val
        if di_low_val is not None: entry["di_low"] = di_low_val
            
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


def _closed_di_z_from_cache(closed_bar_ts: int | None, fallback: float = 0.0) -> float:
    """Return WINxDI z-score aligned to the last closed WIN/WDO bar."""
    if closed_bar_ts is None or not _di_cache:
        return float(fallback)

    history = _di_cache.get("history") or []
    try:
        local_dt = datetime.fromtimestamp(int(closed_bar_ts) + TIME_OFFSET)
        target_date = local_dt.strftime("%Y-%m-%d")
        target_time = local_dt.strftime("%H:%M")
    except Exception:
        target_date = target_time = None

    for entry in reversed(history):
        if entry.get("date") == target_date and entry.get("bar_time") == target_time:
            return float(entry.get("z", fallback) or 0.0)

    # If the DI cache is fresh but timestamp matching fails, prefer its last
    # closed row over current_z, which may belong to the open M5 candle.
    if len(history) >= 2:
        return float(history[-2].get("z", fallback) or 0.0)
    if history:
        return float(history[-1].get("z", fallback) or 0.0)
    return float(fallback)


def _build_response(current_z, current_rho, half_life, strength,
                     beta_ols, beta_ref_20d, beta_delta_pct, beta_change_pct, beta_unstable,
                     rho_status, beta_status, safe_to_trade,
                     trade_result, history, signal, version="v2_kalman"):
    """Build the common response dict for the V2 regime endpoint.

    ``signal`` must be a dict produced by ``get_signal`` from the caller, so qty_*
    fields are sized against the same spread_sd/beta used elsewhere in the request.
    """
    now = datetime.now()
    return {
        "current_z":       round(current_z, 3),
        "current_rho":     round(current_rho, 3),
        "half_life":       round(half_life, 2) if half_life != float("inf") else 0.0,
        "signal":          signal,
        "strength":        round(strength, 1),
        "beta_ols":        round(beta_ols, 4),
        "beta_ref_5d":     round(beta_ols, 4),
        "beta_drift_5d":   0.0,
        "beta_ref_20d":    round(beta_ref_20d, 4),
        "beta_delta_pct":  round(beta_delta_pct, 2),
        "beta_change_pct": round(beta_change_pct, 2),
        "beta_unstable":   beta_unstable,
        "risk_stats_scope": "live" if LIVE_ORDERS else "all",
        "risk_trades_today": trade_result.get("risk_trades_today"),
        "risk_daily_pnl_brl": trade_result.get("risk_daily_pnl_brl"),
        "risk_minutes_since_last_loss": trade_result.get("risk_minutes_since_last_loss"),
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
            "window":     "KALMAN",
            "timeframe":  TF_NAMES.get(TIMEFRAME, str(TIMEFRAME)),
            "hmm_regime": hmm.current_hmm_regime,
            "live_orders_enabled": bool(LIVE_ORDERS),
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

@app.get("/api/v2/regime")
@_serialized_regime_call
def regime_v2():
    """V2 endpoint — Kalman-based regime monitoring + Johansen gate."""
    if not connect_mt5():
        _record_timeline_data_failure(
            "MT5_DISCONNECTED",
            message="connect_mt5() returned False",
            now_dt=datetime.now(),
        )
        return {"error": "MT5 não disponível.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": [], "trades_today": []}

    needed_a = max(KALMAN_BURN_IN, JOH_WINDOW + 10)
    closes_a, opens_a, highs_a, lows_a, times_a = _fetch_ohlc(SYMBOL_A, needed_a)
    closes_b, opens_b, highs_b, lows_b, times_b = _fetch_ohlc(SYMBOL_B, needed_a)

    if closes_a is None or closes_b is None:
        _record_timeline_data_failure(
            "BARS_FETCH_FAILED",
            message="fetch_bars returned no data",
            payload={
                "symbol_a": SYMBOL_A,
                "symbol_b": SYMBOL_B,
                "symbol_a_ok": closes_a is not None,
                "symbol_b_ok": closes_b is not None,
            },
            now_dt=datetime.now(),
        )
        return {"error": "Sem dados.", "current_z": 0, "signal": get_signal(0, hmm_state=hmm.current_hmm_regime), "history": [], "trades_today": []}
    _record_timeline_data_recovery(now_dt=datetime.now())

    # ── Live runtime profile (hot-reloaded each poll) ──
    # Operator can flip runtime tunables via POST /api/runtime-config and the
    # next poll picks them up without a restart. Loaded early so calc_zscore /
    # get_signal can read window/z_entry/z_attention from the same source the
    # risk gate uses below. Falls back to DEFAULTS when the on-disk file is
    # malformed so a bad save doesn't 500 the engine.
    try:
        live_profile = runtime_config.get_profile("live")
    except ValueError:
        live_profile = copy.deepcopy(runtime_config.DEFAULTS["live"])

    min_len = min(len(closes_a), len(closes_b))
    ac, bc, tc = closes_a[-min_len:], closes_b[-min_len:], times_a[-min_len:]
    ao, ah, al = opens_a[-min_len:], highs_a[-min_len:], lows_a[-min_len:]
    bo, bh, bl = opens_b[-min_len:], highs_b[-min_len:], lows_b[-min_len:]
    ols_ac, ols_bc = ac, bc

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
        ao, ah, al = ao[-BARS:], ah[-BARS:], al[-BARS:]
        bo, bh, bl = bo[-BARS:], bh[-BARS:], bl[-BARS:]
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

    # OLS beta on the current window (rho computed here is beta-independent;
    # z_v1 is the slow OLS-based z exposed to the dashboard alongside the fast Kalman z).
    profile_window = int(live_profile["window"])
    beta_ols_real, spread_v1, z_v1_arr, rho_arr = _compute_ols_profile_tail(
        ols_ac, ols_bc, window=profile_window, max_bars=len(ac)
    )
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
    # `safe_to_trade` here is rho+beta sanity ONLY — it powers the dashboard's
    # "ρ ou Δβ fora da zona verde" banner (App.jsx:707). It does NOT include
    # EG/session/anomaly/bar-close — those live in `risk_gate.allowed` (also
    # surfaced as `regime_health.gate_allowed` below).
    safe_to_trade = bool(rho_status["level"] < 2 and beta_status_d["level"] < 2)
    nwe_is_up_now = bool(nwe_is_up_arr[-1])
    nwe_upper_now = float(nwe_upper[-1])
    nwe_lower_now = float(nwe_lower[-1])

    # Trade engine (Consenso WDO + DI + NWE filters)
    now_dt = datetime.now()
    z_di_live = _di_cache.get("current_z", 0.0) if _di_cache else 0.0

    # ── Bar-close gate: entries only on confirmed bar close ──────────
    # `copy_rates_from_pos(symbol, TF, 0, count)` returns the in-formation bar
    # at index [-1]. Entry decisions must use the last *closed* bar (index
    # [-2]) — both for the transition detector AND for the inputs fed to
    # risk_gate/evaluate. Otherwise we'd judge entries on a bar that has only
    # ~1 tick of life and break backtest parity.
    closed_bar_ts = int(tc[-2]) if len(tc) >= 2 else None
    bar_close_confirmed = False
    if closed_bar_ts is not None:
        last_known_closed = getattr(regime_v2, "_last_closed_bar_ts", None)
        if last_known_closed is None:
            # Cold start: capture the current closed bar but don't fire entry
            # this poll — wait for the NEXT confirmed close. Otherwise a
            # restart mid-session would fire entries at an arbitrary moment.
            regime_v2._last_closed_bar_ts = closed_bar_ts
        elif last_known_closed != closed_bar_ts:
            bar_close_confirmed = True
            regime_v2._last_closed_bar_ts = closed_bar_ts
            # Force DI cache refresh on confirmed close (prevents race in consensus)
            di_regime(force=True)

    # Re-fetch DI cache after possible forced update
    z_di_live = _di_cache.get("current_z", 0.0) if _di_cache else 0.0

    # ── Closed-bar values fed to the gate and the engine ──
    # Dashboard payload below keeps live ([-1]) values for display; only entry
    # decisions read from [-2]. Exit checks still see live prices (win_price /
    # wdo_price below) so intra-bar SL/TP fires correctly.
    if len(z_scores) >= 2 and len(rho_arr) >= 2 and len(kf_betas) >= 2:
        z_wdo_closed = float(z_scores[-2])
        rho_closed = float(rho_arr[-2])
        rho_level_closed = get_rho_status(rho_closed)["level"]
        beta_closed = float(kf_betas[-2])
        beta_delta_pct_closed = (
            (beta_closed - beta_ref_20d) / abs(beta_ref_20d) * 100
            if beta_ref_20d != 0 else 0.0
        )
        nwe_is_up_closed = bool(nwe_is_up_arr[-2])
        nwe_upper_closed = float(nwe_upper[-2])
        nwe_lower_closed = float(nwe_lower[-2])
        eg_input_a, eg_input_b = ac[:-1], bc[:-1]
        z_di_closed = _closed_di_z_from_cache(closed_bar_ts, fallback=float(z_di_live))
        entry_win_price_closed = float(ac[-2])
        entry_wdo_price_closed = float(bc[-2])
    else:
        # Insufficient history for closed-bar slice — fall back to live values
        # but bar_close_confirmed will be False so no entries fire anyway.
        z_wdo_closed = current_z
        z_di_closed = float(z_di_live)
        rho_closed = current_rho
        rho_level_closed = rho_status["level"]
        beta_closed = beta_current
        beta_delta_pct_closed = beta_delta_pct
        nwe_is_up_closed = nwe_is_up_now
        nwe_upper_closed = nwe_upper_now
        nwe_lower_closed = nwe_lower_now
        eg_input_a, eg_input_b = ac, bc
        entry_win_price_closed = float(ac[-1])
        entry_wdo_price_closed = float(bc[-1])

    # ── Operational risk stats (TASK-3 AC #11) ──
    today_str = now_dt.strftime("%Y-%m-%d")
    live_risk_only = bool(LIVE_ORDERS)
    trades_today_count = _trade_engine.count_trades_today(
        today_str,
        live_only=live_risk_only,
    )
    daily_pnl_brl = _trade_engine.pnl_today(today_str, live_only=live_risk_only)
    minutes_since_last_loss = _trade_engine.minutes_since_last_loss(
        now=now_dt,
        live_only=live_risk_only,
    )

    # live_profile already loaded above (right after the data-fetch guard) so
    # calc_zscore and other early consumers can read the same source as the
    # risk gate. Bind the strategies subset here, where it's first used.
    live_eg_strategies = live_profile["eg_strategies"]

    # ── Centralized risk gate ──
    eg_pvalue = _compute_live_eg_pvalue(
        live_profile=live_profile,
        win_closes=eg_input_a,
        wdo_closes=eg_input_b,
        bar_ts=closed_bar_ts,
        date_str=today_str,
    )

    # WIN beta state machine — only advance on confirmed bar close so the
    # bar-over-bar change is real. `previous_beta` is None on cold start;
    # `beta_change_pct_closed` stays 0 for the first closed bar of the
    # session and unstable=False (no prior to compare against).
    beta_change_pct_closed = 0.0
    if (
        bar_close_confirmed
        and closed_bar_ts is not None
        and closed_bar_ts != _win_beta_state["last_closed_bar_ts"]
    ):
        prev_beta = _win_beta_state["current_beta"]
        if prev_beta is not None and prev_beta != 0:
            beta_change_pct_closed = (beta_closed - prev_beta) / abs(prev_beta) * 100
            _win_beta_state["unstable"] = abs(beta_change_pct_closed) > WIN_BETA_UNSTABLE_PCT
        else:
            _win_beta_state["unstable"] = False
        _win_beta_state["previous_beta"] = prev_beta
        _win_beta_state["current_beta"] = beta_closed
        _win_beta_state["last_closed_bar_ts"] = closed_bar_ts
    win_beta_unstable = bool(_win_beta_state["unstable"])
    gate_hour, gate_minute = _entry_gate_clock_from_closed_bar(closed_bar_ts, now_dt)

    def _build_gate(trades_today, daily_pnl, mins_since_loss):
        # Closure captures all market-side inputs, which don't change
        # across the pre/post-evaluate boundary. Only the operational
        # stats vary (when an exit fires inside evaluate).
        return risk_gate(
            z_wdo=z_wdo_closed, z_di=z_di_closed,
            rho_level=rho_level_closed,
            beta_delta_pct=beta_delta_pct_closed,
            eg_pvalue=eg_pvalue,
            hour=gate_hour, minute=gate_minute,
            bar_close_confirmed=bar_close_confirmed,
            trades_today_count=trades_today,
            daily_pnl_brl=daily_pnl,
            minutes_since_last_loss=mins_since_loss,
            # Real check: connect_mt5() at endpoint top guarantees a connection
            # was alive earlier in the poll, but the terminal can drop between
            # there and here. terminal_info() returns None when disconnected.
            mt5_connected=mt5.terminal_info() is not None,
            joh_open=joh_open,
            hmm_state=hmm.current_hmm_regime,
            eg_threshold=live_profile["eg_threshold"],
            rho_breakdown_level=live_profile["rho_breakdown_level"],
            beta_delta_max=live_profile["beta_delta_max"],
            z_anomaly=live_profile["z_anomaly"],
            beta_unstable=win_beta_unstable,
            entry_start_h=int(live_profile["entry_start_h"]),
            entry_start_m=int(live_profile["entry_start_m"]),
            entry_end_h=int(live_profile["entry_end_h"]),
            entry_end_m=int(live_profile["entry_end_m"]),
        )

    pre_entry_gate = _build_gate(trades_today_count, daily_pnl_brl, minutes_since_last_loss)

    trade_result = _trade_engine.evaluate(
        z_wdo=z_wdo_closed, z_di=z_di_closed,
        win_price=float(ac[-1]), wdo_price=float(bc[-1]),  # LIVE for exit checks
        entry_win_price=entry_win_price_closed, entry_wdo_price=entry_wdo_price_closed,
        rho=rho_closed, gate=pre_entry_gate, hmm_state=hmm.current_hmm_regime,
        hour=now_dt.hour, minute=now_dt.minute, beta_value=beta_closed,
        nwe_is_up=nwe_is_up_closed, nwe_upper=nwe_upper_closed, nwe_lower=nwe_lower_closed,
        closed_bar_ts=closed_bar_ts,
        now_dt=now_dt,
        eg_strategies=live_eg_strategies,
        force_close_h=int(live_profile["force_close_h"]),
        force_close_m=int(live_profile["force_close_m"]),
        engine_params=live_profile,
        live_only=live_risk_only,
    )

    # Refresh the gate post-evaluate so the published payload reflects
    # any STOP_LOSS / TARGET that fired during this poll. Without this,
    # regime_health.gate_allowed could publish stale `true` while a
    # strategy result correctly carries LOSS_COOLDOWN. Engine state is
    # already committed to SQLite by _close_trade — subsequent queries
    # see fresh values. (Codex round-5 medium.)
    post_trades_today_count = _trade_engine.count_trades_today(
        today_str,
        live_only=live_risk_only,
    )
    post_daily_pnl_brl = _trade_engine.pnl_today(today_str, live_only=live_risk_only)
    post_minutes_since_last_loss = _trade_engine.minutes_since_last_loss(
        now=now_dt,
        live_only=live_risk_only,
    )
    gate = _build_gate(
        post_trades_today_count,
        post_daily_pnl_brl,
        post_minutes_since_last_loss,
    )

    if (
        bar_close_confirmed
        and closed_bar_ts is not None
        and closed_bar_ts != getattr(regime_v2, "_last_emitted_bar_ts", None)
    ):
        emit_closed_bar_timeline(
            db_path=DB_PATH,
            closed_bar_ts=closed_bar_ts,
            gate=pre_entry_gate,
            trade_result=trade_result,
            z_wdo=z_wdo_closed,
            z_di=z_di_closed,
            rho=rho_closed,
            rho_level=rho_level_closed,
            beta_delta_pct=beta_delta_pct_closed,
            eg_pvalue=eg_pvalue,
            joh_open=joh_open,
            mt5_connected=mt5.terminal_info() is not None,
            trades_today_count=trades_today_count,
            daily_pnl_brl=daily_pnl_brl,
            minutes_since_last_loss=minutes_since_last_loss,
            now_dt=now_dt,
            eg_threshold=live_profile["eg_threshold"],
            rho_breakdown_level=live_profile["rho_breakdown_level"],
            beta_delta_max=live_profile["beta_delta_max"],
            z_anomaly=live_profile["z_anomaly"],
        )
        regime_v2._last_emitted_bar_ts = closed_bar_ts

    # History — Statefully loaded from DB to prevent repainting
    db_hist = load_bar_history(days=2) # Load last 2 days is enough for dashboard
    today_str = datetime.now().strftime("%Y-%m-%d")
    db_hist = [h for h in db_hist if h.get("date") == today_str]  # Only today for live view
    
    di_map = {}
    di_price_map = {}
    di_ohlc_map = {}
    if _di_cache and "history" in _di_cache:
        for dh in _di_cache["history"]:
            dt_str = dh.get("date", "") + " " + dh.get("bar_time", "")
            try:
                local_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                local_ts = int(local_dt.timestamp())
                di_map[local_ts] = dh.get("z", 0.0)
                if dh.get("di_price") is not None:
                    di_price_map[local_ts] = dh.get("di_price")
                if any(dh.get(k) is not None for k in ("di_open", "di_high", "di_low")):
                    di_ohlc_map[local_ts] = (
                        dh.get("di_open"),
                        dh.get("di_high"),
                        dh.get("di_low"),
                    )
            except Exception:
                pass

    live_history = _build_history(
        tc[-20:], z_scores[-20:], spreads[-20:],
        win_prices=ac[-20:], wdo_prices=bc[-20:],
        win_opens=ao[-20:], win_highs=ah[-20:], win_lows=al[-20:],
        wdo_opens=bo[-20:], wdo_highs=bh[-20:], wdo_lows=bl[-20:],
        nwe_data=(nwe_line[-20:], nwe_upper[-20:], nwe_lower[-20:], nwe_is_up_arr[-20:]),
        di_map=di_map, di_price_map=di_price_map, di_ohlc_map=di_ohlc_map,
    )
    
    if db_hist and live_history:
        # Append the current open bar (and any missing bars not yet in DB)
        last_db_ts = db_hist[-1]["date"] + " " + db_hist[-1]["bar_time"]
        for lh in live_history:
            lh_ts = lh["date"] + " " + lh["bar_time"]
            if lh_ts > last_db_ts:
                db_hist.append(lh)
        history = db_hist
    else:
        history = _build_history(
            tc, z_scores, spreads, win_prices=ac, wdo_prices=bc,
            win_opens=ao, win_highs=ah, win_lows=al,
            wdo_opens=bo, wdo_highs=bh, wdo_lows=bl,
            nwe_data=(nwe_line, nwe_upper, nwe_lower, nwe_is_up_arr),
            di_map=di_map, di_price_map=di_price_map, di_ohlc_map=di_ohlc_map,
        )

    # Persist closed bars from the FULL `history` (not just live_history).
    # On a midday cold start db_hist is empty → fallback branch returns the
    # full session in `history`; persisting only the last 20 (live_history)
    # would leave older candles unwritten and the next poll's merge branch
    # would shrink the dashboard. Re-persistence of already-stored rows is
    # mostly no-op; missing WDO/DI prices can still be
    # filled on conflict. The trailing open bar is skipped inside
    # _persist_closed_bars.
    #
    # TASK-8 Slice A: attach the closed-bar indicators (the same values fed to
    # risk_gate above) to history[-2] so save_bar_history persists them. Older
    # entries already had their chance in past polls; they keep whatever they
    # had (COALESCE in save_bar_history protects them from NULL overwrites).
    if len(history) >= 2:
        history[-2]["eg_pvalue"] = eg_pvalue
        history[-2]["rho"] = rho_closed
        history[-2]["rho_level"] = rho_level_closed
        history[-2]["beta_value"] = beta_closed
        history[-2]["beta_delta_pct"] = beta_delta_pct_closed
    _persist_closed_bars(history)

    sig_data = get_signal(
        current_z,
        current_spread_sd,
        beta_current,
        z_entry=float(live_profile["z_entry"]),
        z_attention=float(live_profile["z_attention"]),
        hmm_state=hmm.current_hmm_regime,
    )

    res = _build_response(
        current_z, current_rho, 0, min(100.0, abs(current_z) / 4.0 * 100.0),
        beta_current, beta_ref_20d, beta_delta_pct, beta_change_pct_closed, win_beta_unstable,
        rho_status, beta_status_d, safe_to_trade,
        trade_result, history, signal=sig_data, version="v2_kalman",
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
    res["trades_today"] = _trade_engine.get_trades_for_date(
        datetime.now().strftime("%Y-%m-%d")
    )
    res["risk_gate"] = gate
    # Mirror the full gate decision inside regime_health so the dashboard has
    # one obvious place to read it. `safe_to_trade` is intentionally kept as
    # the rho+beta-only flag (its banner depends on that semantic).
    if "regime_health" in res:
        res["regime_health"]["gate_allowed"] = gate["allowed"]
        res["regime_health"]["gate_reasons"] = list(gate["reasons"])
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
def di_regime(force: bool = False):
    """WIN×DI pair trading — Johansen z-score + gate."""
    global _di_cache, _di_cache_ts, _di_beta_state, _di_coint_cache

    if not force and time.time() - _di_cache_ts < CACHE_TTL and _di_cache:
        return _di_cache

    if not connect_mt5():
        return {"error": "MT5 nao disponivel.", "current_z": 0, "signal": _get_di_signal(0), "history": []}

    # Fetch data — need enough for Kalman + Johansen gate
    needed = max(DI_BARS, DI_BETA_REF_BARS, JOH_WINDOW) + DI_KALMAN_W + 10
    closes_win, opens_win, highs_win, lows_win, times_win = _fetch_ohlc(SYMBOL_A, needed)
    closes_di, opens_di, highs_di, lows_di, times_di = _fetch_ohlc(DI_SYMBOL, needed)

    if closes_win is None or closes_di is None:
        return {"error": f"Sem dados para '{SYMBOL_A}'/'{DI_SYMBOL}'.",
                "current_z": 0, "signal": _get_di_signal(0), "history": []}

    min_len = min(len(closes_win), len(closes_di))
    closes_win = closes_win[-min_len:]
    closes_di = closes_di[-min_len:]
    times_win = times_win[-min_len:]
    # OHLC for DI is the leg surfaced into _di_cache history (read back by
    # regime_v2). WIN OHLC stays here in case future callers need it; only DI
    # arrays are propagated downstream.
    opens_di = opens_di[-min_len:]
    highs_di = highs_di[-min_len:]
    lows_di = lows_di[-min_len:]

    today = datetime.now().date()

    # ── Johansen gate + beta ──────────────────────────────────────────
    joh_open, joh_ratio, joh_conv, joh_beta = _compute_johansen_gate(
        closes_win, closes_di, _joh_di_state, len(closes_win)
    )

    # ── DI OLS z-score (Kalman fails here due to inverse correlation forcing positive beta) ──
    ref_window = min(DI_BETA_REF_BARS, len(closes_win))
    beta_ref_20d = calc_beta_ols(closes_win[-ref_window:], closes_di[-ref_window:], window=ref_window)
    
    # We must use the OLS beta which correctly finds the negative correlation
    beta_current = beta_ref_20d
    spread_arr_full, z_arr_full, rho_arr_full = calc_zscore(
        closes_win, closes_di, beta=beta_current, window=DI_KALMAN_W, max_bars=len(closes_win)
    )
    
    spreads = spread_arr_full.tolist()
    z_arr = z_arr_full
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
    history = _build_history(
        times_win[-n_z:],
        z_arr,
        spread_arr[-n_z:],
        di_prices=closes_di[-n_z:],
        di_opens=opens_di[-n_z:],
        di_highs=highs_di[-n_z:],
        di_lows=lows_di[-n_z:],
    )

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
    account = mt5.account_info() if connected else None
    live_symbol_resolved = None
    live_symbol_error = None
    if connected:
        try:
            live_symbol_resolved = resolve_live_symbol_win(LIVE_SYMBOL_WIN)
        except Exception as exc:
            live_symbol_error = str(exc)
    eval_state = _get_eval_state()
    last_completed_epoch = eval_state.get("last_completed_epoch")
    last_completed_age_sec = (
        round(time.time() - last_completed_epoch, 1)
        if last_completed_epoch is not None else None
    )
    return {
        "mt5_connected": connected,
        "terminal_name": info.name if info else None,
        "terminal_path": info.path if info else None,
        "account_login": account.login if account else None,
        "account_server": account.server if account else None,
        "account_name": account.name if account else None,
        "configured_path": MT5_PATH or "(automatico)",
        "symbol_a": SYMBOL_A,
        "symbol_b": SYMBOL_B,
        "di_symbol": DI_SYMBOL,
        "live_symbol_win": live_symbol_resolved or LIVE_SYMBOL_WIN,
        "live_symbol_win_config": LIVE_SYMBOL_WIN,
        "live_symbol_win_resolved": live_symbol_resolved,
        "live_symbol_win_error": live_symbol_error,
        "live_orders_enabled": bool(LIVE_ORDERS),
        "risk_stats_scope": "live" if LIVE_ORDERS else "all",
        "trade_eval_loop": {
            "running": bool(eval_state.get("loop_running")),
            "in_progress": bool(eval_state.get("in_progress")),
            "interval_sec": POLL_INTERVAL_SEC,
            "last_source": eval_state.get("last_source"),
            "last_started_at": eval_state.get("last_started_at"),
            "last_completed_at": eval_state.get("last_completed_at"),
            "last_completed_age_sec": last_completed_age_sec,
            "last_duration_ms": eval_state.get("last_duration_ms"),
            "last_error": eval_state.get("last_error"),
            "last_error_at": eval_state.get("last_error_at"),
            "last_result_error": eval_state.get("last_result_error"),
            "has_snapshot": _latest_regime_snapshot is not None,
        },
        "bar_history": {
            "backend": bhdb.get_backend(),
            "sqlite_path": bhdb.sqlite_path(),
            "pg_write_failures": _pg_write_failures,
            "last_pg_write_failure": _last_pg_write_failure,
        },
    }


@app.get("/api/mt5-account")
def mt5_account():
    if not connect_mt5():
        return {"connected": False}
    ai = mt5.account_info()
    if ai is None:
        return {"connected": True, "account_info": None, "error": str(mt5.last_error())}
    return {
        "connected": True,
        "login": ai.login,
        "name": ai.name,
        "server": ai.server,
        "company": ai.company,
        "currency": ai.currency,
        "balance": ai.balance,
        "equity": ai.equity,
        "trade_mode": ai.trade_mode,
        "trade_mode_label": {0: "DEMO", 1: "CONTEST", 2: "REAL"}.get(ai.trade_mode, "?"),
        "trade_allowed": ai.trade_allowed,
        "trade_expert": ai.trade_expert,
        "leverage": ai.leverage,
    }


@app.get("/api/performance")
def get_performance():
    try:
        return _trade_engine.get_performance(limit=50)
    except Exception as e:
        return {"error": str(e)}


def _valid_replay_date(date_str: str | None) -> bool:
    if not date_str:
        return False
    try:
        parsed = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%d") == date_str


def _replay_timeline_db_path(date_str: str) -> str:
    return os.path.join(REPLAY_DIR, f"execution_timeline_{date_str}.db")


def _resolve_timeline_db(mode: str | None, date: str | None) -> dict:
    mode_norm = (mode or "live").lower()
    if mode_norm == "live":
        return {"ok": True, "mode": "live", "date": None, "db_path": DB_PATH}
    if mode_norm == "replay":
        if not _valid_replay_date(date):
            return {
                "ok": False,
                "status_code": 400,
                "error": "INVALID_REPLAY_DATE",
                "mode": "replay",
                "date": date,
            }
        db_path = _replay_timeline_db_path(date)
        if not os.path.exists(db_path):
            return {
                "ok": False,
                "status_code": 404,
                "error": "REPLAY_NOT_FOUND",
                "mode": "replay",
                "date": date,
                "db_path": db_path,
            }
        return {"ok": True, "mode": "replay", "date": date, "db_path": db_path}
    return {
        "ok": False,
        "status_code": 400,
        "error": "INVALID_TIMELINE_MODE",
        "mode": mode_norm,
    }


_EXPLAINED_TIMELINE_EVENTS = {
    "EG_NOT_COINTEGRATED",
    "EG_UNAVAILABLE",
    "RHO_BREAKDOWN",
    "BETA_DRIFT",
    "BETA_UNSTABLE",
    "Z_ANOMALY",
    "OUT_OF_SESSION",
    "MAX_TRADES_REACHED",
    "DAILY_LOSS_LIMIT",
    "LOSS_COOLDOWN",
    "MT5_DISCONNECTED",
}


def _enrich_timeline_message(row: dict | None) -> dict | None:
    if not row or row.get("event") not in _EXPLAINED_TIMELINE_EVENTS:
        return row
    out = dict(row)
    out["message"] = reason_message(
        str(row.get("event")),
        str(row.get("phase") or ""),
        row,
    )
    return out


def _enrich_timeline_messages(rows: list[dict]) -> list[dict]:
    return [_enrich_timeline_message(row) or row for row in rows]


def _minute_to_hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _timeline_market_bounds(market_hours: bool) -> tuple[str | None, str | None]:
    if not market_hours:
        return None, None
    return _minute_to_hhmm(SESSION_START), _minute_to_hhmm(SESSION_END)


def _timeline_closed_bar_offset(mode: str | None) -> int:
    return TIME_OFFSET if (mode or "live").lower() == "live" else 0


@app.get("/api/execution-timeline")
@app.get("/api/execution_timeline")
def execution_timeline_endpoint(
    limit: int = 200,
    phase: str | None = None,
    status: str | None = None,
    strategy: str | None = None,
    event: str | None = None,
    since: str | None = None,
    mode: str = "live",
    date: str | None = None,
    market_hours: bool = True,
):
    """Structured operational funnel events for the dashboard."""
    resolved = _resolve_timeline_db(mode, date)
    if not resolved["ok"]:
        content = {"error": resolved["error"]}
        if resolved["error"] in {"INVALID_REPLAY_DATE", "REPLAY_NOT_FOUND"}:
            content["date"] = resolved.get("date")
        if resolved["error"] == "INVALID_TIMELINE_MODE":
            content["mode"] = mode
        return JSONResponse(status_code=resolved["status_code"], content=content)

    db_path = resolved["db_path"]
    market_start, market_end = _timeline_market_bounds(market_hours)
    closed_bar_offset = _timeline_closed_bar_offset(resolved["mode"])

    events = _enrich_timeline_messages(
        load_timeline(
            db_path,
            limit=limit,
            phase=phase,
            status=status,
            strategy=strategy,
            event=event,
            since=since,
            time_start=market_start,
            time_end=market_end,
            closed_bar_offset_seconds=closed_bar_offset,
        )
    )
    return {
        "mode": resolved["mode"],
        "date": resolved["date"],
        "market_hours": bool(market_hours),
        "market_window": {"start": market_start, "end": market_end},
        "events": events,
        "summary": {
            "current_bottleneck": _enrich_timeline_message(
                current_bottleneck(
                    db_path,
                    time_start=market_start,
                    time_end=market_end,
                    closed_bar_offset_seconds=closed_bar_offset,
                )
            ),
            "current_live_issue": _enrich_timeline_message(
                current_live_issue(
                    db_path,
                    time_start=market_start,
                    time_end=market_end,
                    closed_bar_offset_seconds=closed_bar_offset,
                )
            ),
        },
    }


COMPARATIVE_DEFAULT_OURS = os.environ.get("COMPARATIVE_OURS_URL", "http://127.0.0.1:8080")
COMPARATIVE_DEFAULT_REF = os.environ.get("COMPARATIVE_REF_URL", "http://127.0.0.1:8081")
COMPARATIVE_OUT_DIR = os.environ.get("COMPARATIVE_OUT_DIR", "audits/live_compare")


def _run_comparative_snapshot(
    *,
    ours: str,
    ref: str,
    tag: str,
    timeout: float,
) -> dict:
    from scripts.compare_miqueias_live import _output_dir, run_compare

    run = run_compare(
        ours_base=ours,
        ref_base=ref,
        out_dir=_output_dir(COMPARATIVE_OUT_DIR, tag),
        timeout=timeout,
    )
    payload = asdict(run)
    for system, endpoints in (payload.get("fetch") or {}).items():
        for name, result in (endpoints or {}).items():
            payload["fetch"][system][name] = {
                "ok": result.get("ok"),
                "url": result.get("url"),
                "status_code": result.get("status_code"),
                "error": result.get("error"),
                "elapsed_ms": result.get("elapsed_ms"),
            }
    return payload


def _comparative_metric_pair(business: dict, key: str) -> dict:
    ours = (business.get("ours") or {}).get(key)
    ref = (business.get("ref") or {}).get(key)
    delta = None
    try:
        if ours is not None and ref is not None:
            delta = round(float(ours) - float(ref), 6)
    except (TypeError, ValueError):
        delta = None
    return {"ours": ours, "ref": ref, "delta": delta}


def _compact_comparative_summary(summary: dict, summary_path: str) -> dict:
    business = summary.get("business") or {}
    decision = summary.get("decision") or {}
    differences = summary.get("differences") or []
    run_id = os.path.basename(os.path.dirname(summary_path))
    return {
        "run_id": run_id,
        "timestamp": summary.get("timestamp"),
        "output_dir": summary.get("output_dir") or os.path.dirname(summary_path),
        "summary_path": summary_path,
        "diff_count": len(differences),
        "decision": decision,
        "signal_mismatch": bool(decision.get("has_signal_mismatch")),
        "actions": {
            "ours": (business.get("ours") or {}).get("strategy_actions") or {},
            "ref": (business.get("ref") or {}).get("strategy_actions") or {},
        },
        "metrics": {
            "z_wdo": _comparative_metric_pair(business, "current_z_wdo"),
            "z_di": _comparative_metric_pair(business, "current_z_di"),
            "rho": _comparative_metric_pair(business, "current_rho"),
            "eg_pvalue": _comparative_metric_pair(business, "eg_pvalue"),
            "di_eg_pvalue": _comparative_metric_pair(business, "di_eg_pvalue"),
            "beta_delta_pct": _comparative_metric_pair(business, "beta_delta_pct"),
        },
        "risk_gate_reasons": {
            "ours": (business.get("ours") or {}).get("risk_gate_reasons"),
            "ref": (business.get("ref") or {}).get("risk_gate_reasons"),
        },
        "differences": differences,
    }


def _comparative_history_rows(date: str | None, limit: int) -> list[dict]:
    base = COMPARATIVE_OUT_DIR
    if not os.path.isdir(base):
        return []

    if date:
        try:
            prefix = datetime.strptime(date, "%Y-%m-%d").strftime("%Y%m%d-")
        except ValueError:
            return []
    else:
        prefix = datetime.now().strftime("%Y%m%d-")

    candidates = []
    for name in os.listdir(base):
        if not name.startswith(prefix):
            continue
        summary_path = os.path.join(base, name, "summary.json")
        if os.path.isfile(summary_path):
            candidates.append(summary_path)

    rows = []
    for summary_path in sorted(candidates, reverse=True)[:max(1, min(limit, 1000))]:
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
            rows.append(_compact_comparative_summary(summary, summary_path))
        except Exception as exc:
            rows.append({
                "run_id": os.path.basename(os.path.dirname(summary_path)),
                "summary_path": summary_path,
                "error": f"{type(exc).__name__}: {exc}",
            })
    return rows


@app.get("/api/comparative")
def comparative_endpoint(
    ours: str = COMPARATIVE_DEFAULT_OURS,
    ref: str = COMPARATIVE_DEFAULT_REF,
    tag: str = "comparative-page",
    timeout: float = 8.0,
):
    """Capture one WDOWIN x Miqueias comparison snapshot and persist it."""
    try:
        return _run_comparative_snapshot(
            ours=ours,
            ref=ref,
            tag=tag,
            timeout=max(0.5, min(timeout, 30.0)),
        )
    except Exception as exc:
        logger.exception("comparative_snapshot_failed")
        return JSONResponse(
            status_code=500,
            content={
                "error": "COMPARATIVE_SNAPSHOT_FAILED",
                "message": f"{type(exc).__name__}: {exc}",
            },
        )


@app.get("/api/comparative/history")
def comparative_history_endpoint(
    date: str | None = None,
    limit: int = 200,
):
    """Intraday table of persisted WDOWIN x Miqueias snapshots."""
    return {
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "out_dir": COMPARATIVE_OUT_DIR,
        "rows": _comparative_history_rows(date, limit),
    }


@app.get("/comparative", response_class=HTMLResponse)
def comparative_html(
    request: Request,
    refresh: int = 300,
):
    """Standalone WDOWIN x Miqueias live comparison page."""
    return templates.TemplateResponse(
        request,
        "comparative.html",
        {
            "ours_url": COMPARATIVE_DEFAULT_OURS,
            "ref_url": COMPARATIVE_DEFAULT_REF,
            "refresh": max(0, min(refresh, 3600)),
            "rendered_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


@app.post("/api/execution-timeline/generate")
def execution_timeline_generate(date: str):
    """Trigger replay generation server-side. Returns the run summary."""
    if not _valid_replay_date(date):
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_REPLAY_DATE", "date": date},
        )

    with _replay_progress_lock:
        if date in _replay_in_progress:
            return JSONResponse(
                status_code=409,
                content={"error": "REPLAY_IN_PROGRESS", "date": date},
            )
        _replay_in_progress.add(date)

    try:
        from scripts.replay_execution_timeline import run_replay
        summary = run_replay(date_str=date, source_db=DB_PATH, out_dir=REPLAY_DIR)
        return {
            "ok": True,
            "date": date,
            "db_path": _replay_timeline_db_path(date),
            "summary": summary,
        }
    except Exception as exc:
        logger.exception("replay_generate_failed date=%s", date)
        return JSONResponse(
            status_code=500,
            content={
                "error": "REPLAY_FAILED",
                "date": date,
                "message": f"{type(exc).__name__}: {exc}",
            },
        )
    finally:
        with _replay_progress_lock:
            _replay_in_progress.discard(date)


_TIMELINE_PHASE_OPTIONS = (
    "DATA", "INDICATORS", "ELIGIBILITY", "RISK",
    "SIGNAL", "ORDER", "EXECUTION", "EXIT",
)
_TIMELINE_STATUS_OPTIONS = ("OK", "BLOCKED", "SKIPPED", "FAILED", "INFO")


def _timeline_row_class(status: str | None) -> str:
    if status in ("FAILED", "BLOCKED"):
        return "bad"
    if status == "OK":
        return "ok"
    if status == "SKIPPED":
        return "skip"
    return "warn"


@app.get("/execution-timeline", response_class=HTMLResponse)
def execution_timeline_html(
    request: Request,
    limit: int = 200,
    phase: str | None = None,
    status: str | None = None,
    strategy: str | None = None,
    event: str | None = None,
    refresh: int = 5,
    mode: str = "live",
    date: str | None = None,
    market_hours: bool = True,
):
    """Standalone server-rendered HTML view of the execution timeline."""
    resolved = _resolve_timeline_db(mode, date)
    mode_norm = resolved.get("mode", "live")
    replay_date = resolved.get("date")
    timeline_error = None
    if mode_norm == "replay":
        refresh = 0
    else:
        refresh = max(0, min(refresh, 3600))

    if resolved["ok"]:
        db_path = resolved["db_path"]
        market_start, market_end = _timeline_market_bounds(market_hours)
        closed_bar_offset = _timeline_closed_bar_offset(mode_norm)
        events = load_timeline(
            db_path,
            limit=limit,
            phase=phase or None,
            status=status or None,
            strategy=strategy or None,
            event=event or None,
            time_start=market_start,
            time_end=market_end,
            closed_bar_offset_seconds=closed_bar_offset,
        )
        events = _enrich_timeline_messages(events)
        current_bottleneck_obj = _enrich_timeline_message(
            current_bottleneck(
                db_path,
                time_start=market_start,
                time_end=market_end,
                closed_bar_offset_seconds=closed_bar_offset,
            )
        )
        current_live_issue_obj = _enrich_timeline_message(
            current_live_issue(
                db_path,
                time_start=market_start,
                time_end=market_end,
                closed_bar_offset_seconds=closed_bar_offset,
            )
        )
    else:
        market_start, market_end = _timeline_market_bounds(market_hours)
        events = []
        current_bottleneck_obj = None
        current_live_issue_obj = None
        if resolved["error"] == "REPLAY_NOT_FOUND":
            timeline_error = {
                "title": "Sem replay para esta data",
                "message": f"Rode o replay de {replay_date} antes de visualizar.",
            }
        elif resolved["error"] == "INVALID_REPLAY_DATE":
            if not date:
                timeline_error = {
                    "title": "Escolha uma data",
                    "message": "Selecione uma data acima para visualizar o replay.",
                }
            else:
                timeline_error = {
                    "title": "Data de replay inválida",
                    "message": "Use o formato YYYY-MM-DD.",
                }
        else:
            timeline_error = {
                "title": "Modo inválido",
                "message": "Use live ou replay.",
            }

    filters = {
        "mode": mode_norm if mode_norm in {"live", "replay"} else mode,
        "date": date or "",
        "phase": phase or "",
        "status": status or "",
        "strategy": strategy or "",
        "event": event or "",
        "limit": limit,
        "market_hours": "1" if market_hours else "0",
    }
    filters_active = (
        filters["mode"] != "live"
        or bool(filters["date"])
        or filters["market_hours"] != "1"
        or any(v for k, v in filters.items() if k not in {"limit", "mode", "date", "market_hours"})
        or limit != 200
    )
    qs = request.url.query
    return templates.TemplateResponse(
        request,
        "execution_timeline.html",
        {
            "events": events,
            "mode": filters["mode"],
            "replay_date": replay_date,
            "timeline_error": timeline_error,
            "current_bottleneck": current_bottleneck_obj,
            "current_live_issue": current_live_issue_obj,
            "filters": filters,
            "filters_active": filters_active,
            "phase_options": _TIMELINE_PHASE_OPTIONS,
            "status_options": _TIMELINE_STATUS_OPTIONS,
            "refresh": refresh,
            "market_window": {"start": market_start, "end": market_end},
            "rendered_at": datetime.now().isoformat(timespec="seconds"),
            "row_class": _timeline_row_class,
            "query_string": qs,
        },
    )


# ─── Multi-day History Endpoint ──────────────────────────────────────────────

_hist_cache: dict = {}
_hist_cache_ts: float = 0.0
_hist_cache_days: int = 0
_hist_cache_window: int = 0

@app.get("/api/trades")
def trades_endpoint(date: str):
    """Trades (OPEN + CLOSED) opened on `date` (YYYY-MM-DD).

    Lets the dashboard render trade markers on a historical day chart without
    pulling the full live regime payload.
    """
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_DATE", "date": date},
        )
    return {"date": date, "trades": _trade_engine.get_trades_for_date(date)}


@app.get("/api/runtime-config")
def runtime_config_get():
    """Return current Live + Replay runtime profiles (or defaults if unset)."""
    try:
        return runtime_config.load_runtime_config()
    except ValueError as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "RUNTIME_CONFIG_INVALID", "detail": str(exc)},
        )


@app.post("/api/runtime-config")
async def runtime_config_post(request: Request):
    """Persist Live + Replay runtime profiles. Whole-document replace."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_JSON"},
        )
    try:
        return runtime_config.save_runtime_config(payload)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "VALIDATION", "detail": str(exc)},
        )


@app.get("/api/history")
def history_endpoint(days: int = 30):
    """Multi-day z-score history (Kalman + OLS + DI).
    
    Returns session-filtered bars for the last N trading days.
    Each bar has: date, bar_time, z (Kalman), z_v1 (OLS), z_di (DI).
    """
    global _hist_cache, _hist_cache_ts, _hist_cache_days, _hist_cache_window

    # Pull the runtime window so the OLS z used for the dashboard history
    # matches the live engine's view (regime_v2 reads the same field). Loaded
    # before the cache check so a runtime POST that changes `window` busts the
    # cache immediately instead of serving stale data keyed on the old window.
    try:
        hist_profile = runtime_config.get_profile("live")
    except ValueError:
        hist_profile = copy.deepcopy(runtime_config.DEFAULTS["live"])
    hist_window = int(hist_profile["window"])

    # Cache for 30s (heavier computation)
    if (
        time.time() - _hist_cache_ts < 30
        and _hist_cache
        and _hist_cache_days == days
        and _hist_cache_window == hist_window
    ):
        return _hist_cache

    if not connect_mt5():
        return {"error": "MT5 não disponível.", "history": [], "days": days}

    try:
        # M5 bars: ~108 bars/session day (9:20-18:20), fetch extra for window warmup
        bars_per_day = 108
        bars_needed = max(days * bars_per_day + hist_window + 50, KALMAN_BURN_IN)

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

        # --- OLS z-scores (inline beta on the current window) ---
        beta_ols_val = calc_beta_ols(ac, bc, window=hist_window)
        _, z_ols, _ = calc_zscore(
            ac, bc, beta=beta_ols_val, window=hist_window, max_bars=min_len
        )

        # --- DI z-scores (Kalman) ---
        z_di_map = {}
        if closes_di is not None:
            min_di = min(len(ac), len(closes_di))
            di_c = closes_di[-min_di:]
            di_t = times_di[-min_di:]
            win_for_di = ac[-min_di:]

            # Keep historical DI aligned with /api/di-regime; Kalman flips this signal.
            ref_window = min(DI_BETA_REF_BARS, len(win_for_di))
            beta_di = calc_beta_ols(
                win_for_di[-ref_window:], di_c[-ref_window:], window=ref_window
            )
            _, z_di_arr, _ = calc_zscore(
                win_for_di, di_c, beta=beta_di,
                window=DI_KALMAN_W, max_bars=len(win_for_di)
            )

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
        _hist_cache_window = hist_window

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), "history": [], "days": days}


# ─── Startup ─────────────────────────────────────────────────────────────────
# NOTE: HMM background thread DISABLED — no longer used in this project.
# It was calling mt5.initialize() from a background thread, which is NOT
# thread-safe and caused Python segfaults (crashing all Python on the machine).
# hmm.start()

if __name__ == "__main__":
    import uvicorn
    print("=" * 55)
    print("  WIN×WDO+DI Regime Monitor — Servidor local")
    print("  WDO:    http://localhost:8080/api/v2/regime")
    print("  DI:     http://localhost:8080/api/di-regime")
    print("  Saude:  http://localhost:8080/health")
    print("  Docs:   http://localhost:8080/docs")
    print("=" * 55)
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=False)
