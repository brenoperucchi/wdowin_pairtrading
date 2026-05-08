# core/config.py
"""
WIN×WDO Setup Matador v4 — Centralized Configuration
==================================================
All trading parameters validated in backtest (2021-2026, 100k bars OOS).
WDO: Kalman Filter (KQ=1e-4, KR=1e2, KW=40) + NWE contra-trend
DI:  Kalman Filter (KQ=1e-3, KR=1e1, KW=60) + NWE contra-trend
CONS: z-scores WDO+DI alinhados (SEM filtro NWE)

Infrastructure constants (ports, paths, timeframes) merged from server.py.
"""
import os

try:
    import MetaTrader5 as mt5
except ImportError:
    # Non-Windows hosts (CI, WSL, the reconcile tooling) can't install
    # MetaTrader5. We only consume `mt5.TIMEFRAME_M5` here — anything that
    # actually needs the API (mt5_client.py, server.py) imports MT5 itself
    # and will raise loudly if missing. The stub keeps ImportError from
    # surfacing for read-only consumers like docs/reconcile/test tooling.
    class _MT5Stub:
        TIMEFRAME_M5 = 5
        ORDER_FILLING_RETURN = 2
    mt5 = _MT5Stub()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

# ─── Infrastructure ─────────────────────────────────────────────────────────
# Dedicated portable MT5 instance for pair trading (XP DEMO conta 52033102).
# Isolated from dco-collector, which runs against E:\...\Books\terminal64.exe
# at ~150 calls/s during 10:00–16:55 BRT — sharing would saturate the IPC queue.
# WIN$N, WDO$N, DI1$N must be enabled in Market Watch.
MT5_PATH = r"E:\MetaTraders\MT5-Python\Ticks\terminal64.exe"
MT5_PORTABLE = True

# ─── Symbols ────────────────────────────────────────────────────────────────
SYMBOL_A = "WIN$N"
SYMBOL_B = "WDO$N"

# ─── Timeframe & Windows ────────────────────────────────────────────────────
TIMEFRAME = mt5.TIMEFRAME_M5
WINDOW = 90
BARS = 250
KALMAN_BURN_IN = 15000
BETA_INITIAL = -22.5

# ─── WDO Pair Trading (WIN×WDO) — Kalman Filter ─────────────────────────────
WDO_KALMAN_Q = 1e-4             # Kalman trans_cov
WDO_KALMAN_R = 1e2              # Kalman obs_cov
WDO_KALMAN_W = 40               # Z-score rolling window
BETA_REF_BARS = 2240
BETA_REF_5D_BARS = 560
BETA_ALERT_PCT = 10.0
BETA_REF_WINDOW = 80
BETA_DELTA_MAX = 25.0
RHO_MIN = -0.40

# ─── Setup Matador: Entry ────────────────────────────────────────────────────
Z_ENTRY = 1.4          # Entry threshold
Z_ANOMALY = 4.0        # Anomaly threshold — don't trade
Z_ATTENTION = 1.2      # Attention zone display only

# ─── Setup Matador: BUY (V2 Kalman) ─────────────────────────────────────────
BUY_SL = 300           # Stop loss in WIN points
BUY_TP = 800           # Take profit in WIN points
BUY_BE_ACT = 300       # Breakeven activation (pts in favor)
BUY_BE_LOCK = 0        # Breakeven lock level (pts)

# ─── Setup Matador: SELL (V1 OLS) ───────────────────────────────────────────
SELL_SL = 300
SELL_TP = 800
SELL_BE_ACT = 300
SELL_BE_LOCK = 0

# ─── Sizing ─────────────────────────────────────────────────────────────────
WIN_CONTRACTS = 2
WIN_PV = 0.20          # R$/point/contract

# ─── Live order scaffold (TASK-2) ───────────────────────────────────────────
# Default remains paper-only. Set environment variable LIVE_ORDERS=1 only for
# an explicitly supervised DEMO/live process.
LIVE_ORDERS = _env_bool("LIVE_ORDERS", False)
LIVE_SYMBOL_WIN = SYMBOL_A
LIVE_DEVIATION = 50
LIVE_MAGIC_BASE = 770000
MAGIC_BY_STRATEGY = {
    "CONS_BASE": LIVE_MAGIC_BASE + 1,
    "WDO_NWE": LIVE_MAGIC_BASE + 2,
    "DI_NWE": LIVE_MAGIC_BASE + 3,
}
LIVE_FILLING = getattr(mt5, "ORDER_FILLING_RETURN", 2)

# ─── Execution costs (TASK-3 AC #15) ────────────────────────────────────────
# Used by validation-grade backtests (research/run_matador_v5_johansen.py)
# to convert gross point P&L into realized BRL P&L. The live engine does not
# read these — actual fills come back from MT5 already net of slippage and
# B3 charges them to the account separately.
#   - WIN_SLIPPAGE_PTS: applied on EACH side (entry + exit). Conservative
#     default of 1 tick (5 pts on WIN). Higher than typical fills but safer
#     to underestimate live P&L than overestimate.
#   - B3_COST_PER_CONTRACT_RT: round-trip B3 emolumentos + XP corretagem
#     per contract, in BRL. Default placeholder — confirmar com XP for the
#     live account before using this number for paridade decisions.
WIN_SLIPPAGE_PTS = 5
B3_COST_PER_CONTRACT_RT = 1.00

# ─── Session ────────────────────────────────────────────────────────────────
ENTRY_START_H = 9
ENTRY_START_M = 0
ENTRY_END_H = 15
ENTRY_END_M = 0
FORCE_CLOSE_H = 17
FORCE_CLOSE_M = 40

# ─── Server ─────────────────────────────────────────────────────────────────
CACHE_TTL = 2.0
TIME_OFFSET = 3 * 3600

# ─── DI Pair Trading (WIN×DI) — Kalman Filter ───────────────────────────────
DI_SYMBOL = "DI1$N"            # Contrato contínuo DI futuro
DI_KALMAN_Q = 1e-3             # Kalman trans_cov (adaptação rápida)
DI_KALMAN_R = 1e1              # Kalman obs_cov (baixa suavização)
DI_KALMAN_W = 60               # Z-score rolling window
DI_BETA_INITIAL = -10000.0     # Beta inicial WIN/DI (escala: WIN~135k, DI~13.5)
DI_BARS = 250                  # Barras para buscar do MT5
DI_BETA_REF_BARS = 2240        # Barras para beta referência 20d
DI_Z_ENTRY = 1.4               # Threshold de entrada
DI_Z_ANOMALY = 4.0             # Threshold de anomalia
DI_Z_ATTENTION = 1.2           # Zona de atenção

# ─── Johansen Gate (cointegration validation only) ──────────────────────────
JOH_WINDOW = 150               # Rolling window para teste de Johansen
JOH_RECHECK_BARS = 12          # Recalcular a cada N barras (~1h em M5)
JOH_BETA_TOLERANCE = 0.30      # Tolerância beta consistency (30%)

# ─── NWE (Nadaraya-Watson Envelope) — Validated OOS 2022-2026 ───────────────
NWE_BANDWIDTH = 8              # Kernel bandwidth
NWE_LOOKBACK = 95              # Lookback window (bars)
NWE_BAND_MULT = 0.10           # Adaptive band multiplier (fraction of band width)
NWE_MULT_MAE = 3.0             # MAE multiplier for bands

# ─── Operational risk (TASK-3 AC #11) ───────────────────────────────────────
# Conservative defaults. These are *floors* — production should tighten, not
# loosen. Each is enforced as a check inside `core.risk_gate.risk_gate(...)`.
# Calibration notes:
#   - MAX_TRADES_PER_DAY: 3 strategy slots × ~1 retry budget. Higher counts
#     correlate with overtrading on noise in past simulated runs.
#   - DAILY_LOSS_LIMIT_BRL: ~2× a single losing trade with WIN_CONTRACTS=2 at
#     BUY_SL=300 pts × WIN_PV=0.20 = R$ 120/contract = R$ 240 total. To
#     calibrate against live P&L distribution, see docs/RUNBOOK_ROLLOVER.md.
#   - LOSS_COOLDOWN_MIN: blocks ALL new entries after any STOP_LOSS for N
#     minutes. Global (not per-slot) by design — a fresh stop usually means
#     the regime is shifting, not just one strategy is wrong.
#   - BLOCK_ON_MT5_DISCONNECT: True is the only safe default for live; flip
#     only for offline backtests/replays.
MAX_TRADES_PER_DAY = 4
DAILY_LOSS_LIMIT_BRL = 240.0
LOSS_COOLDOWN_MIN = 30
BLOCK_ON_MT5_DISCONNECT = True
